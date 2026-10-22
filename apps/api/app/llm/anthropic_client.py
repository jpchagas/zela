"""Claude adapter for the LLM contract, using the Anthropic Python SDK."""

from typing import Any

import anthropic

from app.llm.base import (
    ChatMessage,
    LLMError,
    StopReason,
    ToolCall,
    ToolOutcome,
    ToolSpec,
    Turn,
    Usage,
)

# Re-runs a classifier-declined request on Anthropic's recommended model for that
# refusal category, instead of returning the refusal to us.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_STOP = {
    "end_turn": StopReason.END,
    "tool_use": StopReason.TOOL_USE,
    "refusal": StopReason.REFUSAL,
    "max_tokens": StopReason.MAX_TOKENS,
}


class AnthropicLLM:
    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str,
        effort: str,
        max_tokens: int = 16000,
    ):
        self._client = client
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def start(
        self,
        *,
        system: str,
        context: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> "AnthropicSession":
        return AnthropicSession(self, system=system, context=context, history=history, tools=tools)


class AnthropicSession:
    def __init__(
        self,
        llm: AnthropicLLM,
        *,
        system: str,
        context: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
    ):
        self._llm = llm
        # Cache order is tools -> system -> messages. The breakpoint on the static system
        # block caches tools + instructions across every conversation; per-run context
        # follows it so it never invalidates that prefix.
        self._system = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": context},
        ]
        self._tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
        self.messages: list[dict[str, Any]] = [{"role": m.role, "content": m.text} for m in history]

    def next_turn(self) -> Turn:
        llm = self._llm
        try:
            response = llm._client.beta.messages.create(
                model=llm.model,
                max_tokens=llm._max_tokens,
                output_config={"effort": llm._effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                # Also cache the growing conversation, which the tool loop re-sends.
                cache_control={"type": "ephemeral"},
                system=self._system,
                tools=self._tools,
                messages=self.messages,
            )
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API {exc.status_code} (request {exc.request_id})") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Anthropic connection error: {type(exc).__name__}") from exc

        # Append the full content unchanged: thinking and fallback blocks must round-trip.
        self.messages.append({"role": "assistant", "content": response.content})

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))

        usage = response.usage
        return Turn(
            text="\n".join(p for p in text_parts if p.strip()).strip(),
            tool_calls=tool_calls,
            stop=_STOP.get(response.stop_reason or "", StopReason.OTHER),
            model=response.model,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
            ),
        )

    def add_tool_outcomes(self, outcomes: list[ToolOutcome]) -> None:
        # All results for one assistant turn go back in a single user message.
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": o.call_id,
                        "content": o.content,
                        "is_error": o.is_error,
                    }
                    for o in outcomes
                ],
            }
        )
