import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.operations import EmergencyContactIn, EmergencyContactOut
from app.services import emergency_contacts

router = APIRouter(
    prefix="/condominiums/{condominium_id}/emergency-contacts", tags=["emergency contacts"]
)

can_manage = require_permission(Permission.CONDOMINIUM_UPDATE)


@router.get("", response_model=list[EmergencyContactOut])
def list_contacts(ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)):
    return emergency_contacts.list_contacts(db, ctx)


@router.post("", response_model=EmergencyContactOut, status_code=status.HTTP_201_CREATED)
def add_contact(
    body: EmergencyContactIn, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    return emergency_contacts.add(db, ctx, name=body.name, role=body.role, phone=body.phone)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contact(
    contact_id: uuid.UUID, ctx: CondoContext = Depends(can_manage), db: Session = Depends(get_db)
):
    emergency_contacts.remove(db, ctx, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
