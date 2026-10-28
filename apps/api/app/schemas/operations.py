import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    ActorType,
    DocumentStatus,
    DocumentVisibility,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.schemas.common import ORMModel


class DocumentOut(ORMModel):
    id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    visibility: DocumentVisibility
    status: DocumentStatus
    error: str | None
    chunk_count: int
    indexed_at: datetime | None
    replaces_document_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    created_at: datetime


class DocumentSearchHit(BaseModel):
    document_id: uuid.UUID
    citation: str
    section: str | None
    excerpt: str


class TicketSummary(BaseModel):
    id: uuid.UUID
    number: int
    title: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    ai_suggested_priority: TicketPriority | None
    ai_suggested_category: TicketCategory | None
    unit_label: str | None
    location: str | None
    reporter_name: str | None
    assignee_email: str | None
    created_at: datetime
    resolved_at: datetime | None


class TicketEventOut(ORMModel):
    id: uuid.UUID
    event_type: str
    from_status: TicketStatus | None
    to_status: TicketStatus | None
    note: str | None
    is_internal: bool
    actor_type: ActorType
    actor_id: uuid.UUID | None
    created_at: datetime


class TicketDetail(TicketSummary):
    description: str
    reporter_resident_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    assignee_user_id: uuid.UUID | None
    closed_at: datetime | None
    allowed_transitions: list[TicketStatus]
    events: list[TicketEventOut]


class TicketStatusChange(BaseModel):
    status: TicketStatus
    note: str | None = Field(default=None, max_length=1000)


class TicketNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    public: bool = Field(
        default=False, description="Public notes are sent to the resident on WhatsApp."
    )


class TicketAssign(BaseModel):
    user_id: uuid.UUID | None


class TicketReclassify(BaseModel):
    category: TicketCategory | None = None
    priority: TicketPriority | None = None


class EmergencyContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=80)
    phone: str = Field(min_length=8, max_length=30)


class EmergencyContactOut(ORMModel):
    id: uuid.UUID
    name: str
    role: str | None
    phone_e164: str
    created_at: datetime
