"""Contract for the tools agents may call (PDD §6.3). Implementations arrive with their
milestones: get_resident_context and search_condominium_documents (M2–M3),
create/get_maintenance_ticket (M3), create/cancel_visitor_authorization (M4).

Rules every tool follows:
- The actor comes from ToolContext, which the orchestrator builds from the verified,
  enrolled sender. It never comes from model output.
- A tool validates its own inputs and business rules and calls business services, so it
  inherits their tenant scoping and audit events. It never issues raw SQL for the model.
- A tool reports only what was committed. The agent must not claim success otherwise.
"""

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher
from app.llm.base import ToolSpec
from app.models import AgentRun

if TYPE_CHECKING:
    from app.integrations.google.base import Google
    from app.services.people import Person

ArgsT = TypeVar("ArgsT", bound=BaseModel)


@dataclass(frozen=True)
class ToolContext:
    condominium_id: uuid.UUID
    conversation_id: uuid.UUID
    agent_run_id: uuid.UUID
    # Derived from the triggering webhook event, so a retried run can't act twice.
    idempotency_key: str
    # For tools whose effects continue in the background (e.g. emergency alerts).
    publisher: JobPublisher
    # Legacy (Milestone 2–3) concierge: the enrolled resident in Postgres.
    resident_id: uuid.UUID | None = None
    # Sheet-backed condominiums (ADR 0010/0011): the sender as found in Pessoas.
    person: "Person | None" = None
    google: "Google | None" = None


class ToolError(Exception):
    """A business-rule failure the model should see and explain to the resident."""


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    # Safe to show the model; never includes other residents' data.
    error: str | None = None
    # Extra fields for the agent run's tool-call log (no personal data values).
    log: dict[str, Any] = field(default_factory=dict)


PREVIEW_WINDOW = timedelta(minutes=30)


def preview_key(args: BaseModel | dict[str, Any]) -> str:
    """Fingerprint of the (normalized) arguments a confirmation summary was shown for."""
    data = args.model_dump(exclude={"confirmed"}) if isinstance(args, BaseModel) else args
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


def was_previewed(db: Session, ctx: ToolContext, tool_name: str, key: str) -> bool:
    """True if an earlier run in this conversation showed the summary for exactly these
    arguments. The confirming message must come after the summary, so a single message
    can never both request and confirm a consequential action."""
    since = datetime.now(timezone.utc) - PREVIEW_WINDOW
    runs = db.scalars(
        select(AgentRun.tool_calls).where(
            AgentRun.conversation_id == ctx.conversation_id,
            AgentRun.id != ctx.agent_run_id,
            AgentRun.started_at >= since,
        )
    ).all()
    return any(
        entry.get("tool") == tool_name and entry.get("ok") and entry.get("preview_key") == key
        for calls in runs
        for entry in calls
    )


class Tool(ABC, Generic[ArgsT]):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    # Consequential tools need a confirmed summary from the resident before running.
    requires_confirmation: ClassVar[bool] = False

    @abstractmethod
    def run(self, db: Session, ctx: ToolContext, args: ArgsT) -> ToolResult: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.args_model.model_json_schema(),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        # Registration order is fixed, which keeps the cached prompt prefix stable.
        return [t.spec() for t in self._tools.values()]
