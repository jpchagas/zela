import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.rbac.context import CondoContext, OrgContext, get_org_admin_context, require_permission
from app.rbac.permissions import Permission
from app.schemas.tenancy import (
    CondominiumCreate,
    CondominiumOut,
    CondominiumSummary,
    CondominiumUpdate,
    ManagerPhoneConfig,
    WhatsAppConfig,
)
from app.services import condominiums, manager_phone

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


@router.put("/condominiums/{condominium_id}/manager-phone", response_model=CondominiumOut)
def configure_manager_phone(
    body: ManagerPhoneConfig,
    ctx: CondoContext = Depends(require_permission(Permission.CONDOMINIUM_UPDATE)),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    """Sets the manager's WhatsApp and sends the confirmation message (resends it when
    called again with the same unconfirmed number)."""
    return manager_phone.set_manager_phone(db, ctx, body.number, publisher)
