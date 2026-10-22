import uuid
from datetime import datetime
from typing import Any

from app.models.enums import ActorType
from app.schemas.common import ORMModel


class AuditEventOut(ORMModel):
    id: uuid.UUID
    actor_type: ActorType
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    data: dict[str, Any]
    created_at: datetime
