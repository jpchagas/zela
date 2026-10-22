import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Building
from app.rbac.context import CondoContext
from app.schemas.tenancy import BuildingCreate, BuildingUpdate
from app.services import audit
from app.services.common import flush_or_conflict, get_scoped


def list_buildings(db: Session, ctx: CondoContext) -> list[Building]:
    return list(
        db.scalars(
            select(Building)
            .where(Building.condominium_id == ctx.condominium_id)
            .order_by(Building.name)
        )
    )


def create(db: Session, ctx: CondoContext, data: BuildingCreate) -> Building:
    building = Building(condominium_id=ctx.condominium_id, name=data.name)
    db.add(building)
    flush_or_conflict(db, "A building with this name already exists")
    audit.record_user_action(db, ctx, "building.created", "building", building.id)
    db.commit()
    return building


def update(
    db: Session, ctx: CondoContext, building_id: uuid.UUID, data: BuildingUpdate
) -> Building:
    building = get_scoped(db, Building, ctx, building_id)
    building.name = data.name
    flush_or_conflict(db, "A building with this name already exists")
    audit.record_user_action(db, ctx, "building.updated", "building", building.id)
    db.commit()
    return building


def delete(db: Session, ctx: CondoContext, building_id: uuid.UUID) -> None:
    building = get_scoped(db, Building, ctx, building_id)
    db.delete(building)
    flush_or_conflict(db, "Building still has units")
    audit.record_user_action(db, ctx, "building.deleted", "building", building_id)
    db.commit()
