import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.models.enums import ActorType

if TYPE_CHECKING:
    from app.rbac.context import CondoContext


def record(
    db: Session,
    *,
    organization_id: uuid.UUID | None,
    condominium_id: uuid.UUID | None,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the caller's transaction, so it commits or rolls back with
    the change it describes. Keep personal data values out of `data`."""
    event = AuditEvent(
        organization_id=organization_id,
        condominium_id=condominium_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data or {},
    )
    db.add(event)
    return event


def record_user_action(
    db: Session,
    ctx: "CondoContext",
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    **data: Any,
) -> AuditEvent:
    return record(
        db,
        organization_id=ctx.organization_id,
        condominium_id=ctx.condominium_id,
        actor_type=ActorType.USER,
        actor_id=ctx.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
    )


def list_events(
    db: Session, ctx: "CondoContext", *, entity_id: uuid.UUID | None, limit: int, offset: int
) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.condominium_id == ctx.condominium_id)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))
