import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import OrgRole, StaffRole, db_enum


class User(IdMixin, TimestampMixin, Base):
    """A dashboard identity (manager, staff, org admin). Residents are not users."""

    __tablename__ = "users"

    # Null until the invited person signs in for the first time with a verified email.
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    # Platform admins operate the SaaS; this flag grants no tenant data access by itself.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationMembership(IdMixin, TimestampMixin, Base):
    """Grants a user admin rights over every condominium in an organization."""

    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(db_enum(OrgRole))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffMembership(IdMixin, TimestampMixin, Base):
    """Grants a user a role in one condominium."""

    __tablename__ = "staff_memberships"
    __table_args__ = (UniqueConstraint("user_id", "condominium_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[StaffRole] = mapped_column(db_enum(StaffRole))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
