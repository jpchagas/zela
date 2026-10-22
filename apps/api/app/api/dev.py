"""Development-only helpers. Mounted only when ENV=development."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.session import get_db
from app.integrations.whatsapp.payload import extract_events
from app.integrations.whatsapp.sender import get_whatsapp_sender
from app.llm.factory import get_llm_client
from app.models import Condominium, Message, WebhookEvent
from app.models.enums import MessageDirection
from app.services import webhooks
from app.workers.inbound import process_webhook_event

router = APIRouter(prefix="/dev", tags=["dev"])


class SimulatedMessage(BaseModel):
    condominium_id: uuid.UUID
    from_e164: str = Field(pattern=r"^\+\d{10,15}$")
    text: str = Field(min_length=1, max_length=4096)


@router.post("/whatsapp/inbound")
def simulate_inbound(body: SimulatedMessage, db: Session = Depends(get_db)) -> dict:
    """Feed a resident message through the real pipeline (ledger, worker, agent) and
    return the replies, without Meta. The condominium needs a phone_number_id."""
    condo = db.get(Condominium, body.condominium_id)
    if condo is None or not condo.whatsapp_phone_number_id:
        raise NotFound("Condominium not found or WhatsApp not configured")
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": condo.whatsapp_phone_number_id},
                            "messages": [
                                {
                                    "id": f"dev.{uuid.uuid4().hex}",
                                    "from": body.from_e164.lstrip("+"),
                                    "type": "text",
                                    "text": {"body": body.text},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    event_ids = webhooks.record_new_events(db, extract_events(payload))
    inbound_id = None
    for event_id in event_ids:
        process_webhook_event(
            db, uuid.UUID(event_id), llm=get_llm_client(), sender=get_whatsapp_sender()
        )
        event = db.get(WebhookEvent, uuid.UUID(event_id))
        inbound_id = event.payload["message"]["id"]
    inbound = db.scalar(select(Message).where(Message.provider_message_id == inbound_id))
    replies = db.scalars(
        select(Message).where(
            Message.conversation_id == inbound.conversation_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.created_at >= inbound.created_at,
        )
    ).all()
    return {
        "conversation_id": str(inbound.conversation_id),
        "replies": [{"kind": m.kind.value, "body": m.body} for m in replies],
    }
