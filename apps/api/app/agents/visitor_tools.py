"""Visitor tools for sheet-backed condominiums (ADR 0014).

Residents, owners and the manager authorize visitors (two steps, like ADR 0011: it lets
someone into the building) and answer the desk when a visitor shows up unannounced.
Staff and the manager check visitors at the desk, announce the unannounced ones and
record entries. No tool reveals who authorized a visit beyond what the desk needs.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.delivery_tools import SHEETS_DOWN, _require_desk
from app.agents.people_tools import NoArgs, _person
from app.agents.tools import Tool, ToolContext, ToolError, ToolResult, preview_key, was_previewed
from app.models import Condominium
from app.models.enums import RegisterKind
from app.registers.table import Row, normalize_header
from app.services import drive, people, visitors
from app.services.drive import RegisterUnavailable
from app.services.people import AmbiguousUnit, Membership, PersonRole
from app.services.visitors import VisitorError


def _visitor_out(row: Row, on: date, *, for_desk: bool) -> dict:
    data = {
        "code": row.values["code"],
        "visitor": row.values["visitor"],
        "place": visitors.place_of(row),
        "visit_date": row.values["visit_date"],
        "valid_until": row.values["valid_until"],
        "status": visitors.status_of(row, on),
    }
    if for_desk:
        data["notes"] = row.values["notes"][:200]
    return data


def _condo(db: Session, ctx: ToolContext) -> Condominium:
    return db.get(Condominium, ctx.condominium_id)


class AuthorizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visitor_name: str = Field(min_length=2, max_length=80, description="The visitor's name.")
    visit_date: date = Field(description="First day of the visit (YYYY-MM-DD, local date).")
    last_day: date | None = Field(
        default=None, description="Last day, for visits over several days (e.g. a cleaner)."
    )
    unit: str | None = Field(
        default=None,
        max_length=20,
        description="Which unit, when the sender has more than one. The manager may give "
        "any unit, or none for a visit to the condominium itself.",
    )
    block: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=200, description="E.g. 'entregador de móveis'.")
    confirmed: bool = Field(
        default=False,
        description="false: return a summary to show the sender. true: authorize, only "
        "after the sender confirmed that summary in a later message.",
    )


class AuthorizeVisitor(Tool[AuthorizeArgs]):
    name = "authorize_visitor"
    description = (
        "Authorizes a visitor for one of the sender's units and returns a code to give the "
        "visitor. Two steps: confirmed=false for the summary, then confirmed=true after "
        "the sender confirms."
    )
    args_model = AuthorizeArgs
    requires_confirmation = True

    def run(self, db: Session, ctx: ToolContext, args: AuthorizeArgs) -> ToolResult:
        person = _person(ctx)
        condo = _condo(db, ctx)
        try:
            last = visitors.check_dates(condo, args.visit_date, args.last_day)
            membership, block, unit = self._place(db, ctx, args)
        except VisitorError as exc:
            raise ToolError(str(exc)) from exc
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        summary = {
            "visitor": " ".join(args.visitor_name.split()),
            "place": " ".join(p for p in (block, unit) if p) or "condomínio",
            "visit_date": visitors.fmt(args.visit_date),
            "valid_until": visitors.fmt(last),
            "notes": args.notes,
        }
        key = preview_key(args)
        if not args.confirmed:
            return ToolResult(
                ok=True,
                data={"needs_confirmation": True, "summary": summary},
                log={"preview_key": key},
            )
        if not was_previewed(db, ctx, self.name, key):
            raise ToolError(
                "Not done yet. First call with confirmed=false, show the sender the summary "
                "and ask them to confirm; call with confirmed=true only after they confirm."
            )
        try:
            result = visitors.authorize(
                db,
                ctx.google,
                condo=condo,
                person=person,
                membership=membership,
                block=block,
                unit=unit,
                visitor=args.visitor_name,
                first=args.visit_date,
                last=last,
                notes=args.notes,
                idempotency_key=ctx.idempotency_key,
                actor_id=ctx.agent_run_id,
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(ok=True, data={"authorized": True, "code": result.code, **summary})

    def _place(
        self, db: Session, ctx: ToolContext, args: AuthorizeArgs
    ) -> tuple[Membership | None, str, str]:
        person = _person(ctx)
        own = [m for m in person.memberships if m.unit]
        if args.unit:
            wanted = normalize_header(args.unit)
            matches = [
                m
                for m in own
                if normalize_header(m.unit) == wanted
                and (not args.block or normalize_header(m.block) == normalize_header(args.block))
            ]
            if len(matches) == 1:
                return matches[0], matches[0].block, matches[0].unit
            if person.role != PersonRole.MANAGER:
                raise VisitorError(
                    "That is not one of the sender's units: "
                    + (", ".join(m.label for m in own) or "none")
                )
            table = drive.open_table(
                db, ctx.google, ctx.condominium_id, RegisterKind.PEOPLE, lock=False
            )
            try:
                block, unit = people.resolve_place(table, args.block, args.unit)
            except AmbiguousUnit as exc:
                raise VisitorError(
                    f"Unit {args.unit} exists in more than one block ({exc}). Ask which."
                ) from exc
            return None, block, unit
        if len(own) == 1:
            return own[0], own[0].block, own[0].unit
        if own:
            raise VisitorError("Ask which unit: " + ", ".join(m.label for m in own))
        if person.role == PersonRole.MANAGER:
            return None, "", ""  # a visit to the condominium itself
        raise VisitorError("The sender has no unit on record; suggest talking to the manager.")


class GetMyVisitors(Tool[NoArgs]):
    name = "get_my_visitors"
    description = (
        "Lists the visitors authorized for the sender's units that are still to come, and "
        "any visitor waiting at the front desk for the unit's answer."
    )
    args_model = NoArgs

    def run(self, db: Session, ctx: ToolContext, args: NoArgs) -> ToolResult:
        condo = _condo(db, ctx)
        try:
            table = drive.open_table(db, ctx.google, condo.id, RegisterKind.VISITORS, lock=False)
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        on = visitors.today(condo)
        rows = visitors.for_units(table, _person(ctx), on)
        return ToolResult(
            ok=True, data={"visitors": [_visitor_out(r, on, for_desk=False) for r in rows]}
        )


class CodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=4, max_length=12, description="The 6-digit visitor code.")


class AnswerArgs(CodeArgs):
    allow: bool = Field(description="true to let the visitor in, false to refuse.")


class AnswerVisitor(Tool[AnswerArgs]):
    name = "answer_visitor"
    description = (
        "Answers the front desk about a visitor waiting at the gate for the sender's unit "
        "(the notice has the code). Lets them in or refuses, and tells the desk."
    )
    args_model = AnswerArgs

    def run(self, db: Session, ctx: ToolContext, args: AnswerArgs) -> ToolResult:
        try:
            row, told = visitors.answer(
                db,
                ctx.google,
                ctx.publisher,
                condo=_condo(db, ctx),
                person=_person(ctx),
                code=args.code,
                allow=args.allow,
                actor_id=ctx.agent_run_id,
            )
        except VisitorError as exc:
            raise ToolError(str(exc)) from exc
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True,
            data={"visitor": row.values["visitor"], "allowed": args.allow, "desk_told": told},
        )


class CancelVisitor(Tool[CodeArgs]):
    name = "cancel_visitor"
    description = "Cancels a visitor authorization of the sender's units, by its code."
    args_model = CodeArgs

    def run(self, db: Session, ctx: ToolContext, args: CodeArgs) -> ToolResult:
        try:
            row = visitors.cancel(
                db,
                ctx.google,
                condo=_condo(db, ctx),
                person=_person(ctx),
                code=args.code,
                actor_id=ctx.agent_run_id,
            )
        except VisitorError as exc:
            raise ToolError(str(exc)) from exc
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(ok=True, data={"cancelled": True, "visitor": row.values["visitor"]})


class CheckArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        default="", max_length=80, description="Visitor name, code or unit; empty for all."
    )


class CheckVisitor(Tool[CheckArgs]):
    name = "check_visitor"
    description = (
        "Staff or manager only. Finds visitors authorized for today, or waiting for a "
        "unit's answer, by name, code or unit."
    )
    args_model = CheckArgs

    def run(self, db: Session, ctx: ToolContext, args: CheckArgs) -> ToolResult:
        _require_desk(ctx)
        condo = _condo(db, ctx)
        try:
            table = drive.open_table(db, ctx.google, condo.id, RegisterKind.VISITORS, lock=False)
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        on = visitors.today(condo)
        rows = visitors.at_desk(table, args.query, on)
        return ToolResult(
            ok=True, data={"visitors": [_visitor_out(r, on, for_desk=True) for r in rows]}
        )


class AnnounceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visitor_name: str = Field(min_length=2, max_length=80)
    unit: str = Field(min_length=1, max_length=20)
    block: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=200, description="E.g. 'técnico da internet'.")


class AnnounceVisitor(Tool[AnnounceArgs]):
    name = "announce_visitor"
    description = (
        "Staff or manager only. For a visitor at the gate who is not authorized: asks the "
        "unit on WhatsApp whether to let them in. The answer comes back to the sender."
    )
    args_model = AnnounceArgs

    def run(self, db: Session, ctx: ToolContext, args: AnnounceArgs) -> ToolResult:
        _require_desk(ctx)
        try:
            row, asked = visitors.announce(
                db,
                ctx.google,
                ctx.publisher,
                condo=_condo(db, ctx),
                person=_person(ctx),
                block=args.block,
                unit=args.unit,
                visitor=args.visitor_name,
                notes=args.notes,
                idempotency_key=ctx.idempotency_key,
                actor_id=ctx.agent_run_id,
            )
        except AmbiguousUnit as exc:
            raise ToolError(
                f"Unit {args.unit} exists in more than one block ({exc}). Ask which block."
            ) from exc
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True,
            data={
                "code": row.values["code"],
                "place": visitors.place_of(row),
                "people_asked": asked,
            },
        )


class RecordVisitorEntry(Tool[CodeArgs]):
    name = "record_visitor_entry"
    description = (
        "Staff or manager only. Records that an authorized visitor entered, by the code "
        "from check_visitor. Tells whoever authorized the visit."
    )
    args_model = CodeArgs

    def run(self, db: Session, ctx: ToolContext, args: CodeArgs) -> ToolResult:
        _require_desk(ctx)
        condo = _condo(db, ctx)
        try:
            row, told = visitors.record_entry(
                db,
                ctx.google,
                ctx.publisher,
                condo=condo,
                person=_person(ctx),
                code=args.code,
                idempotency_key=ctx.idempotency_key,
                actor_id=ctx.agent_run_id,
            )
        except VisitorError as exc:
            raise ToolError(str(exc)) from exc
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True,
            data={
                "entered": True,
                "visitor": _visitor_out(row, visitors.today(condo), for_desk=True),
                "authorizer_told": told,
            },
        )
