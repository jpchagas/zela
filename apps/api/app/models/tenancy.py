import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    """A customer account: a single condominium's administration or a management company."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)


class Condominium(IdMixin, TimestampMixin, Base):
    __tablename__ = "condominiums"
    __table_args__ = (UniqueConstraint("organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    address_line: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(9))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    # Meta's phone_number_id for the condominium's WhatsApp sender. Routes inbound
    # webhooks to a tenant. Access tokens live in Secret Manager, not here.
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(64), unique=True)


class Building(IdMixin, TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("condominium_id", "name"),
        UniqueConstraint("condominium_id", "id"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))


class Unit(IdMixin, TimestampMixin, Base):
    __tablename__ = "units"
    __table_args__ = (
        # The composite FK guarantees a unit's building is in the same condominium.
        ForeignKeyConstraint(
            ["condominium_id", "building_id"],
            ["buildings.condominium_id", "buildings.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "condominium_id", "building_id", "identifier", postgresql_nulls_not_distinct=True
        ),
        UniqueConstraint("condominium_id", "id"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column()
    identifier: Mapped[str] = mapped_column(String(40))
    floor: Mapped[str | None] = mapped_column(String(10))


class EmergencyContact(IdMixin, TimestampMixin, Base):
    """On-call people alerted on WhatsApp when a resident reports an emergency."""

    __tablename__ = "emergency_contacts"
    __table_args__ = (UniqueConstraint("condominium_id", "phone_e164"),)

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str | None] = mapped_column(String(80))
    phone_e164: Mapped[str] = mapped_column(String(20))
