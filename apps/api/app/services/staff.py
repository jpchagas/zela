import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound
from app.models import StaffMembership, User
from app.models.enums import StaffRole
from app.rbac.context import CondoContext
from app.schemas.tenancy import StaffInvite, StaffMemberOut
from app.services import audit


def list_members(db: Session, ctx: CondoContext) -> list[StaffMemberOut]:
    rows = db.execute(
        select(StaffMembership, User)
        .join(User, User.id == StaffMembership.user_id)
        .where(
            StaffMembership.condominium_id == ctx.condominium_id,
            StaffMembership.revoked_at.is_(None),
        )
        .order_by(func.lower(User.email))
    ).all()
    return [_to_out(m, u) for m, u in rows]


def invite(db: Session, ctx: CondoContext, data: StaffInvite) -> StaffMemberOut:
    role = StaffRole(data.role)
    # Managers run one condominium; only organization admins may appoint them.
    if role == StaffRole.MANAGER and not ctx.is_org_level:
        raise Forbidden("Only organization admins can add managers")

    email = data.email.lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(email=email, display_name=data.display_name)
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(StaffMembership).where(
            StaffMembership.user_id == user.id,
            StaffMembership.condominium_id == ctx.condominium_id,
        )
    )
    if membership is not None and membership.revoked_at is None:
        raise Conflict("This person is already a staff member of this condominium")
    if membership is None:
        membership = StaffMembership(user_id=user.id, condominium_id=ctx.condominium_id, role=role)
        db.add(membership)
    else:
        membership.role = role
        membership.revoked_at = None
    db.flush()

    audit.record_user_action(
        db, ctx, "staff.invited", "staff_membership", membership.id, role=role.value
    )
    db.commit()
    return _to_out(membership, user)


def revoke(db: Session, ctx: CondoContext, membership_id: uuid.UUID) -> None:
    membership = db.scalar(
        select(StaffMembership).where(
            StaffMembership.id == membership_id,
            StaffMembership.condominium_id == ctx.condominium_id,
            StaffMembership.revoked_at.is_(None),
        )
    )
    if membership is None:
        raise NotFound("Staff membership not found")
    if membership.role == StaffRole.MANAGER and not ctx.is_org_level:
        raise Forbidden("Only organization admins can remove managers")
    membership.revoked_at = datetime.now(timezone.utc)
    audit.record_user_action(db, ctx, "staff.revoked", "staff_membership", membership.id)
    db.commit()


def _to_out(membership: StaffMembership, user: User) -> StaffMemberOut:
    return StaffMemberOut(
        membership_id=membership.id,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role.value,
        has_signed_in=user.firebase_uid is not None,
        created_at=membership.created_at,
    )
