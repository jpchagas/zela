import hashlib
import hmac
import json

import pytest
from sqlalchemy import func, select

from app.core.jobs import get_job_publisher
from app.main import app
from app.models import WebhookEvent

SECRET = "test-app-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _payload(message_id="wamid.1", statuses=()):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PNID"},
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": "5511987654321",
                                    "type": "text",
                                    "text": {"body": "Oi"},
                                }
                            ]
                            if message_id
                            else [],
                            "statuses": [{"id": "wamid.out", "status": s} for s in statuses],
                        }
                    }
                ]
            }
        ],
    }


@pytest.fixture
def published():
    jobs = []

    class FakePublisher:
        def publish(self, topic, payload):
            jobs.append((topic, payload))

    app.dependency_overrides[get_job_publisher] = FakePublisher
    return jobs


def _post(client, payload, signature=None):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={
            "X-Hub-Signature-256": signature or _sign(body),
            "Content-Type": "application/json",
        },
    )


def test_subscription_verification(client):
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "42",
    }
    assert client.get("/webhooks/whatsapp", params=params).text == "42"
    params["hub.verify_token"] = "wrong"
    assert client.get("/webhooks/whatsapp", params=params).status_code == 403


def test_bad_signature_is_rejected_and_nothing_recorded(client, db, published):
    response = _post(client, _payload(), signature="sha256=deadbeef")
    assert response.status_code == 401
    assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 0
    assert published == []


def test_duplicate_delivery_is_processed_once(client, db, published):
    assert _post(client, _payload()).status_code == 200
    assert _post(client, _payload()).status_code == 200

    assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
    assert len(published) == 1
    assert published[0][0] == "whatsapp-inbound"


def test_each_status_transition_is_a_distinct_event(client, db, published):
    _post(client, _payload(message_id=None, statuses=["sent", "delivered"]))
    _post(client, _payload(message_id=None, statuses=["delivered", "read"]))
    ids = set(db.scalars(select(WebhookEvent.external_id)))
    assert ids == {"status:wamid.out:sent", "status:wamid.out:delivered", "status:wamid.out:read"}
    assert len(published) == 3
