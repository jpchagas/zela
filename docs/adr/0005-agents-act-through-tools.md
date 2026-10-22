# 0005: Agents act only through validated backend tools

**Status:** Accepted (2026-10-22). Contract in `app/agents/tools.py`. Tools arrive per milestone.

## Context
PDD §6: agents must complete real tasks without ever bypassing authorization, fabricating
results, or being steered by prompt injection.

## Decision
- The orchestrator builds a `ToolContext` (condominium, enrolled resident, conversation,
  agent run, idempotency key) from verified data. The model never supplies the actor or
  the tenant.
- Tools are classes with a Pydantic args model. They validate inputs, call
  `app/services` (inheriting tenant scoping and audit events), and return a `ToolResult`
  describing what was **committed**. No tool executes model-written SQL.
- Consequential tools set `requires_confirmation`. The orchestrator gets an explicit
  "yes" to a summarized action before calling them.
- AI-proposed values (ticket category or priority) are stored in `ai_suggested_*`
  columns, separate from confirmed values, and the UI styles them as suggestions.
- Every run is stored in `agent_runs` with its tool calls, outcomes and token counts.
- Start with one orchestrated concierge flow plus capabilities (knowledge, maintenance,
  visitors). Add separate agents only when a responsibility earns it (PDD §6.1).

## Consequences
- Each new tool needs unit tests, an isolation test, and AI eval conversations
  (PDD §17) before it is enabled.
