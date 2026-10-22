import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Building, Unit
from app.rbac.context import CondoContext
from app.schemas.tenancy import UnitCreate, UnitUpdate
from app.services import audit
from app.services.common import flush_or_conflict, get_scoped


def list_units(
    db: Session, ctx: CondoContext, *, building_id: uuid.UUID | None, limit: int, offset: int
) -> list[Unit]:
    stmt = select(Unit).where(Unit.condominium_id == ctx.condominium_id)
    if building_id is not None:
        stmt = stmt.where(Unit.building_id == building_id)
    stmt = (
        stmt.outerjoin(Building, Building.id == Unit.building_id)
        .order_by(Building.name.nulls_first(), func.length(Unit.identifier), Unit.identifier)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def get(db: Session, ctx: CondoContext, unit_id: uuid.UUID) -> Unit:
    return get_scoped(db, Unit, ctx, unit_id)


def create(db: Session, ctx: CondoContext, data: UnitCreate) -> Unit:
    if data.building_id is not None:
        get_scoped(db, Building, ctx, data.building_id)
    unit = Unit(condominium_id=ctx.condominium_id, **data.model_dump())
    db.add(unit)
    flush_or_conflict(db, "A unit with this identifier already exists")
    audit.record_user_action(db, ctx, "unit.created", "unit", unit.id)
    db.commit()
    return unit


def update(db: Session, ctx: CondoContext, unit_id: uuid.UUID, data: UnitUpdate) -> Unit:
    unit = get_scoped(db, Unit, ctx, unit_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("building_id") is not None:
        get_scoped(db, Building, ctx, changes["building_id"])
    for field, value in changes.items():
        setattr(unit, field, value)
    flush_or_conflict(db, "A unit with this identifier already exists")
    audit.record_user_action(db, ctx, "unit.updated", "unit", unit.id, fields=sorted(changes))
    db.commit()
    return unit
