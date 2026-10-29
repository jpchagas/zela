"""Delivery tools for sheet-backed condominiums (ADR 0013).

Staff and the manager record packages and mark them as picked up; anyone can ask about
the packages waiting for their own units. Recording is a single step: it is frequent,
happens at a busy front desk, and only tells the unit that something arrived.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.people_tools import NoArgs, _person
from app.agents.tools import Tool, ToolContext, ToolError, ToolResult
from app.models import Condominium
from app.models.enums import ActorType, RegisterKind
from app.registers.table import Row
from app.services import audit, deliveries, drive, people
from app.services.deliveries import PICKED_UP, RETURNED, AmbiguousUnit
from app.services.drive import RegisterUnavailable
from app.services.people import PersonRole

SHEETS_DOWN = "The spreadsheets can't be used right now: {reason} Nothing was changed."


def _require_desk(ctx: ToolContext) -> None:
    if _person(ctx).role not in (PersonRole.STAFF, PersonRole.MANAGER):
        raise ToolError("Only the condominium's staff or manager can do this.")


def _delivery_out(row: Row, *, with_desk: bool) -> dict:
    data = {
        "number": row.values["number"],
        "received_at": row.values["received_at"],
        "place": deliveries.place_of(row),
        "recipient": row.values["recipient"],
        "description": row.values["description"][:200],
        "status": row.values["status"] or deliveries.WAITING,
    }
    if with_desk:
        data["picked_up_at"] = row.values["picked_up_at"]
        data["picked_up_by"] = row.values["picked_up_by"]
    return data


class RecordArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit: str = Field(min_length=1, max_length=20, description="Unit number, e.g. '302'.")
    block: str = Field(default="", max_length=40, description="Block or tower, if given.")
    recipient: str = Field(
        default="", max_length=80, description="Name on the package, if the staff said it."
    )
    description: str = Field(
        default="",
        max_length=200,
        description="What arrived, e.g. 'caixa média, Mercado Livre'. One package per call.",
    )


class RecordDelivery(Tool[RecordArgs]):
    name = "record_delivery"
    description = (
        "Staff or manager only. Records one package received at the front desk in the "
        "Encomendas spreadsheet and notifies the unit on WhatsApp. Returns its number."
    )
    args_model = RecordArgs

    def run(self, db: Session, ctx: ToolContext, args: RecordArgs) -> ToolResult:
        _require_desk(ctx)
        try:
            result = deliveries.receive(
                db,
                ctx.google,
                ctx.publisher,
                condo=db.get(Condominium, ctx.condominium_id),
                person=_person(ctx),
                block=args.block,
                unit=args.unit,
                recipient=args.recipient,
                description=args.description,
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
                "reference": f"#{result.number}",
                "place": result.place,
                "people_notified": result.notified,
                "recipient_found": result.recipient_found,
            },
        )


class GetMyDeliveries(Tool[NoArgs]):
    name = "get_my_deliveries"
    description = "Lists the packages waiting at the front desk for the sender's own units."
    args_model = NoArgs

    def run(self, db: Session, ctx: ToolContext, args: NoArgs) -> ToolResult:
        try:
            rows = deliveries.mine(
                db, ctx.google, db.get(Condominium, ctx.condominium_id), _person(ctx)
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        return ToolResult(
            ok=True, data={"deliveries": [_delivery_out(r, with_desk=False) for r in rows]}
        )


class FindArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    only_waiting: bool = True
    query: str = Field(default="", max_length=80, description="Number, unit, name or word.")


class FindDeliveries(Tool[FindArgs]):
    name = "find_deliveries"
    description = (
        "Staff or manager only. Lists packages (waiting ones by default, newest first, up "
        "to 15), optionally filtered by number, unit, recipient or description."
    )
    args_model = FindArgs

    def run(self, db: Session, ctx: ToolContext, args: FindArgs) -> ToolResult:
        _require_desk(ctx)
        try:
            table = drive.open_table(
                db, ctx.google, ctx.condominium_id, RegisterKind.DELIVERIES, lock=False
            )
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        rows = deliveries.find(table, only_waiting=args.only_waiting, query=args.query)
        return ToolResult(
            ok=True, data={"deliveries": [_delivery_out(r, with_desk=True) for r in rows]}
        )


class CloseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int = Field(ge=1, description="The package number, e.g. 7 for #7.")
    outcome: Literal["retirada", "devolvida"] = Field(
        default="retirada", description="retirada: someone collected it. devolvida: sent back."
    )
    picked_up_by: str = Field(
        default="", max_length=80, description="Who collected it, as the staff said."
    )
    note: str = Field(default="", max_length=200, description="Added to Observações.")


class CloseDelivery(Tool[CloseArgs]):
    name = "close_delivery"
    description = (
        "Staff or manager only. Marks a waiting package as picked up (or returned to the "
        "sender), by its number."
    )
    args_model = CloseArgs

    def run(self, db: Session, ctx: ToolContext, args: CloseArgs) -> ToolResult:
        _require_desk(ctx)
        condo = db.get(Condominium, ctx.condominium_id)
        try:
            table = drive.open_table(db, ctx.google, condo.id, RegisterKind.DELIVERIES)
        except RegisterUnavailable as exc:
            raise ToolError(SHEETS_DOWN.format(reason=exc.message)) from exc
        row = deliveries.by_number(table, str(args.number))
        if row is None:
            db.commit()
            raise ToolError(f"There is no package #{args.number}.")
        if not deliveries.is_waiting(row):
            db.commit()
            raise ToolError(
                f"Package #{args.number} is not waiting any more: {row.values['status']}."
            )
        now = people.local_timestamp(condo)
        values = {
            "status": PICKED_UP if args.outcome == "retirada" else RETURNED,
            "picked_up_at": now,
            "picked_up_by": args.picked_up_by,
        }
        if args.note:
            values["notes"] = f"{row.values['notes']}\n{now}: {args.note}".strip()
        if not row.zela_id:
            table.assign_id(row, f"E-ROW{row.number}")
        updated = table.update(row.zela_id, values)
        audit.record(
            db,
            organization_id=condo.organization_id,
            condominium_id=condo.id,
            actor_type=ActorType.AGENT,
            actor_id=ctx.agent_run_id,
            action="delivery.closed",
            entity_type="sheet_row",
            entity_id=None,
            data={
                "register": "deliveries",
                "number": updated.values["number"],
                "outcome": args.outcome,
            },
        )
        db.commit()
        return ToolResult(
            ok=True, data={"closed": True, "delivery": _delivery_out(updated, with_desk=True)}
        )
