"""Maintenance tickets (PDD §5.6).

The model only *suggests* a category and priority. `classify()` is the deterministic
validation that decides the stored values (ADR 0009), and the emergency procedure runs
from the stored priority, never from chat text alone.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidInput
from app.core.jobs import JobPublisher
from app.models import (
    Building,
    Condominium,
    CondominiumCounter,
    Conversation,
    EmergencyContact,
    MaintenanceTicket,
    OrganizationMembership,
    Resident,
    ResidentPhone,
    StaffMembership,
    TicketEvent,
    Unit,
    User,
)
from app.models.enums import ActorType, TicketCategory, TicketPriority, TicketStatus
from app.rbac.context import CondoContext
from app.services import audit, conversations, notifications
from app.services.common import get_scoped

CATEGORY_LABEL = {
    TicketCategory.ELEVATORS: "Elevadores",
    TicketCategory.GATES_ACCESS: "Portões e acesso",
    TicketCategory.PLUMBING: "Hidráulica",
    TicketCategory.ELECTRICAL: "Elétrica",
    TicketCategory.CLEANING: "Limpeza",
    TicketCategory.SECURITY: "Segurança",
    TicketCategory.COMMON_AREAS: "Áreas comuns",
    TicketCategory.NOISE: "Barulho e convivência",
    TicketCategory.OTHER: "Outros",
}
PRIORITY_LABEL = {
    TicketPriority.LOW: "Baixa",
    TicketPriority.NORMAL: "Normal",
    TicketPriority.HIGH: "Alta",
    TicketPriority.EMERGENCY: "Emergência",
}
STATUS_LABEL = {
    TicketStatus.OPEN: "Aberto",
    TicketStatus.IN_PROGRESS: "Em andamento",
    TicketStatus.WAITING_INFORMATION: "Aguardando informações",
    TicketStatus.WAITING_EXTERNAL: "Aguardando serviço externo",
    TicketStatus.RESOLVED: "Resolvido",
    TicketStatus.CLOSED: "Encerrado",
}
_RANK = {
    TicketPriority.LOW: 0,
    TicketPriority.NORMAL: 1,
    TicketPriority.HIGH: 2,
    TicketPriority.EMERGENCY: 3,
}

# Matched against lowercase text with accents removed.
EMERGENCY_PATTERNS = [
    r"\b(vazamento|cheiro|escape)\s+(forte\s+)?de\s+gas\b",
    r"\bgas\b.{0,30}\b(vazando|vazamento)\b",
    r"\bincendio\b",
    r"\bfogo\b",
    r"\bfumaca\b",
    r"\b(alagamento|alagad[oa]|inundacao|inundad[oa])\b",
    r"\bchoque eletrico\b",
    r"\bcurto[- ]?circuito\b",
    r"\b(pres[oa]s?)\b.{0,30}\belevador\b|\belevador\b.{0,30}\b(pres[oa]s?)\b",
    r"\b(ferid[oa]s?|desmai\w*|inconsciente)\b",
    r"\b(desabamento|desabou|risco de queda)\b",
]
_EMERGENCY = re.compile("|".join(EMERGENCY_PATTERNS))

# Moves staff may make. Closed is final; resolved can be reopened.
TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_INFORMATION,
        TicketStatus.WAITING_EXTERNAL,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.IN_PROGRESS: {
        TicketStatus.WAITING_INFORMATION,
        TicketStatus.WAITING_EXTERNAL,
        TicketStatus.RESOLVED,
    },
    TicketStatus.WAITING_INFORMATION: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.WAITING_EXTERNAL: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.IN_PROGRESS},
    TicketStatus.CLOSED: set(),
}
OPEN_STATUSES = (
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_INFORMATION,
    TicketStatus.WAITING_EXTERNAL,
)
# What residents are told when the status changes.
RESIDENT_STATUS_MESSAGE = {
    TicketStatus.IN_PROGRESS: "a equipe começou a cuidar do problema.",
    TicketStatus.WAITING_INFORMATION: "a equipe precisa de mais informações. Responda por aqui.",
    TicketStatus.WAITING_EXTERNAL: "aguardando um prestador de serviço externo.",
    TicketStatus.RESOLVED: "o problema foi marcado como resolvido. Se continuar, avise por aqui.",
    TicketStatus.CLOSED: "o chamado foi encerrado.",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


@dataclass(frozen=True)
class Classification:
    category: TicketCategory
    priority: TicketPriority
    emergency_by_rule: bool


def classify(
    text: str, ai_category: TicketCategory | None, ai_priority: TicketPriority | None
) -> Classification:
    """Deterministic validation of the model's suggestion.

    - Category: any listed value is accepted; anything else becomes OTHER.
    - Priority: emergency keywords set EMERGENCY regardless of the model. Otherwise the
      model's suggestion is used, defaulting to NORMAL. The model may raise a report to
      EMERGENCY on its own: a missed emergency costs far more than a false alert.
    """
    category = ai_category if isinstance(ai_category, TicketCategory) else TicketCategory.OTHER
    by_rule = bool(_EMERGENCY.search(_plain(text)))
    floor = TicketPriority.EMERGENCY if by_rule else TicketPriority.NORMAL
    suggested = ai_priority if isinstance(ai_priority, TicketPriority) else TicketPriority.NORMAL
    priority = suggested if _RANK[suggested] > _RANK[floor] else floor
    if not by_rule and suggested == TicketPriority.LOW:
        priority = TicketPriority.LOW
    return Classification(category, priority, by_rule)


def next_number(db: Session, condominium_id: uuid.UUID, name: str = "ticket") -> int:
    return db.scalar(
        insert(CondominiumCounter)
        .values(condominium_id=condominium_id, name=name, value=1)
        .on_conflict_do_update(
            index_elements=["condominium_id", "name"],
            set_={"value": CondominiumCounter.value + 1},
        )
        .returning(CondominiumCounter.value)
    )


def unit_label(db: Session, unit_id: uuid.UUID | None) -> str | None:
    if unit_id is None:
        return None
    row = db.execute(
        select(Unit.identifier, Building.name)
        .outerjoin(Building, Building.id == Unit.building_id)
        .where(Unit.id == unit_id)
    ).first()
    if row is None:
        return None
    return f"{row[1]} · {row[0]}" if row[1] else row[0]


# --- Created by a resident through the concierge -----------------------------------------


def create_for_resident(
    db: Session,
    publisher: JobPublisher,
    *,
    condominium: Condominium,
    resident: Resident,
    conversation: Conversation | None,
    unit_id: uuid.UUID | None,
    title: str,
    description: str,
    location: str | None,
    ai_category: TicketCategory | None,
    ai_priority: TicketPriority | None,
    idempotency_key: str,
    agent_run_id: uuid.UUID | None,
) -> tuple[MaintenanceTicket, bool]:
    """Create a ticket (or return the one already created for this key)."""
    existing = db.scalar(
        select(MaintenanceTicket).where(
            MaintenanceTicket.condominium_id == condominium.id,
            MaintenanceTicket.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    decided = classify(f"{title}\n{description}\n{location or ''}", ai_category, ai_priority)
    ticket = MaintenanceTicket(
        condominium_id=condominium.id,
        number=next_number(db, condominium.id),
        unit_id=unit_id,
        reporter_resident_id=resident.id,
        conversation_id=conversation.id if conversation else None,
        title=title.strip(),
        description=description.strip(),
        location=(location or "").strip() or None,
        category=decided.category,
        priority=decided.priority,
        ai_suggested_category=ai_category,
        ai_suggested_priority=ai_priority,
        status=TicketStatus.OPEN,
        idempotency_key=idempotency_key,
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketEvent(
            condominium_id=condominium.id,
            ticket_id=ticket.id,
            event_type="created",
            to_status=TicketStatus.OPEN,
            actor_type=ActorType.AGENT,
            actor_id=agent_run_id,
            note=f"Aberto pelo morador via WhatsApp (agente {agent_run_id}).",
        )
    )
    audit.record(
        db,
        organization_id=condominium.organization_id,
        condominium_id=condominium.id,
        actor_type=ActorType.AGENT,
        actor_id=agent_run_id,
        action="ticket.created",
        entity_type="maintenance_ticket",
        entity_id=ticket.id,
        data={
            "reporter_resident_id": str(resident.id),
            "category": decided.category.value,
            "priority": decided.priority.value,
            "ai_category": ai_category.value if ai_category else None,
            "ai_priority": ai_priority.value if ai_priority else None,
        },
    )
    db.commit()

    if ticket.priority == TicketPriority.EMERGENCY:
        run_emergency_procedure(db, publisher, condominium, ticket, conversation)
    return ticket, True


def run_emergency_procedure(
    db: Session,
    publisher: JobPublisher,
    condominium: Condominium,
    ticket: MaintenanceTicket,
    conversation: Conversation | None,
) -> int:
    """Escalate the conversation and alert every on-call contact. Returns how many."""
    if conversation is not None:
        conversations.escalate(
            db,
            condominium,
            conversation,
            reason=f"Emergência: chamado #{ticket.number} ({ticket.title})",
            actor_type=ActorType.SYSTEM,
            actor_id=None,
        )
    contacts = db.scalars(
        select(EmergencyContact).where(EmergencyContact.condominium_id == condominium.id)
    ).all()
    opened = ticket.created_at.astimezone(ZoneInfo(condominium.timezone))
    for contact in contacts:
        notifications.enqueue(
            db,
            publisher,
            condominium_id=condominium.id,
            recipient_e164=contact.phone_e164,
            template="zela_emergency_alert",
            params={
                "condominium": condominium.name,
                "summary": ticket.title,
                "location": ticket.location or unit_label(db, ticket.unit_id) or "não informado",
                "number": str(ticket.number),
                "time": f"{opened:%H:%M}",
            },
            idempotency_key=f"ticket:{ticket.id}:emergency:{contact.id}",
            entity_type="maintenance_ticket",
            entity_id=ticket.id,
        )
    db.add(
        TicketEvent(
            condominium_id=condominium.id,
            ticket_id=ticket.id,
            event_type="emergency_alerted",
            actor_type=ActorType.SYSTEM,
            note=(
                f"Plantão alertado: {len(contacts)} contato(s)."
                if contacts
                else "Nenhum contato de plantão configurado: ninguém foi alertado por WhatsApp."
            ),
        )
    )
    db.commit()
    return len(contacts)


def list_for_resident(
    db: Session, condominium_id: uuid.UUID, resident_id: uuid.UUID, number: int | None
) -> list[MaintenanceTicket]:
    stmt = select(MaintenanceTicket).where(
        MaintenanceTicket.condominium_id == condominium_id,
        MaintenanceTicket.reporter_resident_id == resident_id,
    )
    if number is not None:
        stmt = stmt.where(MaintenanceTicket.number == number)
    return list(db.scalars(stmt.order_by(MaintenanceTicket.created_at.desc()).limit(5)))


# --- Staff operations -------------------------------------------------------------------------


@dataclass
class TicketRow:
    ticket: MaintenanceTicket
    unit_label: str | None
    reporter_name: str | None
    assignee_email: str | None


def list_tickets(
    db: Session,
    ctx: CondoContext,
    *,
    open_only: bool,
    status: TicketStatus | None,
    priority: TicketPriority | None,
    category: TicketCategory | None,
    q: str | None,
    limit: int,
    offset: int,
) -> list[TicketRow]:
    stmt = (
        select(MaintenanceTicket, Resident.full_name, User.email)
        .outerjoin(Resident, Resident.id == MaintenanceTicket.reporter_resident_id)
        .outerjoin(User, User.id == MaintenanceTicket.assignee_user_id)
        .where(MaintenanceTicket.condominium_id == ctx.condominium_id)
    )
    if open_only:
        stmt = stmt.where(MaintenanceTicket.status.in_(OPEN_STATUSES))
    if status is not None:
        stmt = stmt.where(MaintenanceTicket.status == status)
    if priority is not None:
        stmt = stmt.where(MaintenanceTicket.priority == priority)
    if category is not None:
        stmt = stmt.where(MaintenanceTicket.category == category)
    if q:
        if q.lstrip("#").isdigit():
            stmt = stmt.where(MaintenanceTicket.number == int(q.lstrip("#")))
        else:
            pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            stmt = stmt.where(
                or_(
                    MaintenanceTicket.title.ilike(pattern, escape="\\"),
                    MaintenanceTicket.description.ilike(pattern, escape="\\"),
                )
            )
    priority_order = func.array_position(
        ["emergency", "high", "normal", "low"], MaintenanceTicket.priority
    )
    stmt = (
        stmt.order_by(priority_order, MaintenanceTicket.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        TicketRow(t, unit_label(db, t.unit_id), name, email) for t, name, email in db.execute(stmt)
    ]


def get_detail(
    db: Session, ctx: CondoContext, ticket_id: uuid.UUID
) -> tuple[TicketRow, list[TicketEvent]]:
    ticket = get_scoped(db, MaintenanceTicket, ctx, ticket_id)
    reporter = (
        db.get(Resident, ticket.reporter_resident_id) if ticket.reporter_resident_id else None
    )
    assignee = db.get(User, ticket.assignee_user_id) if ticket.assignee_user_id else None
    events = db.scalars(
        select(TicketEvent)
        .where(TicketEvent.condominium_id == ctx.condominium_id, TicketEvent.ticket_id == ticket.id)
        .order_by(TicketEvent.created_at)
    ).all()
    row = TicketRow(
        ticket,
        unit_label(db, ticket.unit_id),
        reporter.full_name if reporter else None,
        assignee.email if assignee else None,
    )
    return row, list(events)


def change_status(
    db: Session,
    ctx: CondoContext,
    publisher: JobPublisher,
    ticket_id: uuid.UUID,
    to_status: TicketStatus,
    note: str | None,
) -> MaintenanceTicket:
    ticket = get_scoped(db, MaintenanceTicket, ctx, ticket_id)
    if to_status not in TRANSITIONS[ticket.status]:
        raise Conflict(f"Cannot move a ticket from {ticket.status} to {to_status}")
    previous = ticket.status
    ticket.status = to_status
    if to_status == TicketStatus.RESOLVED:
        ticket.resolved_at = _now()
    elif to_status == TicketStatus.CLOSED:
        ticket.closed_at = _now()
        ticket.resolved_at = ticket.resolved_at or ticket.closed_at
    elif previous == TicketStatus.RESOLVED:
        ticket.resolved_at = None  # reopened
    event = TicketEvent(
        condominium_id=ctx.condominium_id,
        ticket_id=ticket.id,
        event_type="status_changed",
        from_status=previous,
        to_status=to_status,
        note=(note or "").strip() or None,
        is_internal=False,
        actor_type=ActorType.USER,
        actor_id=ctx.user.id,
    )
    db.add(event)
    audit.record_user_action(
        db,
        ctx,
        "ticket.status_changed",
        "maintenance_ticket",
        ticket.id,
        **{"from": previous.value, "to": to_status.value},
    )
    db.commit()

    update = RESIDENT_STATUS_MESSAGE[to_status]
    if event.note:
        update = f"{update} Mensagem da equipe: {event.note}"
    _notify_reporter(
        db,
        publisher,
        ticket,
        update=update,
        key=f"ticket:{ticket.id}:event:{event.id}",
        guard={"ticket_status": to_status.value},
    )
    return ticket


def add_note(
    db: Session,
    ctx: CondoContext,
    publisher: JobPublisher,
    ticket_id: uuid.UUID,
    body: str,
    *,
    public: bool,
) -> TicketEvent:
    ticket = get_scoped(db, MaintenanceTicket, ctx, ticket_id)
    if ticket.status == TicketStatus.CLOSED and public:
        raise Conflict("Ticket is closed")
    event = TicketEvent(
        condominium_id=ctx.condominium_id,
        ticket_id=ticket.id,
        event_type="note",
        note=body.strip(),
        is_internal=not public,
        actor_type=ActorType.USER,
        actor_id=ctx.user.id,
    )
    db.add(event)
    audit.record_user_action(
        db, ctx, "ticket.note_added", "maintenance_ticket", ticket.id, public=public
    )
    db.commit()
    if public:
        _notify_reporter(
            db, publisher, ticket, update=event.note, key=f"ticket:{ticket.id}:event:{event.id}"
        )
    return event


def assign(
    db: Session, ctx: CondoContext, ticket_id: uuid.UUID, user_id: uuid.UUID | None
) -> MaintenanceTicket:
    ticket = get_scoped(db, MaintenanceTicket, ctx, ticket_id)
    if user_id is not None and not _is_member(db, ctx, user_id):
        raise InvalidInput("Assignee must be a staff member of this condominium")
    ticket.assignee_user_id = user_id
    db.add(
        TicketEvent(
            condominium_id=ctx.condominium_id,
            ticket_id=ticket.id,
            event_type="assigned" if user_id else "unassigned",
            actor_type=ActorType.USER,
            actor_id=ctx.user.id,
        )
    )
    audit.record_user_action(
        db,
        ctx,
        "ticket.assigned",
        "maintenance_ticket",
        ticket.id,
        assignee_user_id=str(user_id) if user_id else None,
    )
    db.commit()
    return ticket


def reclassify(
    db: Session,
    ctx: CondoContext,
    ticket_id: uuid.UUID,
    category: TicketCategory | None,
    priority: TicketPriority | None,
) -> MaintenanceTicket:
    """Staff confirm or correct category/priority. The AI suggestion stays on record."""
    ticket = get_scoped(db, MaintenanceTicket, ctx, ticket_id)
    changed = {}
    if category is not None and category != ticket.category:
        changed["category"] = [ticket.category.value, category.value]
        ticket.category = category
    if priority is not None and priority != ticket.priority:
        changed["priority"] = [ticket.priority.value, priority.value]
        ticket.priority = priority
    if not changed:
        return ticket
    db.add(
        TicketEvent(
            condominium_id=ctx.condominium_id,
            ticket_id=ticket.id,
            event_type="reclassified",
            note=", ".join(f"{k}: {a} → {b}" for k, (a, b) in changed.items()),
            is_internal=True,
            actor_type=ActorType.USER,
            actor_id=ctx.user.id,
        )
    )
    audit.record_user_action(
        db, ctx, "ticket.reclassified", "maintenance_ticket", ticket.id, **changed
    )
    db.commit()
    return ticket


def _is_member(db: Session, ctx: CondoContext, user_id: uuid.UUID) -> bool:
    staff = db.scalar(
        select(StaffMembership.id).where(
            StaffMembership.user_id == user_id,
            StaffMembership.condominium_id == ctx.condominium_id,
            StaffMembership.revoked_at.is_(None),
        )
    )
    org = db.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == ctx.organization_id,
            OrganizationMembership.revoked_at.is_(None),
        )
    )
    return bool(staff or org)


def _notify_reporter(
    db: Session,
    publisher: JobPublisher,
    ticket: MaintenanceTicket,
    *,
    update: str,
    key: str,
    guard: dict | None = None,
) -> None:
    if ticket.reporter_resident_id is None:
        return
    phone = db.scalar(
        select(ResidentPhone.phone_e164)
        .where(
            ResidentPhone.condominium_id == ticket.condominium_id,
            ResidentPhone.resident_id == ticket.reporter_resident_id,
            ResidentPhone.verified_at.is_not(None),
        )
        .order_by(ResidentPhone.is_primary.desc())
        .limit(1)
    )
    if phone is None:
        return  # no enrolled number; the update stays visible in the ticket history
    notifications.enqueue(
        db,
        publisher,
        condominium_id=ticket.condominium_id,
        recipient_e164=phone,
        resident_id=ticket.reporter_resident_id,
        template="zela_ticket_update",
        params={"number": str(ticket.number), "title": ticket.title, "update": update},
        idempotency_key=key,
        entity_type="maintenance_ticket",
        entity_id=ticket.id,
        guard=guard,
    )


def count_open(db: Session, condominium_id: uuid.UUID) -> tuple[int, int]:
    """(open tickets, open emergencies)"""
    base = (
        select(func.count())
        .select_from(MaintenanceTicket)
        .where(
            MaintenanceTicket.condominium_id == condominium_id,
            MaintenanceTicket.status.in_(OPEN_STATUSES),
        )
    )
    emergencies = base.where(MaintenanceTicket.priority == TicketPriority.EMERGENCY)
    return db.scalar(base) or 0, db.scalar(emergencies) or 0
