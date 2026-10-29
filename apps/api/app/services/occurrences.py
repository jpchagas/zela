"""Occurrences (complaints and maintenance) in the Ocorrências sheet (ADR 0012).

Classification is the same deterministic validation as Milestone 3 tickets
(`tickets.classify`, ADR 0009): the model only suggests, keywords force emergencies, and
the suggestion is stored apart from the confirmed values. Numbers come from a Postgres
counter, so two reports can never share one.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher
from app.integrations.google.base import Google
from app.integrations.whatsapp.templates import OCCURRENCE_EMERGENCY, OCCURRENCE_UPDATE
from app.models import Condominium, EmergencyContact
from app.models.enums import ActorType, RegisterKind, TicketCategory, TicketPriority
from app.registers.table import Row, Table, normalize_header
from app.services import audit, drive, notifications, people, tickets
from app.services.people import Membership, Person

TYPE_LABEL = {
    "manutencao": "Manutenção",
    "reclamacao": "Reclamação",
    "sugestao": "Sugestão",
    "outro": "Outro",
}
STATUS_LABEL = {
    "aberta": "Aberta",
    "em_andamento": "Em andamento",
    "aguardando": "Aguardando",
    "resolvida": "Resolvida",
    "cancelada": "Cancelada",
}
CLOSED = {"Resolvida", "Cancelada"}
# What the reporter is told when the manager changes the status.
REPORTER_MESSAGE = {
    "Aberta": "foi reaberta.",
    "Em andamento": "o síndico começou a cuidar do problema.",
    "Aguardando": "aguardando mais informações ou um prestador de serviço.",
    "Resolvida": "foi marcada como resolvida. Se o problema continuar, avise por aqui.",
    "Cancelada": "foi cancelada.",
}
CATEGORY_BY_LABEL = {normalize_header(v): k for k, v in tickets.CATEGORY_LABEL.items()}


@dataclass(frozen=True)
class Report:
    number: str
    zela_id: str
    category: str
    priority: str
    emergency: bool
    alerted: int
    duplicate: bool


def _table(db: Session, google: Google, condominium_id: uuid.UUID, *, lock: bool = True) -> Table:
    return drive.open_table(db, google, condominium_id, RegisterKind.OCCURRENCES, lock=lock)


def is_open(row: Row) -> bool:
    return row.values["status"] not in CLOSED


def summary_of(row: Row) -> str:
    text = " ".join(row.values["description"].split())
    return text if len(text) <= 60 else text[:57].rstrip() + "..."


def report(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    *,
    condo: Condominium,
    person: Person,
    membership: Membership | None,
    type_: str,
    description: str,
    location: str,
    ai_category: TicketCategory | None,
    ai_priority: TicketPriority | None,
    idempotency_key: str,
    actor_id: uuid.UUID,
) -> Report:
    description = " ".join(description.split())
    seed = f"{condo.id}:{idempotency_key}:{normalize_header(description)}"
    zela_id = "O-" + hashlib.sha256(seed.encode()).hexdigest()[:10].upper()
    table = _table(db, google, condo.id)
    existing = table.find(zela_id)
    if existing is not None:
        db.commit()  # a retried message: report what's there, alert nobody again
        return Report(
            number=existing.values["number"],
            zela_id=zela_id,
            category=existing.values["category"],
            priority=existing.values["priority"],
            emergency=existing.values["priority"]
            == tickets.PRIORITY_LABEL[TicketPriority.EMERGENCY],
            alerted=0,
            duplicate=True,
        )

    cls = tickets.classify(f"{description} {location}", ai_category, ai_priority)
    number = str(tickets.next_number(db, condo.id, "occurrence"))
    now = people.local_timestamp(condo)
    suggestion = (
        f"Categoria: {tickets.CATEGORY_LABEL.get(ai_category, '-') if ai_category else '-'} · "
        f"Prioridade: {tickets.PRIORITY_LABEL.get(ai_priority, '-') if ai_priority else '-'}"
    )
    table.append(
        zela_id,
        {
            "number": number,
            "opened_at": now,
            "type": TYPE_LABEL[type_],
            "description": description,
            "location": location,
            "block": membership.block if membership else "",
            "unit": membership.unit if membership else "",
            "category": tickets.CATEGORY_LABEL[cls.category],
            "priority": tickets.PRIORITY_LABEL[cls.priority],
            "ai_suggestion": suggestion,
            "status": STATUS_LABEL["aberta"],
            "reported_by": person.name or person.role_label,
            "reported_by_id": _reporter_id(person, membership),
            "updated_at": now,
        },
    )
    emergency = cls.priority == TicketPriority.EMERGENCY
    audit.record(
        db,
        organization_id=condo.organization_id,
        condominium_id=condo.id,
        actor_type=ActorType.AGENT,
        actor_id=actor_id,
        action="occurrence.reported",
        entity_type="sheet_row",
        entity_id=None,
        data={
            "register": "occurrences",
            "zela_id": zela_id,
            "number": number,
            "category": str(cls.category),
            "priority": str(cls.priority),
            "emergency_by_rule": cls.emergency_by_rule,
        },
    )
    db.commit()  # the row is in the sheet; record it and release the lock
    alerted = 0
    if emergency:
        alerted = alert_emergency(
            db,
            publisher,
            condo,
            number=number,
            zela_id=zela_id,
            summary=description,
            location=location or (membership.label if membership else "não informado"),
            opened=now,
            person=person,
            membership=membership,
        )
    return Report(
        number=number,
        zela_id=zela_id,
        category=tickets.CATEGORY_LABEL[cls.category],
        priority=tickets.PRIORITY_LABEL[cls.priority],
        emergency=emergency,
        alerted=alerted,
        duplicate=False,
    )


def _reporter_id(person: Person, membership: Membership | None) -> str:
    if membership and membership.zela_id:
        return membership.zela_id
    return next((m.zela_id for m in person.memberships if m.zela_id), "")


def alert_emergency(
    db: Session,
    publisher: JobPublisher,
    condo: Condominium,
    *,
    number: str,
    zela_id: str,
    summary: str,
    location: str,
    opened: str,
    person: Person,
    membership: Membership | None,
) -> int:
    """WhatsApp alert to every on-call contact and the confirmed manager, except the
    reporter. Returns how many were queued."""
    recipients = list(
        db.scalars(
            select(EmergencyContact.phone_e164).where(EmergencyContact.condominium_id == condo.id)
        )
    )
    if condo.manager_phone_e164 and condo.manager_phone_confirmed_at:
        recipients.append(condo.manager_phone_e164)
    reporter = person.first_name or person.role_label
    if membership:
        reporter += f" ({membership.label})"
    queued = 0
    for phone in dict.fromkeys(recipients):  # deduplicated, in order
        if phone == person.phone:
            continue
        notifications.enqueue(
            db,
            publisher,
            condominium_id=condo.id,
            recipient_e164=phone,
            template=OCCURRENCE_EMERGENCY.name,
            params={
                "condominium": condo.name,
                "summary": summary,
                "location": location,
                "number": number,
                "time": opened[-5:],
                "reporter": reporter,
            },
            idempotency_key=f"occurrence:{zela_id}:emergency:{phone}",
        )
        queued += 1
    return queued


def mine(db: Session, google: Google, condo: Condominium, person: Person) -> list[Row]:
    ids = {m.zela_id for m in person.memberships if m.zela_id}
    if not ids:
        return []
    table = _table(db, google, condo.id, lock=False)
    rows = [r for r in table.rows if r.values["reported_by_id"] in ids]
    return list(reversed(rows))[:10]


def find(table: Table, *, only_open: bool, query: str, limit: int = 15) -> list[Row]:
    q = normalize_header(query)
    rows = []
    for row in reversed(table.rows):
        if only_open and not is_open(row):
            continue
        text = normalize_header(
            " ".join(row.values[k] for k in ("number", "description", "location", "block", "unit"))
        )
        if q and q not in text:
            continue
        rows.append(row)
    return rows[:limit]


def by_number(table: Table, number: str) -> Row | None:
    return next((r for r in table.rows if r.values["number"] == str(number)), None)


def notify_reporter(
    db: Session,
    google: Google,
    publisher: JobPublisher,
    condo: Condominium,
    row: Row,
    note: str,
) -> bool:
    """Queues the status update to whoever reported it, guarded on the sheet's status."""
    reporter_id = row.values["reported_by_id"]
    if not reporter_id:
        return False
    people_table = drive.open_table(db, google, condo.id, RegisterKind.PEOPLE, lock=False)
    reporter = people_table.find(reporter_id)
    phone = people.phone_of(reporter) if reporter is not None else None
    if phone is None or not people.is_active(reporter):
        return False
    status = row.values["status"]
    update = REPORTER_MESSAGE.get(status, f"status: {status}.")
    if note:
        update = f"{update} {note}"
    notifications.enqueue(
        db,
        publisher,
        condominium_id=condo.id,
        recipient_e164=phone,
        template=OCCURRENCE_UPDATE.name,
        params={"number": row.values["number"], "summary": summary_of(row), "update": update},
        idempotency_key=f"occurrence:{row.zela_id}:status:{status}:{row.values['updated_at']}",
        guard={"occurrence_status": {"number": row.values["number"], "status": status}},
    )
    return True


def status_still(
    db: Session, google: Google, condominium_id: uuid.UUID, number: str, status: str
) -> bool:
    """Notification guard: is the occurrence still in the status being announced?
    Raises drive.RegisterUnavailable if the sheet can't be read (retry later)."""
    row = by_number(_table(db, google, condominium_id, lock=False), number)
    return row is not None and row.values["status"] == status
