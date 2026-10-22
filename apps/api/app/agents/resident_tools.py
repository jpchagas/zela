"""Tools available to the concierge for an enrolled resident (Milestone 2).

Each tool acts only for `ctx.resident_id`, which the orchestrator took from the verified
sender. No tool accepts a resident, unit or condominium ID from the model.
"""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.tools import Tool, ToolContext, ToolRegistry, ToolResult
from app.models import Building, Condominium, Conversation, Resident, Unit, UnitMembership
from app.models.enums import ActorType
from app.services import conversations

RELATIONSHIP_PT = {
    "owner": "proprietário(a)",
    "tenant": "inquilino(a)",
    "authorized_occupant": "morador(a) autorizado(a)",
}


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetResidentContext(Tool[NoArgs]):
    name = "get_resident_context"
    description = (
        "Returns the identified resident's own registration: first name, their units and "
        "relationship to each, and the condominium's administration contacts. Use it when "
        "the resident asks about their own registration or how to reach the administration. "
        "It never returns data about other residents."
    )
    args_model = NoArgs

    def run(self, db: Session, ctx: ToolContext, args: NoArgs) -> ToolResult:
        resident = db.get(Resident, ctx.resident_id)
        condo = db.get(Condominium, ctx.condominium_id)
        rows = db.execute(
            select(Unit.identifier, Building.name, UnitMembership.relationship)
            .join(UnitMembership, UnitMembership.unit_id == Unit.id)
            .outerjoin(Building, Building.id == Unit.building_id)
            .where(
                UnitMembership.condominium_id == ctx.condominium_id,
                UnitMembership.resident_id == ctx.resident_id,
                UnitMembership.ended_at.is_(None),
            )
        ).all()
        return ToolResult(
            ok=True,
            data={
                "first_name": resident.full_name.split()[0],
                "condominium": condo.name,
                "units": [
                    {
                        "unit": f"{building} · {identifier}" if building else identifier,
                        "relationship": RELATIONSHIP_PT[rel.value],
                    }
                    for identifier, building, rel in rows
                ],
                "administration_contact": {
                    "email": condo.contact_email,
                    "phone": condo.contact_phone,
                },
            },
        )


class EscalateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(
        min_length=3,
        max_length=500,
        description="Short summary in Portuguese of what the resident needs, for the staff.",
    )


class EscalateToHuman(Tool[EscalateArgs]):
    name = "escalate_to_human"
    description = (
        "Hands the conversation to the condominium staff. Use it when the resident asks for "
        "a person, when the request is outside what you can do, when you are not confident, "
        "or for anything urgent or sensitive. After calling it, tell the resident the staff "
        "will reply in this same chat. You stop answering until staff hand it back."
    )
    args_model = EscalateArgs

    def run(self, db: Session, ctx: ToolContext, args: EscalateArgs) -> ToolResult:
        conversations.escalate(
            db,
            db.get(Condominium, ctx.condominium_id),
            db.get(Conversation, ctx.conversation_id),
            reason=args.reason,
            actor_type=ActorType.AGENT,
            actor_id=ctx.agent_run_id,
        )
        return ToolResult(ok=True, data={"escalated": True})


def build_resident_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GetResidentContext())
    registry.register(EscalateToHuman())
    return registry
