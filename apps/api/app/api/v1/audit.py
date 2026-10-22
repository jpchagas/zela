import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.audit import AuditEventOut
from app.schemas.common import Page
from app.services import audit

router = APIRouter(prefix="/condominiums/{condominium_id}/audit-events", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut])
def list_audit_events(
    entity_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CondoContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: Session = Depends(get_db),
):
    items = audit.list_events(db, ctx, entity_id=entity_id, limit=limit, offset=offset)
    return Page(items=items, limit=limit, offset=offset)
