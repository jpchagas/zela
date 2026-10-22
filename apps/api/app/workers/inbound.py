"""Processes one recorded WhatsApp webhook event (ADR 0004).

Safe to run more than once for the same event: the inbound message, the agent run and
the reply are each keyed so a redelivery finds the existing row instead of acting again.
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.concierge import run_concierge
from app.integrations.whatsapp.sender import WhatsAppSender
from app.llm.base import LLMClient
from app.models import Condominium, Conversation, Message, Resident, WebhookEvent
from app.models.enums import ConversationStatus, JobStatus, MessageKind, ResidentStatus
from app.services import conversations, enrollment
from app.services.enrollment import EnrollmentResult

logger = logging.getLogger(__name__)

ASK_FOR_CODE = (
    "Para ativar seu acesso, envie aqui o código de ativação que você recebeu da "
    "administração (por exemplo: ABCD-2345)."
)
UNKNOWN_NUMBER = (
    "Olá! Este é o canal do {condo} no WhatsApp. Não encontrei um cadastro para este número. "
    "Peça à administração do condomínio para cadastrar seu telefone e enviar um código de ativação."
)
WRONG_CODE = "Esse código não confere. Confira e envie novamente."
CODE_UNUSABLE = "Esse código não é mais válido. Peça um novo código à administração."
ACCESS_SUSPENDED = "Seu acesso pelo WhatsApp está suspenso. Fale com a administração do condomínio."
ENROLLED = (
    "Pronto, {name}! Seu WhatsApp está ativado no {condo}. Pode me mandar sua dúvida ou "
    "pedido por aqui, e se precisar, eu chamo a equipe."
)
TEXT_ONLY = "Por enquanto só consigo ler mensagens de texto. Pode escrever o que precisa?"


class UnroutableEvent(Exception):
    """The event can't be processed and retrying won't help."""


def process_webhook_event(
    db: Session, event_id: uuid.UUID, *, llm: LLMClient, sender: WhatsAppSender
) -> None:
    event = db.get(WebhookEvent, event_id)
    if event is None or event.status == JobStatus.PROCESSED:
        return
    event.attempts += 1
    db.commit()
    try:
        if event.event_type == "status":
            _handle_status(db, event.payload)
        elif event.event_type == "message":
            _handle_message(db, event.payload, llm=llm, sender=sender)
        event.status = JobStatus.PROCESSED
        event.processed_at = datetime.now(timezone.utc)
        event.error = None
        db.commit()
    except UnroutableEvent as exc:
        db.rollback()
        _mark_failed(db, event_id, str(exc))
    except Exception as exc:
        db.rollback()
        _mark_failed(db, event_id, f"{type(exc).__name__}: {exc}")
        raise  # let the queue redeliver


def _mark_failed(db: Session, event_id: uuid.UUID, error: str) -> None:
    event = db.get(WebhookEvent, event_id)
    event.status = JobStatus.FAILED
    event.error = error[:1000]
    db.commit()


def _handle_status(db: Session, payload: dict) -> None:
    status = payload["status"]
    errors = status.get("errors") or []
    error = errors[0].get("title") if errors else None
    if not conversations.apply_delivery_status(db, status["id"], status["status"], error):
        logger.info("status for unknown message", extra={"status": status["status"]})


@contextmanager
def _conversation_lock(db: Session, condominium_id: uuid.UUID, contact: str) -> Iterator[None]:
    """Serialize work per contact across workers. Session-level, so it survives the
    commits made while the conversation is processed."""
    key = db.scalar(select(func.hashtextextended(f"conv:{condominium_id}:{contact}", 0)))
    db.execute(select(func.pg_advisory_lock(key)))
    try:
        yield
    finally:
        db.rollback()
        db.execute(select(func.pg_advisory_unlock(key)))
        db.commit()


def _handle_message(db: Session, payload: dict, *, llm: LLMClient, sender: WhatsAppSender) -> None:
    message = payload["message"]
    condominium = db.scalar(
        select(Condominium).where(
            Condominium.whatsapp_phone_number_id == payload.get("phone_number_id")
        )
    )
    if condominium is None:
        raise UnroutableEvent("No condominium uses this WhatsApp phone_number_id")
    contact = "+" + "".join(ch for ch in str(message.get("from", "")) if ch.isdigit())
    if len(contact) < 9:
        raise UnroutableEvent("Missing or invalid sender number")

    with _conversation_lock(db, condominium.id, contact):
        conversation = conversations.open_conversation(db, condominium.id, contact)
        text = (message.get("text") or {}).get("body") if message.get("type") == "text" else None
        inbound = conversations.record_inbound(
            db,
            conversation,
            provider_message_id=message["id"],
            body=text if text is not None else f"[{message.get('type', 'desconhecido')}]",
        )
        kind, reply = _decide_reply(db, llm, condominium, conversation, inbound, contact, text)
        if reply:
            conversations.send_outbound(
                db,
                sender,
                condominium,
                conversation,
                kind=kind,
                body=reply,
                idempotency_key=f"reply:{inbound.id}",
            )


def _decide_reply(
    db: Session,
    llm: LLMClient,
    condominium: Condominium,
    conversation: Conversation,
    inbound: Message,
    contact: str,
    text: str | None,
) -> tuple[MessageKind, str | None]:
    system = MessageKind.SYSTEM_REPLY
    if conversation.status == ConversationStatus.ESCALATED:
        return system, None  # staff own the conversation; they see it in the dashboard

    phone = enrollment.find_phone(db, condominium.id, contact)
    if phone is None:
        return system, UNKNOWN_NUMBER.format(condo=condominium.name)
    resident = db.get(Resident, phone.resident_id)
    if resident.status in (ResidentStatus.SUSPENDED, ResidentStatus.REVOKED):
        return system, ACCESS_SUSPENDED
    if conversation.resident_id != resident.id and phone.verified_at is not None:
        conversation.resident_id = resident.id
        db.commit()

    if phone.verified_at is None:
        if text is None:
            return system, ASK_FOR_CODE
        result = enrollment.try_enroll(db, condominium, phone, text)
        if result == EnrollmentResult.ENROLLED:
            conversation.resident_id = resident.id
            db.commit()
            return system, ENROLLED.format(
                name=resident.full_name.split()[0], condo=condominium.name
            )
        if result == EnrollmentResult.WRONG_CODE:
            return system, WRONG_CODE
        if result in (EnrollmentResult.EXPIRED, EnrollmentResult.LOCKED):
            return system, CODE_UNUSABLE
        return system, ASK_FOR_CODE

    if text is None:
        return system, TEXT_ONLY
    run = run_concierge(
        db,
        llm,
        condominium=condominium,
        conversation=conversation,
        resident=resident,
        trigger=inbound,
    )
    return MessageKind.AI_REPLY, run.reply_text
