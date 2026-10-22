"""Entry points that execute queued jobs with their own database session."""

import logging
import uuid

from app.db.session import SessionLocal
from app.integrations.whatsapp.sender import get_whatsapp_sender
from app.llm.factory import get_llm_client
from app.workers.inbound import process_webhook_event

logger = logging.getLogger(__name__)

INBOUND_TOPIC = "whatsapp-inbound"


def run_inbound_job(payload: dict[str, str]) -> None:
    with SessionLocal() as db:
        process_webhook_event(
            db,
            uuid.UUID(payload["webhook_event_id"]),
            llm=get_llm_client(),
            sender=get_whatsapp_sender(),
        )


HANDLERS = {INBOUND_TOPIC: run_inbound_job}
