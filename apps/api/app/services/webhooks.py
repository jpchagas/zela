from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.whatsapp.payload import InboundEvent
from app.models import WebhookEvent

PROVIDER_META = "meta"


def record_new_events(db: Session, events: list[InboundEvent]) -> list[str]:
    """Insert events into the idempotency ledger and return IDs of rows that were new.
    Retries and duplicate deliveries hit the unique constraint and are skipped."""
    new_ids: list[str] = []
    for event in events:
        row_id = db.scalar(
            insert(WebhookEvent)
            .values(
                provider=PROVIDER_META,
                external_id=event.external_id,
                event_type=event.event_type,
                payload={"phone_number_id": event.phone_number_id, **event.payload},
            )
            .on_conflict_do_nothing(index_elements=["provider", "external_id"])
            .returning(WebhookEvent.id)
        )
        if row_id is not None:
            new_ids.append(str(row_id))
    db.commit()
    return new_ids
