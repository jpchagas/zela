import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.whatsapp.sender import WhatsAppSender, get_whatsapp_sender
from app.models.enums import ConversationStatus
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.common import Page
from app.schemas.conversations import (
    ConversationDetail,
    ConversationSummary,
    MessageOut,
    StaffReplyIn,
)
from app.services import conversations

router = APIRouter(prefix="/condominiums/{condominium_id}/conversations", tags=["conversations"])

can_read = require_permission(Permission.CONVERSATIONS_READ)
can_reply = require_permission(Permission.CONVERSATIONS_REPLY)


def _summary(c, resident_name, preview) -> dict:
    return {
        "id": c.id,
        "contact_e164": c.contact_e164,
        "resident_id": c.resident_id,
        "resident_name": resident_name,
        "status": c.status,
        "escalation_reason": c.escalation_reason,
        "escalated_at": c.escalated_at,
        "last_message_at": c.last_message_at,
        "last_message_preview": preview,
    }


@router.get("", response_model=Page[ConversationSummary])
def list_conversations(
    status_: ConversationStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CondoContext = Depends(can_read),
    db: Session = Depends(get_db),
):
    rows = conversations.list_conversations(db, ctx, status=status_, limit=limit, offset=offset)
    items = [
        ConversationSummary(**_summary(r.conversation, r.resident_name, r.last_message_preview))
        for r in rows
    ]
    return Page(items=items, limit=limit, offset=offset)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    ctx: CondoContext = Depends(can_read),
    db: Session = Depends(get_db),
):
    conv, resident_name, messages = conversations.get_with_messages(db, ctx, conversation_id)
    window_open = conversations.in_service_window(conv)
    return ConversationDetail(
        **_summary(conv, resident_name, None),
        can_reply=window_open and conv.status != ConversationStatus.CLOSED,
        reply_window_ends_at=(
            conv.last_inbound_at + conversations.SERVICE_WINDOW if conv.last_inbound_at else None
        ),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.post(
    "/{conversation_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED
)
def reply(
    conversation_id: uuid.UUID,
    body: StaffReplyIn,
    ctx: CondoContext = Depends(can_reply),
    db: Session = Depends(get_db),
    sender: WhatsAppSender = Depends(get_whatsapp_sender),
):
    return conversations.staff_reply(
        db, ctx, sender, conversation_id, body.body, body.client_message_id
    )


@router.post("/{conversation_id}/return-to-assistant", response_model=ConversationSummary)
def return_to_assistant(
    conversation_id: uuid.UUID,
    ctx: CondoContext = Depends(can_reply),
    db: Session = Depends(get_db),
):
    conv = conversations.hand_back_to_assistant(db, ctx, conversation_id)
    return ConversationSummary(**_summary(conv, None, None))
