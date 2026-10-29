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


class MediaError(Exception):
    """A file someone sent could not be downloaded."""


class WhatsAppSender(Protocol):
    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        """Send a text message and return the provider's message ID."""
        ...

    def send_template(
        self, phone_number_id: str, to_e164: str, name: str, language: str, params: list[str]
    ) -> str:
        """Send an approved template message and return the provider's message ID."""
        ...

    def download_media(self, media_id: str, max_bytes: int) -> bytes:
        """Download a file someone sent (document, image). Raises MediaError."""
        ...


class MetaCloudSender:
    def __init__(self, access_token: str, graph_version: str, timeout: float = 10.0):
        self._client = httpx.Client(
            base_url=f"https://graph.facebook.com/{graph_version}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        return self._post(
            phone_number_id,
            to_e164,
            {"type": "text", "text": {"body": body, "preview_url": False}},
        )

    def send_template(
        self, phone_number_id: str, to_e164: str, name: str, language: str, params: list[str]
    ) -> str:
        return self._post(
            phone_number_id,
            to_e164,
            {
                "type": "template",
                "template": {
                    "name": name,
                    "language": {"code": language},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": p} for p in params],
                        }
                    ],
                },
            },
        )

    def download_media(self, media_id: str, max_bytes: int) -> bytes:
        # Two calls: the media ID resolves to a short-lived URL, which needs the same token.
        try:
            info = self._client.get(f"/{media_id}")
            if info.status_code >= 400:
                raise MediaError(f"WhatsApp media lookup {info.status_code}")
            meta = info.json()
            if int(meta.get("file_size") or 0) > max_bytes:
                raise MediaError("too large")
            response = self._client.get(meta["url"])
        except httpx.HTTPError as exc:
            raise MediaError(f"WhatsApp media download failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise MediaError(f"WhatsApp media download {response.status_code}")
        if len(response.content) > max_bytes:
            raise MediaError("too large")
        return response.content

    def _post(self, phone_number_id: str, to_e164: str, message: dict) -> str:
        try:
            response = self._client.post(
                f"/{phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_e164.lstrip("+"),
                    **message,
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
    templates: list[tuple[str, str, str, list[str]]] = field(default_factory=list)
    fail_with: str | None = None
    # Files "sent" by people, by media ID (tests and the dev inbound endpoint fill it).
    media: dict[str, bytes] = field(default_factory=dict)

    def send_text(self, phone_number_id: str, to_e164: str, body: str) -> str:
        if self.fail_with:
            raise SendError(self.fail_with)
        self.sent.append((phone_number_id, to_e164, body))
        logger.info("whatsapp message recorded (not sent)", extra={"to_suffix": to_e164[-4:]})
        return f"local.{uuid.uuid4().hex}"

    def send_template(
        self, phone_number_id: str, to_e164: str, name: str, language: str, params: list[str]
    ) -> str:
        if self.fail_with:
            raise SendError(self.fail_with)
        self.templates.append((phone_number_id, to_e164, name, params))
        logger.info("whatsapp template recorded (not sent)", extra={"template": name})
        return f"local.{uuid.uuid4().hex}"

    def download_media(self, media_id: str, max_bytes: int) -> bytes:
        if media_id not in self.media:
            raise MediaError("unknown media")
        if len(self.media[media_id]) > max_bytes:
            raise MediaError("too large")
        return self.media[media_id]


@lru_cache
def get_whatsapp_sender() -> WhatsAppSender:
    settings = get_settings()
    if settings.whatsapp_sender == "log":
        return RecordingSender()
    return MetaCloudSender(settings.whatsapp_access_token, settings.whatsapp_graph_version)
