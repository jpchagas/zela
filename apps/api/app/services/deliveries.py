"""Deliveries received at the front desk, in the Encomendas sheet (ADR 0013).

Staff (or the manager) record a package for a unit; Zela notifies the people of that
unit from the Pessoas sheet and the package waits until it is marked as picked up.
Numbers come from a Postgres counter, so two packages never share one.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher
from app.integrations.google.base import Google
from app.integrations.whatsapp.templates import DELIVERY_ARRIVED
from app.models import Condominium
from app.models.enums import ActorType, RegisterKind
from app.registers.table import Row, Table, normalize_header
from app.services import audit, drive, notifications, people, tickets
from app.services.people import Person

WAITING = "Aguardando retirada"
PICKED_UP = "Retirada"
RETURNED = "Devolvida"


@dataclass(frozen=True)
class Received:
    number: str
    zela_id: str
    place: str
    notified: int
    # True when the recipient's name matched someone registered on the unit.
    recipient_found: bool
    duplicate: bool


def _table(db: Session, google: Google, condominium_id: uuid.UUID, *, lock: bool = True) -> Table:
    return drive.open_table(db, google, condominium_id, RegisterKind.DELIVERIES, lock=lock)


def is_waiting(row: Row) -> bool:
    return normalize_header(row.values["status"]) in ("", normalize_header(WAITING))


def place_of(row: Row) -> str:
    return " ".join(p for p in (row.values["block"], row.values["unit"]) if p) or "-"


def receive(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    block: str,
    unit: str,
    recipient: str,
    description: str,
    idempotency_key: str,
    actor_id: uuid.UUID,
) -> Received:
    """Records a package and notifies the unit. Raises people.AmbiguousUnit, or
    drive.RegisterUnavailable when a sheet can't be used."""
    people_table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    block, unit = people.resolve_place(people_table, block, unit)
    recipient = " ".join(recipient.split())
    description = " ".join(description.split())
    seed = (
        f"{condo.id}:{idempotency_key}:{normalize_header(block)}:{normalize_header(unit)}:"
        f"{normalize_header(recipient)}:{normalize_header(description)}"
    )
    zela_id = "E-" + hashlib.sha256(seed.encode()).hexdigest()[:10].upper()
    place = " ".join(p for p in (block, unit) if p)

    table = _table(db, google, condo.id)
    existing = table.find(zela_id)
    if existing is not None:
        db.commit()  # a retried message: report what's there, notify nobody again
        return Received(existing.values["number"], zela_id, place, 0, False, duplicate=True)

    rows, found = people.unit_contacts(people_table, block, unit, recipient)
    to_notify = {people.phone_of(r): r for r in rows}  # one message per number
    number = str(tickets.next_number(db, condo.id, "delivery"))
    now = people.local_timestamp(condo)
    table.append(
        zela_id,
        {
            "number": number,
            "received_at": now,
            "block": block,
            "unit": unit,
            "recipient": recipient,
            "description": description,
            "received_by": person.name or person.role_label,
            "status": WAITING,
            "notified_at": now if to_notify else "",
        },
    )
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.AGENT,
        actor_id=actor_id,
        action="delivery.received",
        entity_type="sheet_row",
        entity_id=None,
        data={
            "register": "deliveries",
            "zela_id": zela_id,
            "number": number,
            "notified": len(to_notify),
            "recipient_found": found,
        },
    )
    db.commit()  # the row is in the sheet; record it and release the lock

    for phone, row in to_notify.items():
        notifications.enqueue(
            db,
            publisher,
            condominium_id=condo.id,
            recipient_e164=phone,
            template=DELIVERY_ARRIVED.name,
            params={
                "first_name": row.values["name"].split()[0] if row.values["name"] else "morador(a)",
                "place": place,
                "description": description or "encomenda",
                "number": number,
            },
            idempotency_key=f"delivery:{zela_id}:arrived:{phone}",
            guard={"delivery_waiting": {"number": number}},
        )
    return Received(number, zela_id, place, len(to_notify), found, duplicate=False)


def mine(db: Session, google: Google, condo: Condominium, person: Person) -> list[Row]:
    """Packages waiting for any of the sender's units (up to 10, newest first)."""
    if not person.memberships:
        return []
    table = _table(db, google, condo.id, lock=False)
    rows = [
        r
        for r in table.rows
        if is_waiting(r)
        and any(people.same_place(r, m.block, m.unit) for m in person.memberships if m.unit)
    ]
    return list(reversed(rows))[:10]


def find(table: Table, *, only_waiting: bool, query: str, limit: int = 15) -> list[Row]:
    q = normalize_header(query)
    rows = []
    for row in reversed(table.rows):
        if only_waiting and not is_waiting(row):
            continue
        text = normalize_header(
            " ".join(row.values[k] for k in ("number", "block", "unit", "recipient", "description"))
        )
        if q and q not in text:
            continue
        rows.append(row)
    return rows[:limit]


def by_number(table: Table, number: str) -> Row | None:
    return next((r for r in table.rows if r.values["number"] == str(number)), None)


def still_waiting(db: Session, google: Google, condominium_id: uuid.UUID, number: str) -> bool:
    """Notification guard: is the package still waiting to be picked up?
    Raises drive.RegisterUnavailable if the sheet can't be read (retry later)."""
    row = by_number(_table(db, google, condominium_id, lock=False), number)
    return row is not None and is_waiting(row)
