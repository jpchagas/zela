import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import (
    ConversationStatus,
    DeliveryStatus,
    JobStatus,
    MessageDirection,
    MessageKind,
    db_enum,
)


class WebhookEvent(IdMixin, Base):
    """Idempotency ledger for inbound provider events. A duplicate delivery hits the
    unique constraint and is acknowledged without being processed twice."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    provider: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[JobStatus] = mapped_column(db_enum(JobStatus), default=JobStatus.RECEIVED)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_condo_last", "condominium_id", "last_message_at"),)

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    # Null until the sender is enrolled and matched to a resident.
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("residents.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    contact_e164: Mapped[str] = mapped_column(String(20))
    status: Mapped[ConversationStatus] = mapped_column(
        db_enum(ConversationStatus), default=ConversationStatus.ACTIVE
    )
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(IdMixin, Base):
    __tablename__ = "messages"

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(db_enum(MessageDirection))
    kind: Mapped[MessageKind] = mapped_column(db_enum(MessageKind))
    # Nullable so retention jobs can redact content while keeping the record.
    body: Mapped[str | None] = mapped_column(Text)
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    delivery_status: Mapped[DeliveryStatus | None] = mapped_column(db_enum(DeliveryStatus))
    redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationEvent(IdMixin, TimestampMixin, Base):
    """An outbound operational notification and its delivery lifecycle."""

    __tablename__ = "notification_events"
    __table_args__ = (UniqueConstraint("condominium_id", "idempotency_key"),)

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("residents.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    template: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[DeliveryStatus] = mapped_column(
        db_enum(DeliveryStatus), default=DeliveryStatus.PENDING
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
