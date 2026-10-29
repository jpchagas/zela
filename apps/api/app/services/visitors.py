"""Visitors in the Visitantes sheet (ADR 0014).

Two ways in, both ending at the front desk:
- a resident authorizes a visitor ahead of time and gets a code; the desk checks the name
  or code, records the entry, and whoever authorized is told the visitor arrived;
- the desk announces a visitor who wasn't authorized; the unit is asked on WhatsApp, and
  whoever answers first lets them in or not, and the desk is told.
Expiry is read from the dates, not written: an authorization past its last day reads as
Expirado even if the sheet still says Autorizado.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher
from app.integrations.google.base import Google
from app.integrations.whatsapp.templates import VISITOR_ANSWER, VISITOR_ARRIVED, VISITOR_AT_GATE
from app.models import Condominium
from app.models.enums import ActorType, RegisterKind
from app.registers.table import Row, Table, normalize_header
from app.services import audit, drive, notifications, people
from app.services.people import Membership, Person

AUTHORIZED = "Autorizado"
WAITING = "Aguardando morador"
ENTERED = "Entrou"
REFUSED = "Recusado"
CANCELLED = "Cancelado"
EXPIRED = "Expirado"
# How far ahead, and for how long, one authorization may go.
MAX_AHEAD = timedelta(days=60)
MAX_SPAN = timedelta(days=30)


class VisitorError(Exception):
    """A rule the request breaks; the message is for the model to explain."""


@dataclass(frozen=True)
class Authorization:
    code: str
    zela_id: str
    place: str
    duplicate: bool


def _table(db: Session, google: Google, condominium_id: uuid.UUID, *, lock: bool = True) -> Table:
    return drive.open_table(db, google, condominium_id, RegisterKind.VISITORS, lock=lock)


def today(condo: Condominium, now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(condo.timezone)).date()


def fmt(day: date) -> str:
    return f"{day:%d/%m/%Y}"


def parse_date(text: str) -> date | None:
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), pattern).date()
        except ValueError:
            continue
    return None


def place_of(row: Row) -> str:
    return " ".join(p for p in (row.values["block"], row.values["unit"]) if p) or "-"


def status_of(row: Row, on: date) -> str:
    """The status as of `on`: a blank status reads as Autorizado, and an authorization or
    an unanswered announcement past its last day reads as Expirado."""
    status = row.values["status"].strip() or AUTHORIZED
    if status in (AUTHORIZED, WAITING):
        first = parse_date(row.values["visit_date"])
        last = parse_date(row.values["valid_until"]) or first
        if last is None or last < on:
            return EXPIRED
    return status


def valid_on(row: Row, on: date) -> bool:
    first = parse_date(row.values["visit_date"])
    return status_of(row, on) == AUTHORIZED and first is not None and first <= on


def by_code(table: Table, code: str) -> Row | None:
    wanted = "".join(ch for ch in code if ch.isdigit())
    return next((r for r in table.rows if wanted and r.values["code"] == wanted), None)


def _new_code(table: Table) -> str:
    used = {r.values["code"] for r in table.rows}
    while (code := f"{secrets.randbelow(900000) + 100000}") in used:
        pass
    return code


def _zela_id(condo: Condominium, idempotency_key: str, *parts: str) -> str:
    seed = ":".join([str(condo.id), idempotency_key, *(normalize_header(p) for p in parts)])
    return "V-" + hashlib.sha256(seed.encode()).hexdigest()[:10].upper()


def check_dates(condo: Condominium, first: date, last: date | None) -> date:
    """Validates an authorization's dates; returns the last day."""
    now = today(condo)
    last = last or first
    if first < now:
        raise VisitorError("The visit date is in the past.")
    if first > now + MAX_AHEAD:
        raise VisitorError("Visits can be authorized up to 60 days ahead.")
    if last < first:
        raise VisitorError("The last day is before the first.")
    if last - first > MAX_SPAN:
        raise VisitorError("One authorization can cover at most 30 days.")
    return last


def _audit(db: Session, condo: Condominium, actor_id: uuid.UUID, action: str, **data) -> None:
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.AGENT,
        actor_id=actor_id,
        action=action,
        entity_type="sheet_row",
        entity_id=None,
        data={"register": "visitors", **data},
    )


