import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidInput
from app.models import Resident, ResidentPhone, Unit, UnitMembership
from app.models.enums import ResidentStatus, UnitRelationship
from app.rbac.context import CondoContext
from app.schemas.residents import PhoneIn, ResidentCreate, ResidentUpdate
from app.services import audit
from app.services.common import flush_or_conflict, get_scoped
from app.services.phones import normalize_phone

PHONE_TAKEN = "This phone number is already registered to a resident of this condominium"


@dataclass
class ResidentDetail:
    resident: Resident
    phones: list[ResidentPhone]
    units: list[UnitMembership]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_residents(
    db: Session,
    ctx: CondoContext,
    *,
    status: ResidentStatus | None,
    unit_id: uuid.UUID | None,
    q: str | None,
    limit: int,
    offset: int,
) -> list[Resident]:
    stmt = select(Resident).where(Resident.condominium_id == ctx.condominium_id)
    if status is not None:
        stmt = stmt.where(Resident.status == status)
    if unit_id is not None:
        stmt = stmt.where(
            Resident.id.in_(
                select(UnitMembership.resident_id).where(
                    UnitMembership.condominium_id == ctx.condominium_id,
                    UnitMembership.unit_id == unit_id,
                    UnitMembership.ended_at.is_(None),
                )
            )
        )
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Resident.full_name.ilike(f"%{escaped}%", escape="\\"))
    stmt = stmt.order_by(func.lower(Resident.full_name)).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_detail(db: Session, ctx: CondoContext, resident_id: uuid.UUID) -> ResidentDetail:
    resident = get_scoped(db, Resident, ctx, resident_id)
    phones = db.scalars(
        select(ResidentPhone)
        .where(
            ResidentPhone.condominium_id == ctx.condominium_id,
            ResidentPhone.resident_id == resident.id,
        )
        .order_by(ResidentPhone.is_primary.desc(), ResidentPhone.created_at)
    ).all()
    units = db.scalars(
        select(UnitMembership)
        .where(
            UnitMembership.condominium_id == ctx.condominium_id,
            UnitMembership.resident_id == resident.id,
        )
        .order_by(UnitMembership.ended_at.is_not(None), UnitMembership.started_at.desc())
    ).all()
    return ResidentDetail(resident=resident, phones=list(phones), units=list(units))


def create(db: Session, ctx: CondoContext, data: ResidentCreate) -> ResidentDetail:
    resident = Resident(
        condominium_id=ctx.condominium_id,
        full_name=data.full_name,
        email=data.email,
        status=ResidentStatus.INVITED,
    )
    db.add(resident)
    db.flush()

    normalized = [normalize_phone(p.number) for p in data.phones]
    if len(set(normalized)) != len(normalized):
        raise InvalidInput("Duplicate phone numbers in request")
    if len({m.unit_id for m in data.units}) != len(data.units):
        raise InvalidInput("Duplicate units in request")
    has_primary = any(p.is_primary for p in data.phones)
    for i, (phone_in, e164) in enumerate(zip(data.phones, normalized, strict=True)):
        db.add(
            ResidentPhone(
                condominium_id=ctx.condominium_id,
                resident_id=resident.id,
                phone_e164=e164,
                is_primary=phone_in.is_primary or (not has_primary and i == 0),
            )
        )
    for membership in data.units:
        _add_membership(db, ctx, resident, membership.unit_id, membership.relationship)
    flush_or_conflict(db, PHONE_TAKEN)

    audit.record_user_action(
        db,
        ctx,
        "resident.created",
        "resident",
        resident.id,
        phone_count=len(normalized),
        unit_ids=[str(m.unit_id) for m in data.units],
    )
    db.commit()
    return get_detail(db, ctx, resident.id)


def update_resident(
    db: Session, ctx: CondoContext, resident_id: uuid.UUID, data: ResidentUpdate
) -> Resident:
    resident = get_scoped(db, Resident, ctx, resident_id)
    _ensure_not_revoked(resident)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(resident, field, value)
    audit.record_user_action(
        db, ctx, "resident.updated", "resident", resident.id, fields=sorted(changes)
    )
    db.commit()
    return resident


def suspend(db: Session, ctx: CondoContext, resident_id: uuid.UUID) -> Resident:
    resident = get_scoped(db, Resident, ctx, resident_id)
    if resident.status not in (ResidentStatus.INVITED, ResidentStatus.ACTIVE):
        raise Conflict(f"Cannot suspend a resident who is {resident.status}")
    return _set_status(db, ctx, resident, ResidentStatus.SUSPENDED)


def reinstate(db: Session, ctx: CondoContext, resident_id: uuid.UUID) -> Resident:
    resident = get_scoped(db, Resident, ctx, resident_id)
    if resident.status != ResidentStatus.SUSPENDED:
        raise Conflict("Only suspended residents can be reinstated")
    has_verified_phone = db.scalar(
        select(func.count())
        .select_from(ResidentPhone)
        .where(
            ResidentPhone.condominium_id == ctx.condominium_id,
            ResidentPhone.resident_id == resident.id,
            ResidentPhone.verified_at.is_not(None),
        )
    )
    # Only a completed enrollment makes someone active; otherwise they go back to invited.
    target = ResidentStatus.ACTIVE if has_verified_phone else ResidentStatus.INVITED
    return _set_status(db, ctx, resident, target)


