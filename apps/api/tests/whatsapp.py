"""Helpers for driving the WhatsApp pipeline in tests."""

import itertools
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.whatsapp.payload import extract_events
from app.integrations.whatsapp.sender import RecordingSender
from app.llm.base import LLMClient
from app.llm.scripted import ScriptedLLM
from app.models import Condominium, Message, Resident, ResidentPhone, UnitMembership
from app.models.enums import MessageDirection, ResidentStatus, UnitRelationship
from app.services import webhooks
from app.workers.inbound import process_webhook_event
from tests.factories import FakePublisher

_ids = itertools.count(1)

RESIDENT_PHONE = "+5511987654321"


def inbound_payload(
    condo: Condominium, from_e164: str, text: str | None, *, msg_type="text", wamid=None
) -> dict:
    message = {
        "id": wamid or f"wamid.test{next(_ids)}",
        "from": from_e164.lstrip("+"),
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": text}
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": condo.whatsapp_phone_number_id},
                            "messages": [message],
                        }
                    }
                ]
            }
        ]
    }


def deliver(
    db: Session,
    condo: Condominium,
    text: str | None,
    *,
    sender: RecordingSender,
    llm: LLMClient | None = None,
    from_e164: str = RESIDENT_PHONE,
    publisher=None,
    google=None,
    **kwargs,
) -> list[uuid.UUID]:
    """Record and process an inbound message like the webhook + worker would."""
    payload = inbound_payload(condo, from_e164, text, **kwargs)
    ids = [uuid.UUID(i) for i in webhooks.record_new_events(db, extract_events(payload))]
    for event_id in ids:
        process_webhook_event(
            db,
            event_id,
            llm=llm or ScriptedLLM(),
            sender=sender,
            publisher=publisher or FakePublisher(),
            google=google,
        )
    return ids


def outbound(db: Session) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.direction == MessageDirection.OUTBOUND)
            .order_by(Message.created_at)
        )
    )


def make_resident(
    db: Session,
    condo: Condominium,
    *,
    phone: str = RESIDENT_PHONE,
    enrolled: bool = True,
    unit=None,
    name: str = "Maria Silva",
) -> Resident:
    resident = Resident(
        condominium_id=condo.id,
        full_name=name,
        status=ResidentStatus.ACTIVE if enrolled else ResidentStatus.INVITED,
    )
    db.add(resident)
    db.flush()
    db.add(
        ResidentPhone(
            condominium_id=condo.id,
            resident_id=resident.id,
            phone_e164=phone,
            is_primary=True,
            verified_at=datetime.now(timezone.utc) if enrolled else None,
        )
    )
    if unit is not None:
        db.add(
            UnitMembership(
                condominium_id=condo.id,
                unit_id=unit.id,
                resident_id=resident.id,
                relationship=UnitRelationship.OWNER,
            )
        )
    db.commit()
    return resident
