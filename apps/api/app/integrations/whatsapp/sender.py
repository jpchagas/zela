"""Outbound WhatsApp messages. Callers persist the message row first and record the
result, so the database always reflects what was actually sent."""

import logging
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SendError(Exception):
    """The provider rejected or could not receive the message."""


class WhatsAppSender(Protocol):
    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        """Send a text message and return the provider's message ID."""
        ...


class MetaCloudSender:
    def __init__(self, access_token: str, graph_version: str, timeout: float = 10.0):
        self._client = httpx.Client(
            base_url=f"https://graph.facebook.com/{graph_version}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        try:
            response = self._client.post(
                f"/{phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_e164.lstrip("+"),
                    "type": "text",
                    "text": {"body": body, "preview_url": False},
                },
            )
        except httpx.HTTPError as exc:
            raise SendError(f"WhatsApp request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            # Meta's error body names the problem (e.g. outside the 24h window); no PII in it.
            raise SendError(f"WhatsApp API {response.status_code}: {response.text[:300]}")
        return response.json()["messages"][0]["id"]


@dataclass
class RecordingSender:
    """Records instead of sending. Used for local development and tests."""

    sent: list[tuple[str, str, str]] = field(default_factory=list)
    fail_with: str | None = None

    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        if self.fail_with:
            raise SendError(self.fail_with)
        self.sent.append((phone_number_id, to_e164, body))
        logger.info("whatsapp message recorded (not sent)", extra={"to_suffix": to_e164[-4:]})
        return f"local.{uuid.uuid4().hex}"


@lru_cache
def get_whatsapp_sender() -> WhatsAppSender:
    settings = get_settings()
    if settings.whatsapp_sender == "log":
        return RecordingSender()
    return MetaCloudSender(settings.whatsapp_access_token, settings.whatsapp_graph_version)
