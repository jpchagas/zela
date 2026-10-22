import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.common import Page
from app.schemas.tenancy import (
    BuildingCreate,
    BuildingOut,
    BuildingUpdate,
    UnitCreate,
    UnitOut,
    UnitUpdate,
)
from app.services import buildings, units

router = APIRouter(prefix="/condominiums/{condominium_id}", tags=["buildings & units"])

can_read = require_permission(Permission.UNITS_READ)
can_manage = require_permission(Permission.UNITS_MANAGE)


@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings(ctx: CondoContext = Depends(can_read), db: Session = Depends(get_db)):
    return buildings.list_buildings(db, ctx)


@router.post("/buildings", response_model=BuildingOut, status_code=status.HTTP_201_CREATED)
def create_building(
    body: BuildingCreate, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return buildings.create(db, ctx, body)


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
def update_building(
    building_id: uuid.UUID,
    body: BuildingUpdate,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return buildings.update(db, ctx, building_id, body)


@router.delete("/buildings/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_building(
    building_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    buildings.delete(db, ctx, building_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/units", response_model=Page[UnitOut])
def list_units(
    building_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: CondoContext = Depends(can_read),
    db: Session = Depends(get_db),
):
    items = units.list_units(db, ctx, building_id=building_id, limit=limit, offset=offset)
    return Page(items=items, limit=limit, offset=offset)


@router.post("/units", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(
    body: UnitCreate, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return units.create(db, ctx, body)


@router.get("/units/{unit_id}", response_model=UnitOut)
def get_unit(
    unit_id: uuid.UUID, ctx: CondoContext = Depends(can_read), db: Session = Depends(get_db)
):
    return units.get(db, ctx, unit_id)


@router.patch("/units/{unit_id}", response_model=UnitOut)
def update_unit(
    unit_id: uuid.UUID,
    body: UnitUpdate,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return units.update(db, ctx, unit_id, body)