def authorize(
    db: Session,
    google: Google,
    *,
    condo: Condominium,
    person: Person,
    block: str,
    unit: str,
    visitor: str,
    first: date,
    last: date,
    notes: str,
    idempotency_key: str,
    actor_id: uuid.UUID,
    membership: Membership | None = None,
) -> Authorization:
    visitor = " ".join(visitor.split())
    zela_id = _zela_id(condo, idempotency_key, visitor, fmt(first))
    place = " ".join(p for p in (block, unit) if p)
    table = _table(db, google, condo.id)
    existing = table.find(zela_id)
    if existing is not None:
        db.commit()  # a retried message: the authorization is already there
        return Authorization(existing.values["code"], zela_id, place, duplicate=True)
    code = _new_code(table)
    table.append(
        zela_id,
        {
            "code": code,
            "visitor": visitor,
            "block": block,
            "unit": unit,
            "authorized_by": _who(person, membership),
            "authorized_by_id": people.id_of(person, membership),
            "visit_date": fmt(first),
            "valid_until": fmt(last),
            "status": AUTHORIZED,
            "notes": notes,
        },
    )
    _audit(db, condo, actor_id, "visitor.authorized", zela_id=zela_id, days=(last - first).days + 1)
    db.commit()
    return Authorization(code, zela_id, place, duplicate=False)


def _who(person: Person, membership: Membership | None) -> str:
    name = person.name or person.role_label
    return f"{name} ({membership.label})" if membership else name


def for_units(table: Table, person: Person, on: date, limit: int = 10) -> list[Row]:
    """The sender's units' visitors still to come or awaiting an answer, newest first."""
    rows = [
        r
        for r in reversed(table.rows)
        if status_of(r, on) in (AUTHORIZED, WAITING)
        and any(people.same_place(r, m.block, m.unit) for m in person.memberships if m.unit)
    ]
    return rows[:limit]


def at_desk(table: Table, query: str, on: date, limit: int = 10) -> list[Row]:
    """What the desk may act on today: visitors valid today or awaiting an answer, matching
    a name, code or unit."""
    q = normalize_header(query)
    rows = []
    for row in reversed(table.rows):
        if not (valid_on(row, on) or status_of(row, on) == WAITING):
            continue
        text = normalize_header(
            " ".join(row.values[k] for k in ("code", "visitor", "block", "unit"))
        )
        if q and q not in text:
            continue
        rows.append(row)
    return rows[:limit]


def record_entry(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    code: str,
    idempotency_key: str,
    actor_id: uuid.UUID,
) -> tuple[Row, bool]:
    """Lets an authorized visitor in. A one-day authorization ends with the entry; a
    longer one stays valid and the entry is added to Observações. Tells whoever authorized
    it ahead of time. Returns the row and whether they were told."""
    table = _table(db, google, condo.id)
    row = by_code(table, code)
    on = today(condo)
    if row is None:
        db.commit()
        raise VisitorError(f"There is no authorization with code {code}.")
    if not valid_on(row, on):
        db.commit()
        raise VisitorError(f"Code {code} is not valid today: {status_of(row, on)}.")
    # Announced at the gate (the desk is on the row before anyone entered): the unit just
    # answered, so don't tell them again.
    announced = bool(row.values["checked_by_id"]) and not row.values["entered_at"]
    now = people.local_timestamp(condo)
    last = parse_date(row.values["valid_until"]) or on
    values = {
        "entered_at": now,
        "checked_by": person.name or person.role_label,
        "checked_by_id": people.id_of(person),
    }
    if last > on:
        values["notes"] = f"{row.values['notes']}\nEntrada em {now}".strip()
    else:
        values["status"] = ENTERED
    if not row.zela_id:
        table.assign_id(row, f"V-ROW{row.number}")
    updated = table.update(row.zela_id, values)
    _audit(db, condo, actor_id, "visitor.entered", zela_id=updated.zela_id)
    db.commit()

    people_table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    phone = people.phone_for_id(people_table, condo, updated.values["authorized_by_id"])
    if announced or phone is None or phone == person.phone:
        return updated, False
    notifications.enqueue(
        db,
        publisher,
        condominium_id=condo.id,
        recipient_e164=phone,
        template=VISITOR_ARRIVED.name,
        params={
            "visitor": updated.values["visitor"],
            "condominium": condo.name,
            "time": now[-5:],
            "code": updated.values["code"],
        },
        idempotency_key=f"visitor:{updated.zela_id}:entered:{idempotency_key}",
    )
    return updated, True


