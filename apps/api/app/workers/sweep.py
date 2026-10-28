"""Re-queue webhook events that were recorded but never finished.

Covers a publish lost after commit, a worker crash, and retryable failures. Run it on a
schedule (Cloud Scheduler in production): `python -m app.workers.sweep`.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.jobs import get_job_publisher
from app.db.session import SessionLocal
from app.models import Document, NotificationEvent, WebhookEvent
from app.models.enums import DeliveryStatus, DocumentStatus, JobStatus
from app.workers.runner import DOCUMENT_TOPIC, INBOUND_TOPIC, NOTIFICATION_TOPIC

STALE_AFTER = timedelta(minutes=2)
MAX_ATTEMPTS = 5


def find_requeueable(db, now: datetime) -> list[WebhookEvent]:
    return list(
        db.scalars(
            select(WebhookEvent)
            .where(
                WebhookEvent.received_at < now - STALE_AFTER,
                WebhookEvent.attempts < MAX_ATTEMPTS,
                or_(
                    WebhookEvent.status == JobStatus.RECEIVED,
                    # Unroutable events are marked failed with attempts kept; they retry
                    # until MAX_ATTEMPTS, which also covers a condo configured late.
                    WebhookEvent.status == JobStatus.FAILED,
                ),
            )
            .order_by(WebhookEvent.received_at)
            .limit(500)
        )
    )


def find_stuck_documents(db, now: datetime) -> list[Document]:
    return list(
        db.scalars(
            select(Document).where(
                Document.status.in_([DocumentStatus.PENDING, DocumentStatus.INDEXING]),
                Document.updated_at < now - STALE_AFTER,
            )
        )
    )


def find_stuck_notifications(db, now: datetime) -> list[NotificationEvent]:
    return list(
        db.scalars(
            select(NotificationEvent).where(
                NotificationEvent.status == DeliveryStatus.PENDING,
                NotificationEvent.attempts < MAX_ATTEMPTS,
                NotificationEvent.updated_at < now - STALE_AFTER,
            )
        )
    )


def main() -> None:
    publisher = get_job_publisher()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        events = find_requeueable(db, now)
        for event in events:
            publisher.publish(INBOUND_TOPIC, {"webhook_event_id": str(event.id)})
        docs = find_stuck_documents(db, now)
        for document in docs:
            publisher.publish(DOCUMENT_TOPIC, {"document_id": str(document.id)})
        pending = find_stuck_notifications(db, now)
        for notification in pending:
            publisher.publish(NOTIFICATION_TOPIC, {"notification_id": str(notification.id)})
    print(
        f"Re-queued {len(events)} event(s), {len(docs)} document(s), {len(pending)} notification(s)"
    )


if __name__ == "__main__":
    main()
