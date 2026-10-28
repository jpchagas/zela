"""The Claude adapter's request shape, without network calls."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.llm.anthropic_client import FALLBACK_BETA, AnthropicLLM
from app.llm.base import ChatMessage, LLMError, StopReason, ToolOutcome, ToolSpec


def _response(content, stop_reason="end_turn"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=None,
        ),
    )


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _llm(responses, model="claude-opus-5-5"):
    messages = FakeMessages(responses)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return AnthropicLLM(client, model=model, effort="medium"), messages


TOOLS = [ToolSpec("get_resident_context", "desc", {"type": "object", "properties": {}})]


def test_request_shape_and_tool_loop():
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    tool_use = SimpleNamespace(type="tool_use", id="toolu_1", name="get_resident_context", input={})
    text = SimpleNamespace(type="text", text="Você mora no 101.")
    llm, messages = _llm([_response([thinking, tool_use], "tool_use"), _response([text])])
    session = llm.start(
        system="STATIC",
        context="Condomínio: X",
        history=[ChatMessage("user", "qual minha unidade?")],
        tools=TOOLS,
    )

    turn = session.next_turn()
    assert turn.stop == StopReason.TOOL_USE
    assert turn.tool_calls[0].name == "get_resident_context"
    assert turn.usage.cache_read_tokens == 100
    session.add_tool_outcomes([ToolOutcome("toolu_1", '{"unit": "101"}')])
    final = session.next_turn()
    assert final.text == "Você mora no 101." and final.stop == StopReason.END

    first = messages.calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["output_config"] == {"effort": "medium"}
    assert first["betas"] == [FALLBACK_BETA] and first["fallbacks"] == "default"
    assert first["system"][0] == {
        "type": "text",
        "text": "STATIC",
        "cache_control": {"type": "ephemeral"},
    }
    assert first["system"][1] == {"type": "text", "text": "Condomínio: X"}
    assert "tool_choice" not in first and "thinking" not in first

    second_messages = messages.calls[1]["messages"]
    # The assistant turn goes back unchanged, thinking block included.
    assert second_messages[1]["content"][0] is thinking
    assert second_messages[2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": '{"unit": "101"}',
            "is_error": False,
        }
    ]


def test_haiku_requests_omit_fallbacks():
    llm, messages = _llm([_response([])], model="claude-haiku-5-5")
    llm.start(system="S", context="C", history=[ChatMessage("user", "x")], tools=TOOLS).next_turn()
    call = messages.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert "betas" not in call and "fallbacks" not in call


def test_refusal_maps_to_refusal_stop():
    llm, _ = _llm([_response([], "refusal")])
    turn = llm.start(
        system="S", context="C", history=[ChatMessage("user", "x")], tools=TOOLS
    ).next_turn()
    assert turn.stop == StopReason.REFUSAL


def test_api_errors_become_llm_errors():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    llm, _ = _llm([anthropic.APIConnectionError(request=request)])
    session = llm.start(system="S", context="C", history=[ChatMessage("user", "x")], tools=TOOLS)
    with pytest.raises(LLMError):
        session.next_turn()
