from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.models import (
    Building,
    Condominium,
    Document,
    Organization,
    OrganizationMembership,
    Resident,
    StaffMembership,
    Unit,
    User,
)
from app.models.enums import ActorType, DocumentStatus, OrgRole, ResidentStatus
from app.rbac.context import CondoContext, OrgContext, resolve_condo_role
from app.rbac.permissions import Role
from app.schemas.tenancy import CondominiumCreate, CondominiumSummary, CondominiumUpdate
from app.services import audit, conversations, tickets
from app.services.common import flush_or_conflict


def list_accessible(db: Session, user: User) -> list[tuple[Condominium, Role]]:
    org_ids = select(OrganizationMembership.organization_id).where(
        OrganizationMembership.user_id == user.id, OrganizationMembership.revoked_at.is_(None)
    )
    staff_condo_ids = select(StaffMembership.condominium_id).where(
        StaffMembership.user_id == user.id, StaffMembership.revoked_at.is_(None)
    )
    condos = db.scalars(
        select(Condominium)
        .where(
            or_(
                Condominium.organization_id.in_(org_ids),
                Condominium.id.in_(staff_condo_ids),
            )
        )
        .order_by(Condominium.name)
    ).all()
    result = []
    for condo in condos:
        role = resolve_condo_role(db, user, condo)
        if role is not None:
            result.append((condo, role))
    return result


def list_organizations(db: Session, user: User) -> list[tuple[Organization, OrgRole]]:
    """Organizations the user may add condominiums to (owners and admins)."""
    return [
        (org, role)
        for org, role in db.execute(
            select(Organization, OrganizationMembership.role)
            .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
            .where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.revoked_at.is_(None),
            )
            .order_by(Organization.name)
        )
    ]


def create(db: Session, ctx: OrgContext, data: CondominiumCreate) -> Condominium:
    condo = Condominium(organization_id=ctx.organization.id, **data.model_dump())
    db.add(condo)
    flush_or_conflict(db, "Condominium could not be created")
    audit.record(
        db,
        organization_id=ctx.organization.id,
        condominium_id=condo.id,
        actor_type=ActorType.USER,
        actor_id=ctx.user.id,
        action="condominium.created",
        entity_type="condominium",
        entity_id=condo.id,
    )
    db.commit()
    return condo


def update(db: Session, ctx: CondoContext, data: CondominiumUpdate) -> Condominium:
    changes = data.model_dump(exclude_unset=True)
    condo = ctx.condominium
    for field, value in changes.items():
        setattr(condo, field, value)
    audit.record_user_action(
        db, ctx, "condominium.updated", "condominium", condo.id, fields=sorted(changes)
    )
    db.commit()
    return condo


def summary(db: Session, ctx: CondoContext) -> CondominiumSummary:
    condo_id = ctx.condominium_id

    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model).where(model.condominium_id == condo_id)
        return db.scalar(stmt.where(*where)) or 0

    open_tickets, open_emergencies = tickets.count_open(db, condo_id)
    by_status = db.execute(
        select(Resident.status, func.count())
        .where(Resident.condominium_id == condo_id)
        .group_by(Resident.status)
    ).all()
    return CondominiumSummary(
        buildings=count(Building),
        units=count(Unit),
        residents_by_status={s.value: 0 for s in ResidentStatus}
        | {s.value: n for s, n in by_status},
        staff=count(StaffMembership, StaffMembership.revoked_at.is_(None)),
        conversations_escalated=conversations.count_escalated(db, condo_id),
        tickets_open=open_tickets,
        tickets_emergency_open=open_emergencies,
        documents_failed=count(Document, Document.status == DocumentStatus.FAILED),
    )


def set_whatsapp(db: Session, ctx: CondoContext, phone_number_id: str | None) -> Condominium:
    # Routes inbound messages to this tenant, so a mistake here misdelivers residents'
    # messages: only organization admins may change it.
    if not ctx.is_org_level:
        raise Forbidden("Only organization admins can configure WhatsApp")
    condo = ctx.condominium
    condo.whatsapp_phone_number_id = phone_number_id
    flush_or_conflict(db, "This WhatsApp number is already linked to another condominium")
    audit.record_user_action(db, ctx, "condominium.whatsapp_configured", "condominium", condo.id)
    db.commit()
    return condo
