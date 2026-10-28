import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmergencyContact
from app.rbac.context import CondoContext
from app.services import audit
from app.services.common import flush_or_conflict, get_scoped
from app.services.phones import normalize_phone


def list_contacts(db: Session, ctx: CondoContext) -> list[EmergencyContact]:
    return list(
        db.scalars(
            select(EmergencyContact)
            .where(EmergencyContact.condominium_id == ctx.condominium_id)
            .order_by(EmergencyContact.created_at)
        )
    )


def add(
    db: Session, ctx: CondoContext, *, name: str, role: str | None, phone: str
) -> EmergencyContact:
    contact = EmergencyContact(
        condominium_id=ctx.condominium_id,
        name=name.strip(),
        role=(role or "").strip() or None,
        phone_e164=normalize_phone(phone),
    )
    db.add(contact)
    flush_or_conflict(db, "This number is already an on-call contact")
    audit.record_user_action(db, ctx, "emergency_contact.added", "emergency_contact", contact.id)
    db.commit()
    return contact


def remove(db: Session, ctx: CondoContext, contact_id: uuid.UUID) -> None:
    contact = get_scoped(db, EmergencyContact, ctx, contact_id)
    db.delete(contact)
    audit.record_user_action(db, ctx, "emergency_contact.removed", "emergency_contact", contact_id)
    db.commit()


def is_emergency_contact(db: Session, condominium_id: uuid.UUID, e164: str) -> bool:
    return (
        db.scalar(
            select(EmergencyContact.id).where(
                EmergencyContact.condominium_id == condominium_id,
                EmergencyContact.phone_e164 == e164,
            )
        )
        is not None
    )
