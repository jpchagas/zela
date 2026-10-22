# 0007: Provider-neutral LLM layer, Claude as the first adapter

**Status:** Accepted (2026-10-22)

## Context
The PDD lists OpenAI as a candidate, not a decision. The agent layer must not depend on one
vendor's API shapes, but each vendor has rules the adapter must follow (e.g. Claude's
thinking blocks must be passed back unchanged within a tool loop).

## Decision
- The agent depends only on `app/llm/base.py`: `LLMClient.start(system, context, history,
  tools)` returns an `LLMSession` with `next_turn()` and `add_tool_outcomes()`. The
  session keeps the provider's native message list, so provider-specific blocks never leak
  into agent code.
- First adapter: Anthropic (`app/llm/anthropic_client.py`), model `claude-opus-5-5`.
  - `output_config.effort` set explicitly (`LLM_EFFORT`, default `medium`). Lower to `low`
    if latency matters and evals hold.
  - Prompt caching: a breakpoint on the static system prompt (tools + instructions are
    shared by every conversation), with per-run context after it, plus automatic caching of
    the conversation for the tool loop. The system prompt lives in
    `app/agents/prompts/concierge_system.md` and must stay byte-identical across runs.
  - `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`): a classifier-declined
    request is retried server-side on Anthropic's recommended model for that category.
    A final `refusal` still gets a safe canned reply.
  - No forced `tool_choice` (rejected by this model). Tool use is steered by the prompt,
    and arguments are validated by each tool's Pydantic model (`extra="forbid"`).
  - SDK timeout 45 s, 2 retries. Any remaining failure becomes `LLMError`, and the resident
    gets an apology instead of silence.
- `LLM_PROVIDER=scripted` uses a rule-based responder for local work without an API key.
  Tests use `ScriptedLLM`, which plays back turns.

## Consequences
- A second provider means one new adapter, plus running the eval suite against it.
- Behavioural guarantees are checked by `tests/evals` (opt-in, calls the real model) and
  by deterministic tests with `ScriptedLLM`.
