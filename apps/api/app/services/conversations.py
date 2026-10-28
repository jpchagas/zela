"""WhatsApp conversations: inbound/outbound message records, delivery status, escalation,
and the dashboard's view of them."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.integrations.whatsapp.sender import SendError, WhatsAppSender
from app.integrations.whatsapp.templates import Template
from app.models import Condominium, Conversation, Message, NotificationEvent, Resident
from app.models.enums import (
    ActorType,
    ConversationStatus,
    DeliveryStatus,
    MessageDirection,
    MessageKind,
)
from app.rbac.context import CondoContext
from app.services import audit
from app.services.common import get_scoped

SERVICE_WINDOW = timedelta(hours=24)

# Status webhooks can arrive out of order; only move forward.
_DELIVERY_RANK = {
    DeliveryStatus.PENDING: 0,
    DeliveryStatus.SENT: 1,
    DeliveryStatus.DELIVERED: 2,
    DeliveryStatus.READ: 3,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def open_conversation(db: Session, condominium_id: uuid.UUID, contact_e164: str) -> Conversation:
    """Return the contact's open conversation, creating it if needed (race-safe)."""
    db.execute(
        insert(Conversation)
        .values(
            id=uuid.uuid4(),
            condominium_id=condominium_id,
            contact_e164=contact_e164,
            status=ConversationStatus.ACTIVE,
            channel="whatsapp",
        )
        .on_conflict_do_nothing(
            index_elements=["condominium_id", "contact_e164"],
            index_where=text("status <> 'closed'"),
        )
    )
    return db.scalars(
        select(Conversation).where(
            Conversation.condominium_id == condominium_id,
            Conversation.contact_e164 == contact_e164,
            Conversation.status != ConversationStatus.CLOSED,
        )
    ).one()


def record_inbound(
    db: Session, conversation: Conversation, *, provider_message_id: str, body: str
) -> Message:
    """Store an inbound message once; a redelivery returns the existing row."""
    now = _now()
    db.execute(
        insert(Message)
        .values(
            id=uuid.uuid4(),
            condominium_id=conversation.condominium_id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            kind=MessageKind.RESIDENT,
            body=body,
            provider_message_id=provider_message_id,
        )
        .on_conflict_do_nothing(index_elements=["provider_message_id"])
    )
    conversation.last_inbound_at = now
    conversation.last_message_at = now
    db.commit()
    return db.scalars(
        select(Message).where(Message.provider_message_id == provider_message_id)
    ).one()


def send_outbound(
    db: Session,
    sender: WhatsAppSender,
    condominium: Condominium,
    conversation: Conversation,
    *,
    kind: MessageKind,
    body: str,
    idempotency_key: str,
    sent_by_user_id: uuid.UUID | None = None,
    template: Template | None = None,
    template_params: dict[str, str] | None = None,
) -> Message:
    """Persist the message, then send it, then record the outcome.

    With `template`, it goes out as that approved template (needed outside the 24h window);
    `body` should then be the template rendered with `template_params`.

    The row is committed before sending so nothing is sent unrecorded. A retry with the
    same key resends only a message still pending (at-least-once); one already sent or
    failed is returned as is.
    """
    message = db.scalar(select(Message).where(Message.idempotency_key == idempotency_key))
    if message is None:
        message = Message(
            condominium_id=condominium.id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            kind=kind,
            body=body,
            sent_by_user_id=sent_by_user_id,
            idempotency_key=idempotency_key,
            delivery_status=DeliveryStatus.PENDING,
        )
        db.add(message)
        conversation.last_message_at = _now()
        db.commit()
    if message.delivery_status != DeliveryStatus.PENDING:
        return message

    if not condominium.whatsapp_phone_number_id:
        message.delivery_status = DeliveryStatus.FAILED
        message.delivery_error = "WhatsApp is not configured for this condominium"
    else:
        try:
            if template is not None:
                message.provider_message_id = sender.send_template(
                    condominium.whatsapp_phone_number_id,
                    conversation.contact_e164,
                    template.name,
                    template.language,
                    template.values(template_params or {}),
                )
            else:
                message.provider_message_id = sender.send_text(
                    condominium.whatsapp_phone_number_id, conversation.contact_e164, message.body
                )
            message.delivery_status = DeliveryStatus.SENT
        except SendError as exc:
            message.delivery_status = DeliveryStatus.FAILED
            message.delivery_error = str(exc)[:1000]
    db.commit()
    return message


