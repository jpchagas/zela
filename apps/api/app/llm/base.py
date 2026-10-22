"""Provider-neutral contract for the agent layer (ADR 0007).

The agent talks to an `LLMSession`, which keeps the provider's native message list for
one agent run. Provider-specific blocks (e.g. thinking) stay inside the adapter and are
passed back unchanged, which some providers require.
"""

import enum
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    call_id: str
    content: str
    is_error: bool = False


class StopReason(str, enum.Enum):
    END = "end"
    TOOL_USE = "tool_use"
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"
    OTHER = "other"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall]
    stop: StopReason
    usage: Usage = field(default_factory=Usage)
    model: str | None = None


class LLMError(Exception):
    """The provider could not produce a turn (after the SDK's own retries)."""


class LLMSession(Protocol):
    def next_turn(self) -> Turn: ...

    def add_tool_outcomes(self, outcomes: list[ToolOutcome]) -> None: ...


class LLMClient(Protocol):
    model: str

    def start(
        self,
        *,
        system: str,
        context: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> LLMSession:
        """Begin one agent run.

        `system` must be byte-identical across runs (it is cached). `context` carries
        per-run facts such as the condominium name and current time.
        """
        ...
