# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

Monorepo implemented through Milestone 3 (knowledge base, maintenance tickets, notifications). Read `README.md` for the
quickstart and `docs/adr/` before changing auth, tenancy, webhooks, or agent tooling.

- `apps/api`: FastAPI + SQLAlchemy 2 (sync) + Alembic. Layout: `app/api` (thin routes),
  `app/services` (business logic, commits, audit), `app/rbac` (CondoContext, permissions),
  `app/auth` (token verification), `app/models`, `app/integrations/whatsapp` (receiver,
  sender, templates), `app/integrations/storage.py` (local disk / GCS), `app/workers` (inbound job, sweeper), `app/llm` (provider-neutral interface, Claude
  adapter, scripted stand-ins), `app/agents` (concierge, tools, prompts).
- `apps/web`: Next.js App Router, Tailwind v4, shadcn/ui. UI copy is pt-BR. Brand tokens are in
  `src/app/globals.css`.

## Commands

Local Postgres runs on host port **5433** because 5432 is used by another project. Run these from the repo root:

- `make db`: start Postgres (creates `zela` and `zela_test`)
- `make test`: API tests against real Postgres (`cd apps/api && .venv/bin/pytest tests/test_residents.py::test_name` for one)
- `make lint`: ruff check + format check
- `make migrate`: apply migrations. New migration: `cd apps/api && .venv/bin/alembic revision --autogenerate -m "..."`, then review it. `alembic check` must report no drift.
- `make seed EMAIL=you@example.com`, `make api-dev`, `make web-dev`
- `make web-check`: tsc + eslint + next build. Run `npm run format` in `apps/web` for prettier.
- `make eval`: AI evals in `apps/api/tests/evals`. These call the real model and cost money,
  so ask before running them. They are skipped unless `ZELA_RUN_EVALS=1`.
- `POST /dev/whatsapp/inbound` (development only) simulates a resident message end to end.

This machine's system Python lacks `venv`; the venv was created with Poetry's bundled virtualenv
(`~/.local/share/pypoetry/venv/bin/python -m virtualenv apps/api/.venv`).

## Implementation conventions

- Condominium-scoped routes live under `/v1/condominiums/{condominium_id}/...` and depend on
  `require_permission(...)`. Services load tenant rows only via `get_scoped()` or queries filtered by
  `ctx.condominium_id`. New tenant tables get `condominium_id` plus composite FKs to their parents.
- Foreign or missing tenant resources return 404, never 403. Add each new endpoint to the
  parametrized cases in `tests/test_tenant_isolation.py`.
- Services write audit events in the same transaction via `audit.record_user_action`. Record IDs and
  changed field names, never personal data values.
- Enums are stored as VARCHAR + CHECK via `db_enum()`. Pass `name=` when a table has two columns of the
  same enum.
- Agent capabilities are `Tool` subclasses registered in `app/agents/resident_tools.py`. Tools
  act only for `ToolContext.resident_id` and never take actor or tenant IDs from the model.
  Arguments use Pydantic models with `extra="forbid"`. For each new tool, add a `ScriptedLLM`
  test and an eval case.
- The concierge system prompt (`app/agents/prompts/concierge_system.md`) must stay static
  (it's cached). Per-run facts go in `render_context()`.
- WhatsApp side effects go through `services/conversations.send_outbound` with an idempotency
  key. Never call the sender directly. Proactive messages go through
  `services/notifications.enqueue` with a guard when they announce a state, so they're skipped
  if the state changed before sending. New templates must also be added to
  `docs/whatsapp-templates.md`.
- Background work goes through `JobPublisher` topics handled in `app/workers/runner.py`
  (`whatsapp-inbound`, `document-index`, `notification-send`). Tests use `JOBS_MODE=log` and the
  `publisher` fixture, and run jobs explicitly.
- Ticket category and priority come from `services/tickets.classify()` (ADR 0009). Don't store
  model output directly as confirmed values.
- Postgres search uses the `pt_unaccent` text search config (migration 0003).
- Keep `apps/web/src/lib/types.ts` and `src/lib/permissions.ts` in sync with the API schemas and
  `app/rbac/permissions.py`.

## Stack and open decisions (see PDD §10.2 and §16, ADRs 0001–0006)

- Web: Next.js + TypeScript, Tailwind CSS + shadcn/ui
- API: Python + FastAPI, PostgreSQL, SQLAlchemy + Alembic
- AI: OpenAI API; retrieval through Postgres full-text and/or vector search
- GCP: Cloud Run, Cloud Storage, Pub/Sub, Cloud Logging
- Auth: Firebase Auth (decided, ADR 0002)

Decided on 2026-10-22: Firebase Auth, Postgres as the system of record, Meta Cloud API direct,
and organization → many condominiums. Still open (PDD §16): human support channel, visitor-workflow
integration, first commercial feature, billing, and pilot customer type. Do not hard-code assumptions about
those. Raise them with the user.

## Architectural invariants

These rules come from the design doc and should shape any code written here:

- **Layering:** WhatsApp/Web → API → Auth & RBAC → Business Services → Agent Orchestrator → Approved Tools → DB. The agent layer calls business services and never bypasses their validation or authorization.
- **Agents act only through explicit backend tools** (e.g. `get_resident_context`, `search_condominium_documents`, `create_maintenance_ticket`, `create_visitor_authorization`). They never generate raw DB operations. Each tool validates the actor, the condominium scope, its inputs, and the business rules. A model's interpretation of a request never counts as authorization.
- **The database is the source of truth.** It outranks model output and chat history. Never report an action as successful until it has been persisted. Notifications must reflect the stored state.
- **Multi-tenant isolation:** all tenant data is scoped to an organization and a condominium. Cross-condominium access must be prevented and covered by tests. Residents must never be able to enumerate the directory or see other residents' data through chat.
- **Idempotency:** WhatsApp webhooks are retried and duplicated. Duplicate events must not create duplicate business operations. Verify webhook signatures.
- **Async work:** long tasks like document indexing and notifications go to background workers. The webhook response must not wait on them.
- **Untrusted input:** resident messages and uploaded documents are untrusted, so guard against prompt injection. RAG answers must cite their sources and say plainly when they are uncertain rather than make something up.
- **Auditability:** record tool calls, ticket changes, and security-sensitive actions as audit events or agent runs.
- **AI suggestions** (category, priority) go through deterministic validation. The UI must visually separate AI suggestions from confirmed records.
- **LGPD:** collect only the data needed, set retention for personal data and conversation content, and keep secrets out of ordinary application records.

## Product conventions

- Conversational UX is in Brazilian Portuguese. Keep replies concise, ask only for missing info, confirm consequential actions, and give a reference number for operational requests.
- Brand palette: terracotta `#C96A4A`, charcoal `#1C1C1E`, warm white `#F5F2EE`, sand `#D8C3A5`, deep copper `#A44A2A`. Fonts: Manrope or Inter.
- Definition of done (PDD §17) covers backend authorization, audit events, unit and integration tests, and AI eval tests for AI features.
