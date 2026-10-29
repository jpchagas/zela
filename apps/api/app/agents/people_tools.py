"""Tools for sheet-backed condominiums (ADR 0010/0011), chosen by the sender's role.

The sender is `ctx.person`, which the worker identified from the stored record before the
run. No tool takes the actor, their role or the condominium from the model. Registering
or changing a person is consequential, so it runs in two steps: a summary first
(confirmed=false), and the write only from a later message (confirmed=true).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.tools import (
    Tool,
    ToolContext,
    ToolError,
    ToolResult,
    preview_key,
    was_previewed,
)
from app.core.errors import InvalidInput
from app.integrations.whatsapp.templates import PERSON_WELCOME
from app.models import Condominium
from app.models.enums import ActorType
from app.registers.table import Row
from app.services import audit, notifications, people
from app.services.drive import RegisterUnavailable
from app.services.people import ROLE_LABEL, STATUS_ACTIVE, STATUS_INACTIVE, PersonRole
from app.services.phones import normalize_phone

RoleArg = Literal["sindico", "proprietario", "morador", "funcionario"]
ROLE_ARG = {
    "sindico": PersonRole.MANAGER,
    "proprietario": PersonRole.OWNER,
    "morador": PersonRole.RESIDENT,
    "funcionario": PersonRole.STAFF,
}
NEEDS_PREVIEW = (
    "Not done yet. First call with confirmed=false, show the manager the summary and ask "
    "them to confirm; call with confirmed=true only after they reply confirming it."
)
SHEETS_DOWN = "The Pessoas spreadsheet can't be used right now: {reason} Nothing was changed."


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _person(ctx: ToolContext) -> people.Person:
    if ctx.person is None:
        raise ToolError("No identified sender")
    return ctx.person


def _require_manager(ctx: ToolContext) -> None:
    if _person(ctx).role != PersonRole.MANAGER:
        raise ToolError("Only the condominium's manager can do this.")


def _table(db: Session, ctx: ToolContext):
    try:
        return people.open_people(db, ctx.google, ctx.condominium_id)
    except RegisterUnavailable as exc:
        raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc


def _row_out(row: Row) -> dict:
    return {
        "id": row.zela_id,
        "name": row.values["name"],
        "whatsapp": row.values["whatsapp"],
        "role": row.values["role"],
        "block": row.values["block"],
        "unit": row.values["unit"],
        "status": STATUS_INACTIVE if not people.is_active(row) else STATUS_ACTIVE,
        "notes": row.values["notes"],
    }


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidInput as exc:
        raise ToolError(
            "That WhatsApp number is not valid. Ask for the number with area code, "
            "e.g. 11 98765-4321."
        ) from exc


def _audit(db: Session, ctx: ToolContext, action: str, **data) -> None:
    condo = db.get(Condominium, ctx.condominium_id)
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.AGENT,
        actor_id=ctx.agent_run_id,
        action=action,
        entity_type="sheet_row",
        entity_id=None,
        data={"register": "people", **data},
    )


class GetMyRegistration(Tool[NoArgs]):
    name = "get_my_registration"
    description = (
        "Returns the sender's own registration in the condominium: name, role and units. "
        "Never returns anyone else's data."
    )
    args_model = NoArgs

    def run(self, db: Session, ctx: ToolContext, args: NoArgs) -> ToolResult:
        person = _person(ctx)
        return ToolResult(
            ok=True,
            data={
                "name": person.name,
                "role": person.role_label,
                "units": [
                    {"place": m.label, "role": ROLE_LABEL[m.role]} for m in person.memberships
                ],
            },
        )


class RegisterArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120, description="Full name.")
    whatsapp: str = Field(
        min_length=8, max_length=30, description="The person's WhatsApp, with area code."
    )
    role: RoleArg
    block: str = Field(default="", max_length=40, description="Block or tower, if any.")
    unit: str = Field(
        default="",
        max_length=40,
        description="Unit number, e.g. '302'. Required for owners and residents.",
    )
    notes: str = Field(default="", max_length=300)
    confirmed: bool = Field(
        default=False,
        description="false: validate and return a summary to show the manager. true: "
        "register, only after the manager confirmed that summary in a later message.",
    )


class RegisterPerson(Tool[RegisterArgs]):
    name = "register_person"
    description = (
        "Manager only. Registers a resident, owner, staff member or manager in the "
        "condominium's Pessoas spreadsheet, so they can use Zela on WhatsApp. Two steps: "
        "call with confirmed=false to get a summary, show it and ask the manager to "
        "confirm, then call again with confirmed=true after they confirm. The person gets "
        "a welcome message on WhatsApp."
    )
    args_model = RegisterArgs
    requires_confirmation = True

    def run(self, db: Session, ctx: ToolContext, args: RegisterArgs) -> ToolResult:
        _require_manager(ctx)
        phone = _phone(args.whatsapp)
        role = ROLE_ARG[args.role]
        if role in (PersonRole.OWNER, PersonRole.RESIDENT) and not args.unit.strip():
            raise ToolError("Ask which unit the person lives in or owns.")
        normalized = args.model_copy(
            update={"whatsapp": phone, "name": " ".join(args.name.split())}
        )
        key = preview_key(normalized)

        table = _table(db, ctx)
        same_number = [r for r in table.rows if people.phone_of(r) == phone and people.is_active(r)]
        duplicate = next(
            (r for r in same_number if people.same_place(r, args.block, args.unit)), None
        )
        if duplicate is not None:
            db.commit()  # release the sheet lock
            return ToolResult(
                ok=True, data={"already_registered": True, "person": _row_out(duplicate)}
            )
        summary = {
            "name": normalized.name,
            "whatsapp": phone,
            "role": ROLE_LABEL[role],
            "block": args.block,
            "unit": args.unit,
            "notes": args.notes,
            "also_registered_in": [r.values["unit"] for r in same_number],
        }
        if not args.confirmed:
            db.commit()
            return ToolResult(
                ok=True,
                data={"needs_confirmation": True, "summary": summary},
                log={"preview_key": key},
            )
        if not was_previewed(db, ctx, self.name, key):
            db.commit()
            raise ToolError(NEEDS_PREVIEW)

        condo = db.get(Condominium, ctx.condominium_id)
        now = people.local_timestamp(condo)
        zela_id = people.new_person_id(f"{ctx.condominium_id}:{key}")
        row = table.append(
            zela_id,
            {
                "name": normalized.name,
                "whatsapp": phone,
                "block": args.block,
                "unit": args.unit,
                "role": ROLE_LABEL[role],
                "status": STATUS_ACTIVE,
                "notes": args.notes,
                "created_at": now,
                "updated_at": now,
            },
        )
        _audit(db, ctx, "person.registered", zela_id=zela_id, role=str(role))
        db.commit()  # the row is in the sheet; this records it and releases the lock
        welcome = phone != _person(ctx).phone
        if welcome:
            notifications.enqueue(
                db,
                ctx.publisher,
                condominium_id=condo.id,
                recipient_e164=phone,
                template=PERSON_WELCOME.name,
                params={"first_name": normalized.name.split()[0], "condominium": condo.name},
                idempotency_key=f"welcome:{zela_id}",
            )
        return ToolResult(
            ok=True,
            data={
                "registered": True,
                "id": row.zela_id,
                "row": row.number,
                "welcome_message_sent": welcome,
            },
        )


class FindArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        min_length=2, max_length=80, description="Part of a name, a unit, or phone digits."
    )


class FindPeople(Tool[FindArgs]):
    name = "find_people"
    description = (
        "Manager only. Searches the Pessoas spreadsheet by name, unit or phone digits and "
        "returns up to 10 people with their IDs (needed to update someone)."
    )
    args_model = FindArgs

    def run(self, db: Session, ctx: ToolContext, args: FindArgs) -> ToolResult:
        _require_manager(ctx)
        table = _table(db, ctx)
        rows = people.search(table, args.query)
        for row in rows:
            # Rows typed by hand have no ID yet; give them one so they can be updated.
            table.assign_id(row, people.new_person_id(f"{ctx.condominium_id}:row:{row.number}"))
        db.commit()
        return ToolResult(ok=True, data={"people": [_row_out(r) for r in rows]})


class UpdateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: str = Field(min_length=3, max_length=40, description="ID from find_people.")
    name: str | None = Field(default=None, min_length=2, max_length=120)
    whatsapp: str | None = Field(default=None, min_length=8, max_length=30)
    role: RoleArg | None = None
    block: str | None = Field(default=None, max_length=40)
    unit: str | None = Field(default=None, max_length=40)
    status: Literal["ativo", "inativo"] | None = Field(
        default=None, description="'inativo' removes the person's access to Zela."
    )
    notes: str | None = Field(default=None, max_length=300)
    confirmed: bool = Field(
        default=False,
        description="false: return a summary of the change to show the manager. true: "
        "apply it, only after the manager confirmed that summary in a later message.",
    )


class UpdatePerson(Tool[UpdateArgs]):
    name = "update_person"
    description = (
        "Manager only. Changes someone's registration (name, WhatsApp, role, block, unit, "
        "notes) or deactivates/reactivates them. Find their ID with find_people first. Two "
        "steps, like register_person: confirmed=false for the summary, then confirmed=true "
        "after the manager confirms."
    )
    args_model = UpdateArgs
    requires_confirmation = True

    def run(self, db: Session, ctx: ToolContext, args: UpdateArgs) -> ToolResult:
        _require_manager(ctx)
        changes: dict[str, str] = {}
        if args.name is not None:
            changes["name"] = " ".join(args.name.split())
        if args.whatsapp is not None:
            changes["whatsapp"] = _phone(args.whatsapp)
        if args.role is not None:
            changes["role"] = ROLE_LABEL[ROLE_ARG[args.role]]
        for field in ("block", "unit", "notes"):
            if getattr(args, field) is not None:
                changes[field] = getattr(args, field)
        if args.status is not None:
            changes["status"] = STATUS_ACTIVE if args.status == "ativo" else STATUS_INACTIVE
        if not changes:
            raise ToolError("Nothing to change.")
        key = preview_key({"person_id": args.person_id, **changes})

        table = _table(db, ctx)
        row = table.find(args.person_id)
        if row is None:
            db.commit()
            raise ToolError("No person with that ID. Use find_people to get the right ID.")
        if not args.confirmed:
            db.commit()
            return ToolResult(
                ok=True,
                data={
                    "needs_confirmation": True,
                    "person": _row_out(row),
                    "changes": changes,
                },
                log={"preview_key": key},
            )
        if not was_previewed(db, ctx, self.name, key):
            db.commit()
            raise ToolError(NEEDS_PREVIEW)
        condo = db.get(Condominium, ctx.condominium_id)
        updated = table.update(
            args.person_id, {**changes, "updated_at": people.local_timestamp(condo)}
        )
        _audit(db, ctx, "person.updated", zela_id=args.person_id, fields=sorted(changes))
        db.commit()
        return ToolResult(ok=True, data={"updated": True, "person": _row_out(updated)})
