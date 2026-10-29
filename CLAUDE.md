# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

**Changing direction (ADR 0010).** Zela is a low-cost,
WhatsApp-first product. Everyone uses WhatsApp: manager, owners, residents and staff. The
condominium's records are Google Sheets in the manager's Drive. The website is setup only,
for the manager: list their condominiums, add one, connect its WhatsApp and Drive. Postgres
keeps only setup and plumbing data.

The code below is still the Milestone 1–3 build: a dashboard, with Postgres as the record. It
is being reworked in phases. New code follows ADR 0010. Don't add features to the dashboard
work screens or to the Postgres business tables. Read `README.md` for the quickstart and
`docs/adr/` before changing auth, tenancy, webhooks, storage or agent tooling.

- `apps/api`: FastAPI + SQLAlchemy 2 (sync) + Alembic. Layout: `app/api` (thin routes),
  `app/services` (business logic, commits, audit), `app/rbac` (CondoContext, permissions),
  `app/auth` (token verification), `app/models`, `app/integrations/whatsapp` (receiver,
  sender, templates), `app/integrations/google` (OAuth, Drive and Sheets client, plus
  `FakeGoogle`), `app/registers` (sheet specs, `Table`), `app/integrations/storage.py` (local
  disk / GCS), `app/workers` (inbound job, sweeper), `app/llm` (provider-neutral interface,
  Claude adapter, scripted stand-ins), `app/agents` (concierge, tools, prompts).
