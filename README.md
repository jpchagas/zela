# Zela

The AI concierge for condominiums. Residents use WhatsApp, and managers and staff use a web
dashboard. See [product_design_document.md](product_design_document.md) for scope and
[docs/adr/](docs/adr/) for architecture decisions.

```
apps/api   FastAPI · SQLAlchemy · Alembic · Postgres   (business services, RBAC, agent tools, webhooks)
apps/web   Next.js · Tailwind · shadcn/ui              (management dashboard, pt-BR)
docs/adr   Architecture decision records
infra/     Local infrastructure helpers
```

## Quickstart

Requires Docker, Python 3.10+ and Node 22.

```bash
make db                                  # Postgres on localhost:5433 (dev + test databases)
make api-install migrate
make seed EMAIL=you@example.com          # demo condominium, you as org owner
make api-dev                             # http://localhost:8000/docs

make web-install web-dev                 # http://localhost:3000, sign in with that email
```

Both apps default to **dev auth** (`AUTH_MODE=dev` / `NEXT_PUBLIC_AUTH_MODE=dev`): the
dashboard sends `Bearer dev:<email>` and the API trusts it. The API refuses this mode
outside `ENV=development|test`. For Firebase, set `AUTH_MODE=firebase` and
`FIREBASE_PROJECT_ID` in `apps/api/.env`, and the `NEXT_PUBLIC_FIREBASE_*` values in
`apps/web/.env.local`.

### Try the WhatsApp flow locally

With `ENV=development`, `POST /dev/whatsapp/inbound` feeds a message through the real
pipeline (ledger → worker → enrollment/concierge) without Meta and returns the replies.
The seeded condominium has a WhatsApp ID, so:

1. In the dashboard, add a resident with a phone, then click **Gerar código** on the phone.
2. Simulate the resident sending the code, then any question:

```bash
curl -s localhost:8000/dev/whatsapp/inbound -H 'Content-Type: application/json' \
  -d '{"condominium_id":"<id>","from_e164":"+5511987654321","text":"ABCD-2345"}'
```

To try documents and tickets: upload a PDF in **Documentos**, ask about it, or report a
problem ("o portão da garagem quebrou"). Tickets appear in **Chamados**. Add an on-call
contact in **Configurações** to see emergency alerts; locally they're recorded, not sent.

`LLM_PROVIDER=scripted` (the default in `.env.example`) answers with a rule-based stand-in.
It only understands a few phrases and doesn't use documents or tickets, so use Claude to
try those flows.
Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to use Claude. Replies show up in
**Conversas**.

## Checks

```bash
make test        # API tests against real Postgres, including tenant-isolation tests
make lint        # ruff
make web-check   # tsc, eslint, next build
make eval        # opt-in AI evals against the real model (costs money)
```

## Status

Milestone 0 (foundation) and the Milestone 1 slice are in place:

- Organizations → condominiums → buildings → units, residents (phones, unit links,
  suspend/reinstate/revoke), staff invites, audit log
- Firebase-backed auth with invite-only linking and role-based access per condominium
- Schema for Milestones 2–4 (conversations, messages, tickets, visitors, documents,
  agent runs, notifications, webhook idempotency)
- WhatsApp webhook receiver: signature check, dedupe ledger, enqueue seam
- Agent tool contract (`apps/api/app/agents/tools.py`)

Milestone 2 (WhatsApp and AI foundation):

- Inbound worker: per-contact ordering, and idempotent message, agent-run and reply records.
  Delivery statuses tracked, plus a sweeper for unfinished events.
- Resident enrollment by one-time code bound to the registered number (ADR 0008)
- Concierge agent on a provider-neutral LLM layer, Claude first (ADR 0007), with tools
  `get_resident_context` and `escalate_to_human`. Every run is recorded in `agent_runs`.
- Dashboard: conversations with escalation, staff replies within the 24h window, activation
  codes, WhatsApp configuration. AI, staff and automatic messages are styled distinctly.
- Opt-in AI eval suite (`tests/evals`)

Milestone 3 (knowledge and maintenance):

- Document knowledge base: PDF and text upload, background indexing into section-aware
  chunks, and accent-insensitive Portuguese search. Answers cite their source ("Regimento
  Interno, p. 4"). Versions can be replaced, documents deactivated, and the search tested
  in the dashboard.
- Maintenance tickets from WhatsApp. Categories are validated against a fixed list and
  priority is rule-checked, with the AI's suggestion kept beside the confirmed values.
  Numbering is per condominium, and staff manage status, notes, assignment and
  classification.
- Emergency procedure: on-call contacts per condominium get a WhatsApp alert, and the
  conversation is escalated (ADR 0009).
- Notifications: plain text inside the 24h window and approved templates outside it
  (`docs/whatsapp-templates.md`). Each one is re-checked against the stored state before
  sending.

Next: Milestone 4. That covers visitor authorization.
