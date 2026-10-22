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

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

ArgsT = TypeVar("ArgsT", bound=BaseModel)


@dataclass(frozen=True)
class ToolContext:
    condominium_id: uuid.UUID
    resident_id: uuid.UUID
    conversation_id: uuid.UUID
    agent_run_id: uuid.UUID
    # Derived from the triggering webhook event, so a retried run can't act twice.
    idempotency_key: str


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    # Safe to show the model; never includes other residents' data.
    error: str | None = None


class Tool(ABC, Generic[ArgsT]):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]]
    # Consequential tools need a confirmed summary from the resident before running.
    requires_confirmation: ClassVar[bool] = False

    @abstractmethod
    def run(self, db: Session, ctx: ToolContext, args: ArgsT) -> ToolResult: ...

    def json_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_model.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.json_schema() for t in self._tools.values()]
