"""Splits a Meta Cloud API webhook payload into individually idempotent events."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InboundEvent:
    external_id: str
    event_type: str  # "message" | "status"
    phone_number_id: str | None
    payload: dict[str, Any]


def extract_events(body: dict[str, Any]) -> list[InboundEvent]:
    events: list[InboundEvent] = []
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            for message in value.get("messages") or []:
                if message.get("id"):
                    events.append(
                        InboundEvent(
                            external_id=f"msg:{message['id']}",
                            event_type="message",
                            phone_number_id=phone_number_id,
                            payload={"message": message, "contacts": value.get("contacts")},
                        )
                    )
            for status in value.get("statuses") or []:
                if status.get("id") and status.get("status"):
                    # The same message moves through sent → delivered → read; each is distinct.
                    events.append(
                        InboundEvent(
                            external_id=f"status:{status['id']}:{status['status']}",
                            event_type="status",
                            phone_number_id=phone_number_id,
                            payload={"status": status},
                        )
                    )
    return events
