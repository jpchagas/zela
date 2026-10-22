import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rbac.context import CondoContext, OrgContext, get_org_admin_context, require_permission
from app.rbac.permissions import Permission
from app.schemas.tenancy import (
    CondominiumCreate,
    CondominiumOut,
    CondominiumSummary,
    CondominiumUpdate,
    WhatsAppConfig,
)
from app.services import condominiums

router = APIRouter(tags=["condominiums"])


@router.post(
    "/organizations/{organization_id}/condominiums",
    response_model=CondominiumOut,
    status_code=status.HTTP_201_CREATED,
)
def create_condominium(
    organization_id: uuid.UUID,
    body: CondominiumCreate,
    ctx: OrgContext = Depends(get_org_admin_context),
    db: Session = Depends(get_db),
):
    return condominiums.create(db, ctx, body)


@router.get("/condominiums/{condominium_id}", response_model=CondominiumOut)
def get_condominium(ctx: CondoContext = Depends(require_permission(Permission.CONDOMINIUM_READ))):
    return ctx.condominium


@router.patch("/condominiums/{condominium_id}", response_model=CondominiumOut)
def update_condominium(
    body: CondominiumUpdate,
    ctx: CondoContext = Depends(require_permission(Permission.CONDOMINIUM_UPDATE)),
    db: Session = Depends(get_db),
):
    return condominiums.update(db, ctx, body)


@router.get("/condominiums/{condominium_id}/summary", response_model=CondominiumSummary)
def get_summary(
    ctx: CondoContext = Depends(require_permission(Permission.CONDOMINIUM_READ)),
    db: Session = Depends(get_db),
):
    return condominiums.summary(db, ctx)


@router.put("/condominiums/{condominium_id}/whatsapp", response_model=CondominiumOut)
def configure_whatsapp(
    body: WhatsAppConfig,
    ctx: CondoContext = Depends(require_permission(Permission.CONDOMINIUM_UPDATE)),
    db: Session = Depends(get_db),
):
    return condominiums.set_whatsapp(db, ctx, body.whatsapp_phone_number_id)
