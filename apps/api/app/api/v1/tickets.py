import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.models.enums import TicketCategory, TicketPriority, TicketStatus
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.common import Page
from app.schemas.operations import (
    TicketAssign,
    TicketDetail,
    TicketEventOut,
    TicketNoteIn,
    TicketReclassify,
    TicketStatusChange,
    TicketSummary,
)
from app.services import tickets

router = APIRouter(prefix="/condominiums/{condominium_id}/tickets", tags=["tickets"])

can_read = require_permission(Permission.TICKETS_READ)
can_manage = require_permission(Permission.TICKETS_MANAGE)


def _summary(row: tickets.TicketRow) -> dict:
    t = row.ticket
    return {
        "id": t.id,
        "number": t.number,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "category": t.category,
        "ai_suggested_priority": t.ai_suggested_priority,
        "ai_suggested_category": t.ai_suggested_category,
        "unit_label": row.unit_label,
        "location": t.location,
        "reporter_name": row.reporter_name,
        "assignee_email": row.assignee_email,
        "created_at": t.created_at,
        "resolved_at": t.resolved_at,
    }


def _detail(db: Session, ctx: CondoContext, ticket_id: uuid.UUID) -> TicketDetail:
    row, events = tickets.get_detail(db, ctx, ticket_id)
    t = row.ticket
    return TicketDetail(
        **_summary(row),
        description=t.description,
        reporter_resident_id=t.reporter_resident_id,
        conversation_id=t.conversation_id,
        assignee_user_id=t.assignee_user_id,
        closed_at=t.closed_at,
        allowed_transitions=sorted(tickets.TRANSITIONS[t.status], key=list(TicketStatus).index),
        events=[TicketEventOut.model_validate(e) for e in events],
    )


@router.get("", response_model=Page[TicketSummary])
def list_tickets(
    open_only: bool = Query(False, alias="open"),
    status_: TicketStatus | None = Query(None, alias="status"),
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CondoContext = Depends(can_read),
    db: Session = Depends(get_db),
):
    rows = tickets.list_tickets(
        db,
        ctx,
        open_only=open_only,
        status=status_,
        priority=priority,
        category=category,
        q=q,
        limit=limit,
        offset=offset,
    )
    return Page(items=[TicketSummary(**_summary(r)) for r in rows], limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: uuid.UUID, ctx: CondoContext = Depends(can_read), db: Session = Depends(get_db)
):
    return _detail(db, ctx, ticket_id)


@router.post("/{ticket_id}/status", response_model=TicketDetail)
def change_status(
    ticket_id: uuid.UUID,
    body: TicketStatusChange,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    tickets.change_status(db, ctx, publisher, ticket_id, body.status, body.note)
    return _detail(db, ctx, ticket_id)


@router.post("/{ticket_id}/notes", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
def add_note(
    ticket_id: uuid.UUID,
    body: TicketNoteIn,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    tickets.add_note(db, ctx, publisher, ticket_id, body.body, public=body.public)
    return _detail(db, ctx, ticket_id)


@router.put("/{ticket_id}/assignee", response_model=TicketDetail)
def assign(
    ticket_id: uuid.UUID,
    body: TicketAssign,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    tickets.assign(db, ctx, ticket_id, body.user_id)
    return _detail(db, ctx, ticket_id)


@router.put("/{ticket_id}/classification", response_model=TicketDetail)
def reclassify(
    ticket_id: uuid.UUID,
    body: TicketReclassify,
    ctx: CondoContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    tickets.reclassify(db, ctx, ticket_id, body.category, body.priority)
    return _detail(db, ctx, ticket_id)