def announce(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    block: str,
    unit: str,
    visitor: str,
    notes: str,
    idempotency_key: str,
    actor_id: uuid.UUID,
) -> tuple[Row, int]:
    """A visitor at the gate without authorization: records them as awaiting the unit's
    answer and asks the unit. Raises people.AmbiguousUnit. Returns the row and how many
    people were asked."""
    people_table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    block, unit = people.resolve_place(people_table, block, unit)
    contacts, _ = people.unit_contacts(people_table, block, unit, "")
    to_ask = {people.phone_of(r): r for r in contacts}
    visitor = " ".join(visitor.split())
    on = today(condo)
    zela_id = _zela_id(condo, idempotency_key, visitor, block, unit)

    table = _table(db, google, condo.id)
    existing = table.find(zela_id)
    if existing is not None:
        db.commit()
        return existing, 0
    row = table.append(
        zela_id,
        {
            "code": _new_code(table),
            "visitor": visitor,
            "block": block,
            "unit": unit,
            "visit_date": fmt(on),
            "valid_until": fmt(on),
            "status": WAITING,
            "checked_by": person.name or person.role_label,
            "checked_by_id": people.id_of(person),
            "notes": notes,
        },
    )
    _audit(db, condo, actor_id, "visitor.announced", zela_id=zela_id, asked=len(to_ask))
    db.commit()

    place = place_of(row)
    for phone in to_ask:
        notifications.enqueue(
            db,
            publisher,
            condominium_id=condo.id,
            recipient_e164=phone,
            template=VISITOR_AT_GATE.name,
            params={
                "visitor": visitor,
                "condominium": condo.name,
                "place": place,
                "code": row.values["code"],
            },
            idempotency_key=f"visitor:{zela_id}:ask:{phone}",
            guard={"visitor_status": {"code": row.values["code"], "status": WAITING}},
        )
    return row, len(to_ask)


def answer(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    code: str,
    allow: bool,
    actor_id: uuid.UUID,
) -> tuple[Row, bool]:
    """The unit's answer to an announcement. Only someone registered on that unit may
    answer, and only while it is still waiting. Tells the desk. Returns the row and
    whether the desk was told."""
    table = _table(db, google, condo.id)
    row = by_code(table, code)
    if row is None or not any(
        people.same_place(row, m.block, m.unit) for m in person.memberships if m.unit
    ):
        db.commit()  # someone else's unit reads the same as a code that doesn't exist
        raise VisitorError(f"There is no visitor waiting for the sender's unit with code {code}.")
    status = status_of(row, today(condo))
    if status != WAITING:
        db.commit()
        raise VisitorError(f"That visitor is not waiting for an answer any more: {status}.")
    membership = next(m for m in person.memberships if people.same_place(row, m.block, m.unit))
    updated = table.update(
        row.zela_id,
        {
            "status": AUTHORIZED if allow else REFUSED,
            "authorized_by": _who(person, membership),
            "authorized_by_id": people.id_of(person, membership),
        },
    )
    _audit(db, condo, actor_id, "visitor.answered", zela_id=updated.zela_id, allowed=allow)
    db.commit()

    people_table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    desk = people.phone_for_id(people_table, condo, updated.values["checked_by_id"])
    if desk is None:
        return updated, False
    notifications.enqueue(
        db,
        publisher,
        condominium_id=condo.id,
        recipient_e164=desk,
        template=VISITOR_ANSWER.name,
        params={
            "place": place_of(updated),
            "answer": "liberou" if allow else "não liberou",
            "visitor": updated.values["visitor"],
            "code": updated.values["code"],
        },
        idempotency_key=f"visitor:{updated.zela_id}:answer",
    )
    return updated, True


def cancel(
    db: Session, google: Google, *, condo: Condominium, person: Person, code: str, actor_id
) -> Row:
    """Cancels an authorization of one of the sender's units (any unit, for the manager)."""
    table = _table(db, google, condo.id)
    row = by_code(table, code)
    mine = row is not None and (
        person.role == people.PersonRole.MANAGER
        or any(people.same_place(row, m.block, m.unit) for m in person.memberships if m.unit)
    )
    if not mine:
        db.commit()
        raise VisitorError(f"There is no authorization of the sender's units with code {code}.")
    status = status_of(row, today(condo))
    if status not in (AUTHORIZED, WAITING):
        db.commit()
        raise VisitorError(f"That authorization can't be cancelled: {status}.")
    if not row.zela_id:
        table.assign_id(row, f"V-ROW{row.number}")
    updated = table.update(row.zela_id, {"status": CANCELLED})
    _audit(db, condo, actor_id, "visitor.cancelled", zela_id=updated.zela_id)
    db.commit()
    return updated


def status_still(
    db: Session, google: Google, condominium_id: uuid.UUID, code: str, status: str
) -> bool:
    """Notification guard: does the visitor still have this status (as of today)?
    Raises drive.RegisterUnavailable if the sheet can't be read (retry later)."""
    condo = db.get(Condominium, condominium_id)
    row = by_code(_table(db, google, condominium_id, lock=False), code)
    return row is not None and status_of(row, today(condo)) == status
