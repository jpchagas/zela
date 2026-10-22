import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import (
    ActorType,
    TicketPriority,
    TicketStatus,
    VisitorAuthorizationStatus,
    db_enum,
)


class CondominiumCounter(Base):
    """Per-condominium sequences for human-friendly references (e.g. ticket #42).
    Incremented with UPDATE ... RETURNING so concurrent requests never share a number."""

    __tablename__ = "condominium_counters"

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(default=0)


class MaintenanceTicket(IdMixin, TimestampMixin, Base):
    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        UniqueConstraint("condominium_id", "number"),
        UniqueConstraint("condominium_id", "idempotency_key"),
        UniqueConstraint("condominium_id", "id"),
        ForeignKeyConstraint(["condominium_id", "unit_id"], ["units.condominium_id", "units.id"]),
        ForeignKeyConstraint(
            ["condominium_id", "reporter_resident_id"],
            ["residents.condominium_id", "residents.id"],
        ),
        Index("ix_maintenance_tickets_condo_status", "condominium_id", "status"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column()
    unit_id: Mapped[uuid.UUID | None] = mapped_column()
    reporter_resident_id: Mapped[uuid.UUID | None] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    # Confirmed values, set by deterministic validation or a human.
    category: Mapped[str | None] = mapped_column(String(60))
    priority: Mapped[TicketPriority] = mapped_column(
        db_enum(TicketPriority), default=TicketPriority.NORMAL
    )
    # What the model proposed, kept separate so the UI can label it as a suggestion.
    ai_suggested_category: Mapped[str | None] = mapped_column(String(60))
    ai_suggested_priority: Mapped[TicketPriority | None] = mapped_column(
        db_enum(TicketPriority, name="ai_suggested_priority")
    )
    status: Mapped[TicketStatus] = mapped_column(db_enum(TicketStatus), default=TicketStatus.OPEN)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketEvent(IdMixin, Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["condominium_id", "ticket_id"],
            ["maintenance_tickets.condominium_id", "maintenance_tickets.id"],
            ondelete="CASCADE",
        ),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[TicketStatus | None] = mapped_column(
        db_enum(TicketStatus, name="from_status")
    )
    to_status: Mapped[TicketStatus | None] = mapped_column(db_enum(TicketStatus, name="to_status"))
    note: Mapped[str | None] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_type: Mapped[ActorType] = mapped_column(db_enum(ActorType))
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisitorAuthorization(IdMixin, TimestampMixin, Base):
    """A recorded authorization. Staff verify it against this table; a chat message
    alone never grants access."""

    __tablename__ = "visitor_authorizations"
    __table_args__ = (
        UniqueConstraint("condominium_id", "number"),
        UniqueConstraint("condominium_id", "idempotency_key"),
        ForeignKeyConstraint(["condominium_id", "unit_id"], ["units.condominium_id", "units.id"]),
        ForeignKeyConstraint(
            ["condominium_id", "resident_id"], ["residents.condominium_id", "residents.id"]
        ),
        CheckConstraint("expires_at > valid_from", name="valid_window"),
        Index("ix_visitor_authorizations_condo_valid", "condominium_id", "valid_from"),
    )

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column()
    unit_id: Mapped[uuid.UUID] = mapped_column()
    resident_id: Mapped[uuid.UUID] = mapped_column()
    visitor_name: Mapped[str] = mapped_column(String(200))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[VisitorAuthorizationStatus] = mapped_column(
        db_enum(VisitorAuthorizationStatus), default=VisitorAuthorizationStatus.ACTIVE
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
