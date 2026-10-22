"""Resolves who the caller is inside a condominium. Every condominium-scoped route goes
through `require_permission`, and every service query filters by `ctx.condominium_id`."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.errors import Forbidden, NotFound
from app.db.session import get_db
from app.models import Condominium, Organization, OrganizationMembership, StaffMembership, User
from app.models.enums import OrgRole
from app.rbac.permissions import ORG_LEVEL_ROLES, ROLE_PERMISSIONS, Permission, Role


@dataclass(frozen=True)
class CondoContext:
    user: User
    condominium: Condominium
    role: Role

    @property
    def condominium_id(self) -> uuid.UUID:
        return self.condominium.id

    @property
    def organization_id(self) -> uuid.UUID:
        return self.condominium.organization_id

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]

    @property
    def is_org_level(self) -> bool:
        return self.role in ORG_LEVEL_ROLES

    def require(self, permission: Permission) -> None:
        if permission not in self.permissions:
            raise Forbidden(f"Missing permission: {permission}")


@dataclass(frozen=True)
class OrgContext:
    user: User
    organization: Organization
    role: OrgRole


def resolve_condo_role(db: Session, user: User, condominium: Condominium) -> Role | None:
    org_role = db.scalar(
        select(OrganizationMembership.role).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == condominium.organization_id,
            OrganizationMembership.revoked_at.is_(None),
        )
    )
    if org_role is not None:
        return Role(f"org_{org_role.value}")
    staff_role = db.scalar(
        select(StaffMembership.role).where(
            StaffMembership.user_id == user.id,
            StaffMembership.condominium_id == condominium.id,
            StaffMembership.revoked_at.is_(None),
        )
    )
    return Role(staff_role.value) if staff_role is not None else None


def get_condo_context(
    condominium_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CondoContext:
    condominium = db.get(Condominium, condominium_id)
    role = resolve_condo_role(db, user, condominium) if condominium else None
    if condominium is None or role is None:
        # Same response whether it doesn't exist or isn't yours: no tenant enumeration.
        raise NotFound("Condominium not found")
    return CondoContext(user=user, condominium=condominium, role=role)


def require_permission(permission: Permission) -> Callable[..., CondoContext]:
    def dependency(ctx: CondoContext = Depends(get_condo_context)) -> CondoContext:
        ctx.require(permission)
        return ctx

    return dependency


def get_org_admin_context(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    row = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            Organization.id == organization_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.revoked_at.is_(None),
        )
    ).first()
    if row is None:
        raise NotFound("Organization not found")
    return OrgContext(user=user, organization=row[0], role=row[1])
