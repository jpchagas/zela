"""Entry points that execute queued jobs with their own database session."""

import logging
import uuid

from app.db.session import SessionLocal
from app.integrations.google.factory import get_google
from app.integrations.storage import get_blob_store
from app.integrations.whatsapp.sender import get_whatsapp_sender
from app.llm.factory import get_llm_client
from app.services import documents, drive, notifications
from app.workers.inbound import process_webhook_event

logger = logging.getLogger(__name__)

INBOUND_TOPIC = "whatsapp-inbound"
DOCUMENT_TOPIC = "document-index"
NOTIFICATION_TOPIC = notifications.NOTIFICATION_TOPIC
DRIVE_SETUP_TOPIC = drive.DRIVE_SETUP_TOPIC


def run_inbound_job(payload: dict[str, str]) -> None:
    with SessionLocal() as db:
        process_webhook_event(
            db,
            uuid.UUID(payload["webhook_event_id"]),
            llm=get_llm_client(),
            sender=get_whatsapp_sender(),
            google=get_google(),
        )


def run_document_job(payload: dict[str, str]) -> None:
    with SessionLocal() as db:
        documents.index_document(db, get_blob_store(), uuid.UUID(payload["document_id"]))


def run_notification_job(payload: dict[str, str]) -> None:
    with SessionLocal() as db:
        notifications.deliver(
            db, uuid.UUID(payload["notification_id"]), get_whatsapp_sender(), get_google()
        )


def run_drive_setup_job(payload: dict[str, str]) -> None:
    with SessionLocal() as db:
        drive.setup_registers(db, get_google(), uuid.UUID(payload["condominium_id"]))


HANDLERS = {
    INBOUND_TOPIC: run_inbound_job,
    DOCUMENT_TOPIC: run_document_job,
    NOTIFICATION_TOPIC: run_notification_job,
    DRIVE_SETUP_TOPIC: run_drive_setup_job,
}
