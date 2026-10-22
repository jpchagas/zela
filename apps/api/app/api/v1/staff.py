import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.tenancy import StaffInvite, StaffMemberOut
from app.services import staff

router = APIRouter(prefix="/condominiums/{condominium_id}/staff", tags=["staff"])


@router.get("", response_model=list[StaffMemberOut])
def list_staff(
    ctx: CondoContext = Depends(require_permission(Permission.STAFF_READ)),
    db: Session = Depends(get_db),
):
    return staff.list_members(db, ctx)


@router.post("", response_model=StaffMemberOut, status_code=status.HTTP_201_CREATED)
def invite_staff(
    body: StaffInvite,
    ctx: CondoContext = Depends(require_permission(Permission.STAFF_MANAGE)),
    db: Session = Depends(get_db),
):
    return staff.invite(db, ctx, body)


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_staff(
    membership_id: uuid.UUID,
    ctx: CondoContext = Depends(require_permission(Permission.STAFF_MANAGE)),
    db: Session = Depends(get_db),
):
    staff.revoke(db, ctx, membership_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
