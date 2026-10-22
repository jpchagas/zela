import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.rbac.context import CondoContext

T = TypeVar("T")


def get_scoped(db: Session, model: type[T], ctx: CondoContext, entity_id: uuid.UUID) -> T:
    """Load a condominium-owned row, or 404 if it belongs to any other condominium."""
    obj = db.scalar(
        select(model).where(
            model.id == entity_id,  # type: ignore[attr-defined]
            model.condominium_id == ctx.condominium_id,  # type: ignore[attr-defined]
        )
    )
    if obj is None:
        raise NotFound(f"{model.__name__} not found")
    return obj


def flush_or_conflict(db: Session, message: str) -> None:
    """Flush pending changes, turning constraint violations into a 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(message) from exc