def apply_delivery_status(
    db: Session, provider_message_id: str, status: str, error: str | None = None
) -> bool:
    """Apply a provider status callback. Returns False if the message is unknown."""
    message = db.scalar(select(Message).where(Message.provider_message_id == provider_message_id))
    if message is None:
        return False
    try:
        new = DeliveryStatus(status)
    except ValueError:
        return True  # statuses we don't track (e.g. "deleted")
    current = message.delivery_status or DeliveryStatus.PENDING
    if new == DeliveryStatus.FAILED:
        if _DELIVERY_RANK.get(current, 0) < _DELIVERY_RANK[DeliveryStatus.DELIVERED]:
            message.delivery_status = new
            message.delivery_error = (error or "failed")[:1000]
    elif current == DeliveryStatus.FAILED or _DELIVERY_RANK[new] > _DELIVERY_RANK.get(current, 0):
        message.delivery_status = new
    # A notification's status mirrors the message it was delivered as.
    db.execute(
        update(NotificationEvent)
        .where(NotificationEvent.message_id == message.id)
        .values(status=message.delivery_status, error=message.delivery_error)
    )
    db.commit()
    return True


def escalate(
    db: Session,
    condominium: Condominium,
    conversation: Conversation,
    *,
    reason: str,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
) -> None:
    if conversation.status != ConversationStatus.ESCALATED:
        conversation.status = ConversationStatus.ESCALATED
        conversation.escalated_at = _now()
    conversation.escalation_reason = reason[:1000]
    audit.record(
        db,
        organization_id=condominium.organization_id,
        condominium_id=condominium.id,
        actor_type=actor_type,
        actor_id=actor_id,
        action="conversation.escalated",
        entity_type="conversation",
        entity_id=conversation.id,
    )
    db.commit()


def in_service_window(conversation: Conversation, now: datetime | None = None) -> bool:
    last = conversation.last_inbound_at
    return last is not None and (now or _now()) - last < SERVICE_WINDOW


# --- Dashboard ---------------------------------------------------------------------------


@dataclass
class ConversationRow:
    conversation: Conversation
    resident_name: str | None
    last_message_preview: str | None


def list_conversations(
    db: Session,
    ctx: CondoContext,
    *,
    status: ConversationStatus | None,
    limit: int,
    offset: int,
) -> list[ConversationRow]:
    last_body = (
        select(Message.body)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    stmt = (
        select(Conversation, Resident.full_name, last_body)
        .outerjoin(Resident, Resident.id == Conversation.resident_id)
        .where(Conversation.condominium_id == ctx.condominium_id)
    )
    if status is not None:
        stmt = stmt.where(Conversation.status == status)
    stmt = (
        stmt.order_by(Conversation.last_message_at.desc().nulls_last()).limit(limit).offset(offset)
    )
    return [
        ConversationRow(c, name, (body or "")[:140] or None) for c, name, body in db.execute(stmt)
    ]


def get_with_messages(
    db: Session, ctx: CondoContext, conversation_id: uuid.UUID, *, limit: int = 200
) -> tuple[Conversation, str | None, list[Message]]:
    conversation = get_scoped(db, Conversation, ctx, conversation_id)
    resident_name = (
        db.scalar(select(Resident.full_name).where(Resident.id == conversation.resident_id))
        if conversation.resident_id
        else None
    )
    recent = (
        select(Message)
        .where(
            Message.condominium_id == ctx.condominium_id, Message.conversation_id == conversation.id
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
        .subquery()
    )
    messages = db.scalars(
        select(Message).join(recent, recent.c.id == Message.id).order_by(Message.created_at)
    ).all()
    return conversation, resident_name, list(messages)


def staff_reply(
    db: Session,
    ctx: CondoContext,
    sender: WhatsAppSender,
    conversation_id: uuid.UUID,
    body: str,
    idempotency_key: str,
) -> Message:
    conversation = get_scoped(db, Conversation, ctx, conversation_id)
    if conversation.status == ConversationStatus.CLOSED:
        raise Conflict("Conversation is closed")
    if not in_service_window(conversation):
        # Outside 24h WhatsApp only allows approved templates (arrives with notifications).
        raise Conflict("Outside WhatsApp's 24-hour reply window; the resident must write first")
    message = send_outbound(
        db,
        sender,
        ctx.condominium,
        conversation,
        kind=MessageKind.STAFF_REPLY,
        body=body,
        idempotency_key=f"staff:{ctx.user.id}:{idempotency_key}",
        sent_by_user_id=ctx.user.id,
    )
    audit.record_user_action(
        db,
        ctx,
        "conversation.staff_replied",
        "conversation",
        conversation.id,
        delivery_status=message.delivery_status.value if message.delivery_status else None,
    )
    db.commit()
    return message


def hand_back_to_assistant(
    db: Session, ctx: CondoContext, conversation_id: uuid.UUID
) -> Conversation:
    conversation = get_scoped(db, Conversation, ctx, conversation_id)
    if conversation.status != ConversationStatus.ESCALATED:
        raise Conflict("Conversation is not escalated")
    conversation.status = ConversationStatus.ACTIVE
    conversation.escalation_reason = None
    conversation.escalated_at = None
    audit.record_user_action(
        db, ctx, "conversation.returned_to_assistant", "conversation", conversation.id
    )
    db.commit()
    return conversation


def count_escalated(db: Session, condominium_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.condominium_id == condominium_id,
                Conversation.status == ConversationStatus.ESCALATED,
            )
        )
        or 0
    )
