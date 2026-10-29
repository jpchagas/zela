# Zela

The low-cost AI concierge for condominiums. Everyone uses WhatsApp: the manager, owners,
residents and staff. The condominium's records are Google Sheets in the manager's own
Drive, and the website is only for setup (connecting WhatsApp and Drive). See
[ADR 0010](docs/adr/0010-whatsapp-first-sheets-as-records.md) for this direction,
[product_design_document.md](product_design_document.md) for the original scope, and
[docs/adr/](docs/adr/) for every architecture decision.

```
apps/api   FastAPI · SQLAlchemy · Alembic · Postgres   (webhooks, agent tools, Google Sheets registers)
apps/web   Next.js · Tailwind · shadcn/ui              (setup page for the manager, pt-BR)
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

### Connect Google Drive

The setup page's **Conectar Google Drive** button creates the condominium's spreadsheets.
With `GOOGLE_MODE=fake` (the default in `.env.example`), it works without any Google
account, against an in-memory Drive that's lost on restart. To use your real Drive, follow
[docs/google-setup.md](docs/google-setup.md).

### Try the WhatsApp flow locally

This still runs the Milestone 1–3 flow, which ADR 0010 is replacing phase by phase.

With `ENV=development`, `POST /dev/whatsapp/inbound` feeds a message through the real
pipeline (ledger → worker → enrollment/concierge) without Meta and returns the replies.
The seeded condominium has a WhatsApp ID, so:

1. Register a resident and issue an enrollment code through the API (`/docs`). Those
   dashboard screens were removed in the pivot.
2. Simulate the resident sending the code, then any question:

```bash
curl -s localhost:8000/dev/whatsapp/inbound -H 'Content-Type: application/json' \
  -d '{"condominium_id":"<id>","from_e164":"+5511987654321","text":"ABCD-2345"}'
```

Report a problem ("o portão da garagem quebrou") to open a ticket. Add an on-call contact
on the setup page to see emergency alerts; locally they're recorded, not sent.

`LLM_PROVIDER=scripted` (the default in `.env.example`) answers with a rule-based stand-in.
It only understands a few phrases and doesn't use documents or tickets, so use Claude to
try those flows.
Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to use Claude. The default model is
`claude-haiku-5-5`; set `LLM_MODEL` to change it.

## Checks

```bash
make test        # API tests against real Postgres, including tenant-isolation tests
make lint        # ruff
make web-check   # tsc, eslint, next build
make eval        # opt-in AI evals against the real model (costs money)
```

## Status

**Changing direction (ADR 0010).** The rework goes in phases on `feat/sheets-pivot`:

- Phase 0, done: the decision is recorded and the default model is Haiku.
- Phase 1, done: Google Drive connection; the condominium's registers (Pessoas,
  Ocorrências, Visitantes, Encomendas) are found or created in the manager's Drive and
  read by column name, tolerating hand edits; the website is cut down to setup.
- Next: Phase 2, people registered and recognized through WhatsApp. Then occurrences,
  deliveries, visitors, and optionally questions about the condominium's rules.

The Milestone 1–3 build below is still in the code and is being replaced:

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
