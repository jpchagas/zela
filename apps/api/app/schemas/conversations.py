import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ConversationStatus, DeliveryStatus, MessageDirection, MessageKind
from app.schemas.common import ORMModel


class ConversationSummary(BaseModel):
    id: uuid.UUID
    contact_e164: str
    resident_id: uuid.UUID | None
    resident_name: str | None
    status: ConversationStatus
    escalation_reason: str | None
    escalated_at: datetime | None
    last_message_at: datetime | None
    last_message_preview: str | None


class MessageOut(ORMModel):
    id: uuid.UUID
    direction: MessageDirection
    kind: MessageKind
    body: str | None
    delivery_status: DeliveryStatus | None
    delivery_error: str | None
    sent_by_user_id: uuid.UUID | None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    can_reply: bool
    reply_window_ends_at: datetime | None
    messages: list[MessageOut]


class StaffReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    # Set by the client per submit, so a double-click or retry doesn't send twice.
    client_message_id: str = Field(min_length=8, max_length=64)
