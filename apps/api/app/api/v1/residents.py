import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ResidentStatus
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.common import Page
from app.schemas.residents import (
    PhoneIn,
    PhoneOut,
    ResidentCreate,
    ResidentDetail,
    ResidentOut,
    ResidentUpdate,
    UnitMembershipIn,
    UnitMembershipOut,
)
from app.services import residents

router = APIRouter(prefix="/condominiums/{condominium_id}/residents", tags=["residents"])

can_read = require_permission(Permission.RESIDENTS_READ)
can_manage = require_permission(Permission.RESIDENTS_MANAGE)


def _detail(d: residents.ResidentDetail) -> ResidentDetail:
    return ResidentDetail(
        **ResidentOut.model_validate(d.resident).model_dump(),
        phones=[PhoneOut.model_validate(p) for p in d.phones],
        units=[UnitMembershipOut.model_validate(m) for m in d.units],
    )


@router.get("", response_model=Page[ResidentOut])
def list_residents(
    status_: ResidentStatus | None = Query(None, alias="status"),
    unit_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CondoContext = Depends(can_read),
    db: Session = Depends(get_db),
):
    items = residents.list_residents(
        db, ctx, status=status_, unit_id=unit_id, q=q, limit=limit, offset=offset
    )
    return Page(items=items, limit=limit, offset=offset)


@router.post("", response_model=ResidentDetail, status_code=status.HTTP_201_CREATED)
def create_resident(
    body: ResidentCreate, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return _detail(residents.create(db, ctx, body))


@router.get("/{resident_id}", response_model=ResidentDetail)
def get_resident(
    resident_id: uuid.UUID, ctx: CondoContext = Depends(can_read), db: Session = Depends(get_db)
):
    return _detail(residents.get_detail(db, ctx, resident_id))


@router.patch("/{resident_id}", response_model=ResidentOut)
def update_resident(
    resident_id: uuid.UUID,
    body: ResidentUpdate,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return residents.update_resident(db, ctx, resident_id, body)


@router.post("/{resident_id}/suspend", response_model=ResidentOut)
def suspend_resident(
    resident_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return residents.suspend(db, ctx, resident_id)


@router.post("/{resident_id}/reinstate", response_model=ResidentOut)
def reinstate_resident(
    resident_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return residents.reinstate(db, ctx, resident_id)


@router.post("/{resident_id}/revoke", response_model=ResidentOut)
def revoke_resident(
    resident_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return residents.revoke(db, ctx, resident_id)


@router.post("/{resident_id}/phones", response_model=PhoneOut, status_code=status.HTTP_201_CREATED)
def add_phone(
    resident_id: uuid.UUID,
    body: PhoneIn,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return residents.add_phone(db, ctx, resident_id, body)


@router.delete("/{resident_id}/phones/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_phone(
    resident_id: uuid.UUID,
    phone_id: uuid.UUID,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    residents.remove_phone(db, ctx, resident_id, phone_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{resident_id}/units", response_model=UnitMembershipOut, status_code=status.HTTP_201_CREATED
)
def link_unit(
    resident_id: uuid.UUID,
    body: UnitMembershipIn,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return residents.add_unit_membership(db, ctx, resident_id, body.unit_id, body.relationship)


@router.post("/{resident_id}/units/{membership_id}/end", response_model=UnitMembershipOut)
def end_unit_link(
    resident_id: uuid.UUID,
    membership_id: uuid.UUID,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    return residents.end_unit_membership(db, ctx, resident_id, membership_id)
