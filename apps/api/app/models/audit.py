import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin
from app.models.enums import ActorType, AgentRunStatus, db_enum


class AuditEvent(IdMixin, Base):
    """Append-only record of security-sensitive and operational changes.

    `data` holds identifiers and the names of changed fields, not personal data values.
    """

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_condo_created", "condominium_id", "created_at"),)

    # Both null for platform-level events such as a user's first sign-in.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    condominium_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE")
    )
    actor_type: Mapped[ActorType] = mapped_column(db_enum(ActorType))
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(IdMixin, Base):
    """One agent execution for an inbound message, including every tool call and its outcome."""

    __tablename__ = "agent_runs"

    condominium_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominiums.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    # One run per inbound message: a redelivered job finds the existing run instead of
    # calling the model (and the tools) again.
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), unique=True
    )
    agent: Mapped[str] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[AgentRunStatus] = mapped_column(db_enum(AgentRunStatus))
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list)
    input_tokens: Mapped[int | None] = mapped_column()
    output_tokens: Mapped[int | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    # The reply the run produced, so a redelivered job can send it without re-running.
    reply_text: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
