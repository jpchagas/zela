import json

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, InvalidInput, Unauthenticated
from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.integrations.whatsapp.payload import extract_events
from app.integrations.whatsapp.signature import is_valid_signature
from app.services import webhooks
from app.workers.runner import INBOUND_TOPIC

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_subscription(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
) -> str:
    if (
        mode != "subscribe"
        or not settings.whatsapp_verify_token
        or (token != settings.whatsapp_verify_token)
    ):
        raise Forbidden("Verification failed")
    return challenge


@router.post("/whatsapp")
async def receive(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    publisher: JobPublisher = Depends(get_job_publisher),
) -> Response:
    """Acknowledge fast: verify, record, enqueue. Agent work happens in a worker."""
    body = await request.body()
    if not is_valid_signature(
        settings.whatsapp_app_secret, body, request.headers.get("X-Hub-Signature-256")
    ):
        raise Unauthenticated("Invalid signature")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise InvalidInput("Body is not JSON") from exc

    new_ids = webhooks.record_new_events(db, extract_events(payload))
    for event_id in new_ids:
        publisher.publish(INBOUND_TOPIC, {"webhook_event_id": event_id})
    return Response(status_code=200)