def revoke(db: Session, ctx: CondoContext, resident_id: uuid.UUID) -> Resident:
    """Permanently end a resident's access: status becomes revoked and every active unit
    membership is closed. Phones are unlinked so the number can enroll elsewhere."""
    resident = get_scoped(db, Resident, ctx, resident_id)
    _ensure_not_revoked(resident)
    now = _now()
    db.execute(
        update(UnitMembership)
        .where(
            UnitMembership.condominium_id == ctx.condominium_id,
            UnitMembership.resident_id == resident.id,
            UnitMembership.ended_at.is_(None),
        )
        .values(ended_at=now)
    )
    phones = db.scalars(
        select(ResidentPhone).where(
            ResidentPhone.condominium_id == ctx.condominium_id,
            ResidentPhone.resident_id == resident.id,
        )
    ).all()
    for phone in phones:
        db.delete(phone)
    return _set_status(db, ctx, resident, ResidentStatus.REVOKED)


def add_phone(
    db: Session, ctx: CondoContext, resident_id: uuid.UUID, data: PhoneIn
) -> ResidentPhone:
    resident = get_scoped(db, Resident, ctx, resident_id)
    _ensure_not_revoked(resident)
    if data.is_primary:
        _clear_primary(db, ctx, resident.id)
    phone = ResidentPhone(
        condominium_id=ctx.condominium_id,
        resident_id=resident.id,
        phone_e164=normalize_phone(data.number),
        is_primary=data.is_primary,
    )
    db.add(phone)
    flush_or_conflict(db, PHONE_TAKEN)
    audit.record_user_action(db, ctx, "resident.phone_added", "resident", resident.id)
    db.commit()
    return phone


def remove_phone(
    db: Session, ctx: CondoContext, resident_id: uuid.UUID, phone_id: uuid.UUID
) -> None:
    resident = get_scoped(db, Resident, ctx, resident_id)
    phone = get_scoped(db, ResidentPhone, ctx, phone_id)
    if phone.resident_id != resident.id:
        raise InvalidInput("Phone does not belong to this resident")
    db.delete(phone)
    audit.record_user_action(db, ctx, "resident.phone_removed", "resident", resident.id)
    db.commit()


def add_unit_membership(
    db: Session,
    ctx: CondoContext,
    resident_id: uuid.UUID,
    unit_id: uuid.UUID,
    relationship: UnitRelationship,
) -> UnitMembership:
    resident = get_scoped(db, Resident, ctx, resident_id)
    _ensure_not_revoked(resident)
    membership = _add_membership(db, ctx, resident, unit_id, relationship)
    flush_or_conflict(db, "Resident is already linked to this unit")
    audit.record_user_action(
        db,
        ctx,
        "resident.unit_linked",
        "resident",
        resident.id,
        unit_id=str(unit_id),
        relationship=relationship.value,
    )
    db.commit()
    return membership


def end_unit_membership(
    db: Session, ctx: CondoContext, resident_id: uuid.UUID, membership_id: uuid.UUID
) -> UnitMembership:
    membership = get_scoped(db, UnitMembership, ctx, membership_id)
    if membership.resident_id != resident_id:
        raise InvalidInput("Membership does not belong to this resident")
    if membership.ended_at is not None:
        raise Conflict("Membership already ended")
    membership.ended_at = _now()
    audit.record_user_action(
        db, ctx, "resident.unit_unlinked", "resident", resident_id, unit_id=str(membership.unit_id)
    )
    db.commit()
    return membership


def _add_membership(
    db: Session,
    ctx: CondoContext,
    resident: Resident,
    unit_id: uuid.UUID,
    relationship: UnitRelationship,
) -> UnitMembership:
    get_scoped(db, Unit, ctx, unit_id)
    membership = UnitMembership(
        condominium_id=ctx.condominium_id,
        unit_id=unit_id,
        resident_id=resident.id,
        relationship=relationship,
    )
    db.add(membership)
    return membership


def _clear_primary(db: Session, ctx: CondoContext, resident_id: uuid.UUID) -> None:
    db.execute(
        update(ResidentPhone)
        .where(
            ResidentPhone.condominium_id == ctx.condominium_id,
            ResidentPhone.resident_id == resident_id,
        )
        .values(is_primary=False)
    )


def _set_status(
    db: Session, ctx: CondoContext, resident: Resident, status: ResidentStatus
) -> Resident:
    previous = resident.status
    resident.status = status
    resident.status_changed_at = _now()
    audit.record_user_action(
        db,
        ctx,
        "resident.status_changed",
        "resident",
        resident.id,
        **{"from": previous.value, "to": status.value},
    )
    db.commit()
    return resident


def _ensure_not_revoked(resident: Resident) -> None:
    if resident.status == ResidentStatus.REVOKED:
        raise Conflict("Resident access was revoked; create a new resident record instead")
