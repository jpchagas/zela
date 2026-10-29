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
from app.agents.zela import run_zela
from app.core.jobs import JobPublisher, get_job_publisher
from app.integrations.google.base import Google
from app.integrations.whatsapp.sender import WhatsAppSender
from app.llm.base import LLMClient
from app.models import Condominium, Conversation, Message, Resident, WebhookEvent
from app.models.enums import ConversationStatus, JobStatus, MessageKind, ResidentStatus
from app.services import (
    conversations,
    drive,
    emergency_contacts,
    enrollment,
    manager_phone,
    people,
    rules,
)
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
ON_CALL_ACK = (
    "Mensagem recebida. Este número está no plantão de emergência do {condo}: acompanhe e "
    "atualize os chamados pelo painel do Zela."
)


# Sheet-backed condominiums (ADR 0010/0011).
UNKNOWN_PERSON = (
    "Olá! Este é o atendimento do {condo} pelo WhatsApp. Não encontrei este número no "
    "cadastro do condomínio. Peça ao síndico para cadastrar você."
)
ON_CALL_ACK_SHEETS = (
    "Mensagem recebida. Este número está no plantão de emergência do {condo}. As "
    "ocorrências ficam na planilha Ocorrências, no Google Drive do síndico."
)
SHEETS_UNAVAILABLE = (
    "Estou sem acesso ao cadastro do condomínio agora e não consigo atender. Tente de novo "
    "mais tarde ou fale com o síndico."
)
SHEETS_UNAVAILABLE_MANAGER = (
    "Não consigo acessar as planilhas do condomínio no Google Drive: {reason} "
    "Confira a página de configuração do Zela."
)


class UnroutableEvent(Exception):
    """The event can't be processed and retrying won't help."""


def process_webhook_event(
    db: Session,
    event_id: uuid.UUID,
    *,
    llm: LLMClient,
    sender: WhatsAppSender,
    publisher: JobPublisher | None = None,
    google: Google | None = None,
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
            _handle_message(
                db, event.payload, llm=llm, sender=sender, publisher=publisher, google=google
            )
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
    """Serialize work per contact across workers.

    A session-level advisory lock belongs to the connection that took it, and the ORM
    session hands its connection back to the pool at every commit. So the lock lives on a
    dedicated connection, which also releases it if anything goes wrong."""
    key = db.scalar(select(func.hashtextextended(f"conv:{condominium_id}:{contact}", 0)))
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
        lock_conn.execute(select(func.pg_advisory_lock(key)))
        try:
            yield
        finally:
            db.rollback()
            lock_conn.execute(select(func.pg_advisory_unlock(key)))


def _handle_message(
    db: Session,
    payload: dict,
    *,
    llm: LLMClient,
    sender: WhatsAppSender,
    publisher: JobPublisher | None,
    google: Google | None,
) -> None:
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
        if text is not None:
            body = text
        elif message.get("type") == "document":
            body = f"[documento: {(message.get('document') or {}).get('filename', '')}]"
        else:
            body = f"[{message.get('type', 'desconhecido')}]"
        inbound = conversations.record_inbound(
            db, conversation, provider_message_id=message["id"], body=body
        )
        kind, reply = _decide_reply(
            db,
            llm,
            publisher,
            google,
            condominium,
            conversation,
            inbound,
            contact,
            text,
            sender=sender,
            message=message,
        )
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
    publisher: JobPublisher | None,
    google: Google | None,
    condominium: Condominium,
    conversation: Conversation,
    inbound: Message,
    contact: str,
    text: str | None,
    *,
    sender: WhatsAppSender,
    message: dict,
) -> tuple[MessageKind, str | None]:
    system = MessageKind.SYSTEM_REPLY
    sheets = drive.uses_sheets(db, condominium.id)
    confirmation = manager_phone.handle_inbound(
        db, condominium, contact, text, drive_connected=sheets
    )
    if confirmation is not None:
        return system, confirmation
    if sheets:
        return _decide_sheet_reply(
            db,
            llm,
            publisher,
            google,
            condominium,
            conversation,
            inbound,
            contact,
            text,
            sender=sender,
            message=message,
        )
    return _decide_legacy_reply(
        db, llm, publisher, condominium, conversation, inbound, contact, text
    )


def _decide_sheet_reply(
    db: Session,
    llm: LLMClient,
    publisher: JobPublisher | None,
    google: Google | None,
    condominium: Condominium,
    conversation: Conversation,
    inbound: Message,
    contact: str,
    text: str | None,
    *,
    sender: WhatsAppSender,
    message: dict,
) -> tuple[MessageKind, str | None]:
    system = MessageKind.SYSTEM_REPLY
    if google is None:
        from app.integrations.google.factory import get_google

        google = get_google()
    try:
        person = people.identify(db, google, condominium, contact)
    except drive.RegisterUnavailable as exc:
        is_manager = bool(
            condominium.manager_phone_confirmed_at and condominium.manager_phone_e164 == contact
        )
        if is_manager:
            return system, SHEETS_UNAVAILABLE_MANAGER.format(reason=exc.message)
        return system, SHEETS_UNAVAILABLE
    if person is None:
        if emergency_contacts.is_emergency_contact(db, condominium.id, contact):
            return system, ON_CALL_ACK_SHEETS.format(condo=condominium.name)
        # Answered without the model: unknown numbers cost nothing and learn nothing.
        return system, UNKNOWN_PERSON.format(condo=condominium.name)
    if message.get("type") == "document":
        # Handled without the model: saved to Drive and indexed (ADR 0015).
        return system, rules.receive(
            db,
            google,
            sender,
            publisher or get_job_publisher(),
            condo=condominium,
            person=person,
            message=message,
        )
    if text is None:
        return system, TEXT_ONLY
    run = run_zela(
        db,
        llm,
        condominium=condominium,
        conversation=conversation,
        person=person,
        trigger=inbound,
        google=google,
        publisher=publisher,
    )
    return MessageKind.AI_REPLY, run.reply_text


def _decide_legacy_reply(
    db: Session,
    llm: LLMClient,
    publisher: JobPublisher | None,
    condominium: Condominium,
    conversation: Conversation,
    inbound: Message,
    contact: str,
    text: str | None,
) -> tuple[MessageKind, str | None]:
    """Milestone 2–3 flow (Postgres residents, enrollment codes, dashboard escalation),
    for condominiums that haven't connected Google Drive."""
    system = MessageKind.SYSTEM_REPLY
    if conversation.status == ConversationStatus.ESCALATED:
        return system, None  # staff own the conversation; they see it in the dashboard

    phone = enrollment.find_phone(db, condominium.id, contact)
    if phone is None:
        if emergency_contacts.is_emergency_contact(db, condominium.id, contact):
            return system, ON_CALL_ACK.format(condo=condominium.name)
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
        publisher=publisher,
    )
    return MessageKind.AI_REPLY, run.reply_text
