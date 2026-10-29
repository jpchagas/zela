"""Operational notifications on WhatsApp (tickets, emergencies).

Enqueue writes a `notification_events` row in the caller's committed state and publishes
its ID; the worker sends it later. Before sending, the worker re-checks the guard against
the database, so a notification never announces a state that is no longer true.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher
from app.integrations.whatsapp.sender import WhatsAppSender
from app.integrations.whatsapp.templates import TEMPLATES
from app.models import Condominium, MaintenanceTicket, NotificationEvent
from app.models.enums import DeliveryStatus, MessageKind
from app.services import conversations

NOTIFICATION_TOPIC = "notification-send"


def enqueue(
    db: Session,
    publisher: JobPublisher,
    *,
    condominium_id: uuid.UUID,
    recipient_e164: str,
    template: str,
    params: dict[str, str],
    idempotency_key: str,
    resident_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    guard: dict[str, Any] | None = None,
) -> uuid.UUID | None:
    """Record a notification and queue it. Returns None if the key was already used."""
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template {template}")
    notification_id = db.scalar(
        insert(NotificationEvent)
        .values(
            id=uuid.uuid4(),
            condominium_id=condominium_id,
            resident_id=resident_id,
            recipient_e164=recipient_e164,
            template=template,
            entity_type=entity_type,
            entity_id=entity_id,
            idempotency_key=idempotency_key,
            status=DeliveryStatus.PENDING,
            attempts=0,
            data={"params": params, "guard": guard or {}},
        )
        .on_conflict_do_nothing(index_elements=["condominium_id", "idempotency_key"])
        .returning(NotificationEvent.id)
    )
    db.commit()
    if notification_id is not None:
        publisher.publish(NOTIFICATION_TOPIC, {"notification_id": str(notification_id)})
    return notification_id


def deliver(db: Session, notification_id: uuid.UUID, sender: WhatsAppSender) -> None:
    notification = db.get(NotificationEvent, notification_id)
    if notification is None or notification.status != DeliveryStatus.PENDING:
        return
    notification.attempts += 1
    db.commit()

    if not _guard_holds(db, notification):
        notification.status = DeliveryStatus.SKIPPED
        notification.error = "superseded: the record changed before this was sent"
        db.commit()
        return

    condominium = db.get(Condominium, notification.condominium_id)
    template = TEMPLATES[notification.template]
    params = notification.data["params"]
    conversation = conversations.open_conversation(db, condominium.id, notification.recipient_e164)
    in_window = conversations.in_service_window(conversation)
    message = conversations.send_outbound(
        db,
        sender,
        condominium,
        conversation,
        kind=MessageKind.NOTIFICATION,
        body=template.render(params),
        idempotency_key=f"notification:{notification.id}",
        template=None if in_window else template,
        template_params=params,
    )
    notification.message_id = message.id
    notification.provider_message_id = message.provider_message_id
    notification.status = message.delivery_status
    notification.error = message.delivery_error
    db.commit()


def _guard_holds(db: Session, notification: NotificationEvent) -> bool:
    guard = notification.data.get("guard") or {}
    pending_phone = guard.get("manager_phone_pending")
    if pending_phone is not None:
        condo = db.get(Condominium, notification.condominium_id)
        return (
            condo.manager_phone_e164 == pending_phone and condo.manager_phone_confirmed_at is None
        )
    expected = guard.get("ticket_status")
    if expected is None:
        return True
    status = db.scalar(
        select(MaintenanceTicket.status).where(MaintenanceTicket.id == notification.entity_id)
    )
    return status is not None and status.value == expected
