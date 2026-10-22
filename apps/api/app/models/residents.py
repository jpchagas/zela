import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ResidentStatus, UnitRelationship, db_enum


class Resident(IdMixin, TimestampMixin, Base):
    """A person living in or responsible for units of one condominium.

    Residents are scoped to a single condominium (see ADR 0003). Someone with units in two
    condominiums has two records, which keeps one condominium's data out of the other's view.
    """

    __tablename__ = "residents"
    __table_args__ = (UniqueConstraint("condominium_id", "id"),)

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[ResidentStatus] = mapped_column(
        db_enum(ResidentStatus), default=ResidentStatus.INVITED
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResidentPhone(IdMixin, TimestampMixin, Base):
    __tablename__ = "resident_phones"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "resident_id"],
            ["residents.condominium_id", "residents.id"],
            ondelete="CASCADE",
        ),
        # One number identifies at most one resident within a condominium.
        UniqueConstraint("condominium_id", "phone_e164"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    resident_id: Mapped[uuid.UUID] = mapped_column(index=True)
    phone_e164: Mapped[str] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set by the WhatsApp enrollment flow (Milestone 2). A bare number match is not
    # enough for sensitive operations.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UnitMembership(IdMixin, TimestampMixin, Base):
    __tablename__ = "unit_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "unit_id"],
            ["units.condominium_id", "units.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["condominium_id", "resident_id"],
            ["residents.condominium_id", "residents.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_unit_memberships_active",
            "unit_id",
            "resident_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(index=True)
    relationship: Mapped[UnitRelationship] = mapped_column(db_enum(UnitRelationship))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnrollmentCode(IdMixin, TimestampMixin, Base):
    """One-time code that proves a WhatsApp sender is the resident a manager registered.

    Bound to one registered phone: enrollment needs both the matching sender number and the
    code. Only an HMAC of the code is stored (see app.services.enrollment).
    """

    __tablename__ = "enrollment_codes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "resident_id"],
            ["residents.condominium_id", "residents.id"],
            ondelete="CASCADE",
        ),
        Index(
            "uq_enrollment_codes_pending",
            "phone_id",
            unique=True,
            postgresql_where=text("used_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    resident_id: Mapped[uuid.UUID] = mapped_column(index=True)
    phone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resident_phones.id", ondelete="CASCADE")
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
