"""Occurrence tools for sheet-backed condominiums (ADR 0012).

Anyone identified can report an occurrence and follow their own; only the manager can
list everyone's and change them. Reporting is a single step, since emergencies can't wait
for a confirmation round-trip. A manager's change notifies the reporter, so it takes the
same two steps as changing a person (ADR 0011).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.people_tools import SHEETS_DOWN, NoArgs, _person, _require_manager
from app.agents.tools import Tool, ToolContext, ToolError, ToolResult, preview_key, was_previewed
from app.models import Condominium
from app.models.enums import ActorType, RegisterKind, TicketCategory, TicketPriority
from app.registers.table import Row, normalize_header
from app.services import audit, drive, occurrences, people, tickets
from app.services.drive import RegisterUnavailable
from app.services.occurrences import CLOSED, STATUS_LABEL

TypeArg = Literal["manutencao", "reclamacao", "sugestao", "outro"]
StatusArg = Literal["aberta", "em_andamento", "aguardando", "resolvida", "cancelada"]
CategoryArg = Literal[tuple(c.value for c in TicketCategory)]  # type: ignore[valid-type]
PriorityArg = Literal["low", "normal", "high", "emergency"]


def _occurrence_out(row: Row, *, with_reporter: bool) -> dict:
    data = {
        "number": row.values["number"],
        "opened_at": row.values["opened_at"],
        "type": row.values["type"],
        "description": row.values["description"][:300],
        "location": row.values["location"],
        "place": " ".join(p for p in (row.values["block"], row.values["unit"]) if p),
        "category": row.values["category"],
        "priority": row.values["priority"],
        "status": row.values["status"],
    }
    if with_reporter:
        data["reported_by"] = row.values["reported_by"]
        data["assignee"] = row.values["assignee"]
    return data


class ReportArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: TypeArg = Field(description="manutencao for things broken or needing repair.")
    description: str = Field(
        min_length=5, max_length=1000, description="What happened, in the sender's words."
    )
    location: str = Field(
        min_length=2, max_length=150, description="Where, e.g. 'garagem, portão 2'."
    )
    in_own_unit: bool = Field(description="True if the problem is inside the sender's unit.")
    unit: str | None = Field(
        default=None,
        max_length=60,
        description="Which of the sender's units, when they have more than one.",
    )
    category: CategoryArg  # type: ignore[valid-type]
    priority: PriorityArg = Field(
        description="Your suggestion; emergency for risk to people or property right now."
    )


class ReportOccurrence(Tool[ReportArgs]):
    name = "report_occurrence"
    description = (
        "Registers a complaint, maintenance problem or suggestion in the condominium's "
        "Ocorrências spreadsheet and returns its number. Category and priority are your "
        "suggestion; the system validates them. For emergencies it also alerts the on-call "
        "contacts and the manager."
    )
    args_model = ReportArgs

    def run(self, db: Session, ctx: ToolContext, args: ReportArgs) -> ToolResult:
        person = _person(ctx)
        membership = None
        if args.in_own_unit or args.unit:
            if not person.memberships:
                raise ToolError("The sender has no unit on record; ask where it happened.")
            if args.unit:
                wanted = normalize_header(args.unit)
                membership = next(
                    (m for m in person.memberships if wanted in normalize_header(m.label)), None
                )
                if membership is None:
                    raise ToolError(
                        "That is not one of the sender's units: "
                        + ", ".join(m.label for m in person.memberships)
                    )
            elif len(person.memberships) == 1:
                membership = person.memberships[0]
            else:
                raise ToolError("Ask which unit: " + ", ".join(m.label for m in person.memberships))
        try:
            result = occurrences.report(
                db,
                ctx.google,
                ctx.publisher,
                condo=db.get(Condominium, ctx.condominium_id),
                person=person,
                membership=membership,
                type_=args.type,
                description=args.description,
                location=args.location,
                ai_category=TicketCategory(args.category),
                ai_priority=TicketPriority(args.priority),
                idempotency_key=ctx.idempotency_key,
                actor_id=ctx.agent_run_id,
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True,
            data={
                "reference": f"#{result.number}",
                "category": result.category,
                "priority": result.priority,
                "emergency_procedure_started": result.emergency,
                "on_call_alerted": result.alerted,
            },
        )


class GetMyOccurrences(Tool[NoArgs]):
    name = "get_my_occurrences"
    description = "Lists the occurrences the sender reported (up to 10, newest first)."
    args_model = NoArgs

    def run(self, db: Session, ctx: ToolContext, args: NoArgs) -> ToolResult:
        try:
            rows = occurrences.mine(
                db, ctx.google, db.get(Condominium, ctx.condominium_id), _person(ctx)
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True, data={"occurrences": [_occurrence_out(r, with_reporter=False) for r in rows]}
        )


class FindArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    only_open: bool = True
    query: str = Field(default="", max_length=80, description="Number, word, place or unit.")


class FindOccurrences(Tool[FindArgs]):
    name = "find_occurrences"
    description = (
        "Manager only. Lists occurrences (open ones by default, newest first, up to 15), "
        "optionally filtered by number, word, place or unit."
    )
    args_model = FindArgs

    def run(self, db: Session, ctx: ToolContext, args: FindArgs) -> ToolResult:
        _require_manager(ctx)
        try:
            table = drive.open_table(
                db, ctx.google, ctx.condominium_id, RegisterKind.OCCURRENCES, lock=False
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        rows = occurrences.find(table, only_open=args.only_open, query=args.query)
        return ToolResult(
            ok=True, data={"occurrences": [_occurrence_out(r, with_reporter=True) for r in rows]}
        )


class UpdateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int = Field(ge=1, description="The occurrence number, e.g. 12 for #12.")
    status: StatusArg | None = None
    note_for_reporter: str = Field(
        default="", max_length=300, description="Sent to the reporter with a status change."
    )
    internal_note: str = Field(
        default="", max_length=300, description="Added to Observações; the reporter doesn't see it."
    )
    assignee: str | None = Field(default=None, max_length=80)
    category: CategoryArg | None = None  # type: ignore[valid-type]
    priority: PriorityArg | None = None
    confirmed: bool = Field(
        default=False,
        description="false: return a summary of the change to show the manager. true: "
        "apply it, only after the manager confirmed that summary in a later message.",
    )


class UpdateOccurrence(Tool[UpdateArgs]):
    name = "update_occurrence"
    description = (
        "Manager only. Changes an occurrence's status, assignee, category or priority, or "
        "adds a note. A status change notifies whoever reported it. Two steps: "
        "confirmed=false for the summary, then confirmed=true after the manager confirms."
    )
    args_model = UpdateArgs
    requires_confirmation = True

    def run(self, db: Session, ctx: ToolContext, args: UpdateArgs) -> ToolResult:
        _require_manager(ctx)
        changes: dict[str, str] = {}
        if args.status is not None:
            changes["status"] = STATUS_LABEL[args.status]
        if args.assignee is not None:
            changes["assignee"] = args.assignee
        if args.category is not None:
            changes["category"] = tickets.CATEGORY_LABEL[TicketCategory(args.category)]
        if args.priority is not None:
            changes["priority"] = tickets.PRIORITY_LABEL[TicketPriority(args.priority)]
        if not changes and not args.internal_note:
            raise ToolError("Nothing to change.")
        key = preview_key(args)

        condo = db.get(Condominium, ctx.condominium_id)
        try:
            table = drive.open_table(db, ctx.google, condo.id, RegisterKind.OCCURRENCES)
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        row = occurrences.by_number(table, str(args.number))
        if row is None:
            db.commit()
            raise ToolError(f"There is no occurrence #{args.number}.")
        status_changed = "status" in changes and changes["status"] != row.values["status"]
        if not args.confirmed:
            db.commit()
            return ToolResult(
                ok=True,
                data={
                    "needs_confirmation": True,
                    "occurrence": _occurrence_out(row, with_reporter=True),
                    "changes": changes,
                    "internal_note": args.internal_note,
                    "reporter_will_be_notified": status_changed,
                },
                log={"preview_key": key},
            )
        if not was_previewed(db, ctx, self.name, key):
            db.commit()
            raise ToolError(
                "Not done yet. First call with confirmed=false, show the manager the summary "
                "and ask them to confirm; call with confirmed=true only after they confirm."
            )

        now = people.local_timestamp(condo)
        values = {**changes, "updated_at": now}
        if args.internal_note:
            previous = row.values["notes"]
            values["notes"] = f"{previous}\n{now}: {args.internal_note}".strip()
        if status_changed:
            values["closed_at"] = now if changes["status"] in CLOSED else ""
        if not row.zela_id:
            table.assign_id(row, f"O-ROW{row.number}")
        updated = table.update(row.zela_id, values)
        audit.record(
            db,
            organization_id=condo.organization_id,
            condominium_id=condo.id,
            actor_type=ActorType.AGENT,
            actor_id=ctx.agent_run_id,
            action="occurrence.updated",
            entity_type="sheet_row",
            entity_id=None,
            data={
                "register": "occurrences",
                "number": updated.values["number"],
                "fields": sorted(k for k in values if k != "updated_at"),
            },
        )
        db.commit()
        notified = False
        if status_changed:
            try:
                notified = occurrences.notify_reporter(
                    db, ctx.google, ctx.publisher, condo, updated, args.note_for_reporter
                )
            except RegisterUnavailable:
                notified = False
        return ToolResult(
            ok=True,
            data={
                "updated": True,
                "occurrence": _occurrence_out(updated, with_reporter=True),
                "reporter_notified": notified,
            },
        )