- `apps/web` is now setup only: `app/page.tsx` lists the user's condominiums and lets
  organization owners and admins add one; `app/c/[condoId]/page.tsx` is one condominium's
  setup (WhatsApp, Google Drive, manager's number, on-call contacts).
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
- Agent capabilities are `Tool` subclasses. Sheet-backed condominiums use `app/agents/zela.py`
  with tools in `app/agents/people_tools.py`, `occurrence_tools.py`, `delivery_tools.py`,
  `visitor_tools.py` and `rule_tools.py`, chosen by the sender's role in
  `zela.build_registry`; tools act only for `ToolContext.person`. The legacy concierge uses `app/agents/resident_tools.py` and
  `ToolContext.resident_id`. Tools never take actor or tenant IDs from the model.
- Consequential tools (changing people or occurrences, authorizing visitors) take two steps:
  `confirmed=false` returns a summary with a `preview_key` in `ToolResult.log`;
  `confirmed=true` must pass `was_previewed()` (ADR 0011). Reporting occurrences and
  recording or closing deliveries, and answering a gate notice, are single steps
  (ADR 0012/0013/0014).
  Arguments use Pydantic models with `extra="forbid"`. For each new tool, add a `ScriptedLLM`
  test and an eval case.
- System prompts (`app/agents/prompts/*.md`) must stay static (they're cached). Per-run facts
  go in `render_context()`.
- Senders in sheet mode are identified by `services/people.identify()` (confirmed manager
  number plus active Pessoas rows); unknown numbers get a fixed reply without the model.
- WhatsApp side effects go through `services/conversations.send_outbound` with an idempotency
  key. Never call the sender directly. Proactive messages go through
  `services/notifications.enqueue` with a guard when they announce a state, so they're skipped
  if the state changed before sending. New templates must also be added to
  `docs/whatsapp-templates.md`.
- Background work goes through `JobPublisher` topics handled in `app/workers/runner.py`
  (`whatsapp-inbound`, `document-index`, `notification-send`). Tests use `JOBS_MODE=log` and the
  `publisher` fixture, and run jobs explicitly.
- Ticket and occurrence category and priority come from `services/tickets.classify()`
  (ADR 0009/0012). Don't store model output directly as confirmed values; the suggestion goes
  in "Sugestão da IA".
- Notifications that announce a sheet value use a guard that re-reads the sheet at send time
  (`occurrence_status`, `delivery_waiting`, `visitor_status`). `notifications.deliver`
  needs `google` for those.
- Condominium records go through `services/drive.open_table()`, which loads a `Table`
  under the per-condominium sheet lock; commit after the last write. Columns are matched by
  header name (`app/registers/specs.py`). Add columns freely, but never rename a header.
  Every row Zela writes gets an `ID Zela` derived from the triggering message, so a retried
  message can't add the same row twice.
- Google calls go through the `Google` and `Workspace` protocols. Tests use the `google`
  fixture (`FakeGoogle`) and hand-edit its tabs to simulate managers; locally,
  `GOOGLE_MODE=fake` works without credentials (`docs/google-setup.md`). Values are written
  RAW, so text that looks like a formula stays text.
- Postgres search uses the `pt_unaccent` text search config (migration 0003).
- Documents for rules Q&A arrive as WhatsApp files from the manager and are handled by
  `services/rules.py` without the model: saved to Drive (`gdrive:` URIs, readable under
  `drive.file` because Zela created them), indexed by the `document-index` job (ADR 0015).
- Keep `apps/web/src/lib/types.ts` and `src/lib/permissions.ts` in sync with the API schemas and
  `app/rbac/permissions.py`.

## Stack and open decisions (see PDD §16 and ADRs 0001–0010)

- Web: Next.js + TypeScript, Tailwind CSS + shadcn/ui. Used for setup only.
- API: Python + FastAPI. A slim Postgres (SQLAlchemy + Alembic) holds setup and plumbing data only.
- Records: Google Sheets in the manager's Drive (ADR 0010). OneDrive may come later; Dropbox is
  out of scope unless customers ask for it.
- AI: provider-neutral layer (ADR 0007). The default model is `claude-haiku-5-5` (cost), set
  with `LLM_MODEL`.
- GCP: Cloud Run, Pub/Sub, Cloud Logging
- Auth: Firebase Auth for the manager's setup login (ADR 0002)

Decided: Firebase Auth, Meta Cloud API direct, organization → many condominiums (2026-10-22).
On 2026-10-28: WhatsApp for every role, Google Sheets as the record, a setup-only website,
and Haiku as the default model. On 2026-10-29: visitors are handled over WhatsApp and the
front desk (resident authorization plus asking the unit about unannounced visitors), with
no intercom or access-control integration for now (ADR 0014). Also on 2026-10-29: a síndico
can manage many condominiums, each with its own Zela WhatsApp number (inbound messages are
routed by that number), so the síndico has one chat per condominium. Still open (PDD §16): first
commercial feature, billing, and pilot customer type. Do not hard-code assumptions about
those. Raise them with the user.

Keep it low cost. Prefer free-tier-friendly choices. Keep the number of LLM calls and their
tokens down, and batch Sheets API calls.

## Architectural invariants

These rules come from the design doc and should shape any code written here:

- **Layering:** WhatsApp/Web → API → Auth & RBAC → Business Services → Agent Orchestrator → Approved Tools → DB. The agent layer calls business services and never bypasses their validation or authorization.
- **Agents act only through explicit backend tools** (e.g. `get_resident_context`, `search_condominium_documents`, `create_maintenance_ticket`, `create_visitor_authorization`). They never generate raw DB operations. Each tool validates the actor, the condominium scope, its inputs, and the business rules. A model's interpretation of a request never counts as authorization.
- **The stored record is the source of truth.** For condominium data that is the Google Sheet; for setup and plumbing it is Postgres. It outranks model output and chat history. Never report an action as successful until the write is confirmed. Re-read a row before acting on it, because people edit the sheets by hand. Notifications must reflect the stored state.
- **Multi-tenant isolation:** all tenant data is scoped to an organization and a condominium, and each condominium uses its own Drive credentials and spreadsheet IDs. Cross-condominium access must be prevented and covered by tests. Residents must never be able to enumerate the directory or see other residents' data through chat. What a sender may do depends on their role in the Pessoas sheet, and the backend validates that role. The model's view of who is writing never counts.
- **Idempotency:** WhatsApp webhooks are retried and duplicated. Duplicate events must not create duplicate business operations; sheet rows carry a Zela ID that is checked before writing. Verify webhook signatures.
- **Async work:** long tasks like document indexing and notifications go to background workers. The webhook response must not wait on them.
- **Untrusted input:** resident messages and uploaded documents are untrusted, so guard against prompt injection. RAG answers must cite their sources and say plainly when they are uncertain rather than make something up.
- **Auditability:** record tool calls, ticket changes, and security-sensitive actions as audit events or agent runs.
- **AI suggestions** (category, priority) go through deterministic validation. Keep AI suggestions separate from confirmed values, both in the sheet columns and in the messages.
- **LGPD:** collect only the data needed. Personal data lives in the customer's Drive; Postgres keeps phone numbers only for routing, plus short-lived conversation text with a retention limit. Keep secrets, such as OAuth tokens, encrypted and out of ordinary records.

## Product conventions

- Conversational UX is in Brazilian Portuguese. Keep replies concise, ask only for missing info, confirm consequential actions, and give a reference number for operational requests.
- Brand palette: terracotta `#C96A4A`, charcoal `#1C1C1E`, warm white `#F5F2EE`, sand `#D8C3A5`, deep copper `#A44A2A`. Fonts: Manrope or Inter.
- Definition of done (PDD §17) covers backend authorization, audit events, unit and integration tests, and AI eval tests for AI features.
