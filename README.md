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

To try the whole product in stages (local, then real AI, Drive and WhatsApp), follow
[docs/testing-guide.md](docs/testing-guide.md).

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

### Try people over WhatsApp

With Drive connected (fake mode is fine), set your number under **Seu WhatsApp de síndico**,
then use `POST /dev/whatsapp/inbound` to play the manager and then the new person. The
rule-based stand-in (`LLM_PROVIDER=scripted`) understands this exact phrasing:

```bash
say() { curl -s localhost:8000/dev/whatsapp/inbound -H 'Content-Type: application/json' \
  -d "{\"condominium_id\":\"<id>\",\"from_e164\":\"$1\",\"text\":\"$2\"}"; }
say +5511955550000 "sim"     # confirms the manager number
say +5511955550000 "cadastrar Juliana Prado, apto 204, bloco B, 11 91234-5678, moradora"
say +5511955550000 "sim"     # confirms the summary; the row appears in Pessoas
say +5511912345678 "meu cadastro"
say +5511912345678 "o portão da garagem quebrou"      # occurrence #1
say +5511912345678 "tem fumaça saindo do quadro de luz" # emergency: on-call + manager alerted
say +5511912345678 "minhas ocorrências"
say +5511955550000 "ocorrencias abertas"
say +5511955550000 "cadastrar Jorge Silva, 11 93333-0001, porteiro"
say +5511955550000 "sim"
say +5511933330001 "chegou encomenda pro 204 bloco B"   # Juliana is told
say +5511912345678 "tem encomenda pra mim?"
say +5511933330001 "encomenda #1 retirada pela Juliana"
say +5511933330001 "encomendas pendentes"
say +5511912345678 "autorizar visita de Marcos Lima hoje"
say +5511912345678 "sim"                     # returns a 6-digit code
say +5511933330001 "visitante Marcos"
say +5511933330001 "entrada <código>"         # Juliana is told Marcos arrived
say +5511933330001 "anunciar Paulo pro 204"   # Juliana is asked on WhatsApp
say +5511912345678 "sim"                     # the desk is told she let him in
# The manager sends a document (any PDF with selectable text), then a resident asks:
curl -s localhost:8000/dev/whatsapp/inbound -H 'Content-Type: application/json' -d "{
  \"condominium_id\":\"<id>\",\"from_e164\":\"+5511955550000\",
  \"document\":{\"filename\":\"Regimento Interno.pdf\",
  \"content_base64\":\"$(base64 -w0 regimento.pdf)\"}}"
say +5511912345678 "qual o horário da piscina?"
```

With Claude (`LLM_PROVIDER=anthropic`), write naturally.

### Try the legacy WhatsApp flow locally

Condominiums without Drive still run the Milestone 1–3 flow, which ADR 0010 is replacing
phase by phase.

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
- Phase 2, done: the manager's WhatsApp is set on the setup page and confirmed by
  answering SIM; senders are recognized from the Pessoas sheet; the manager registers,
  finds, corrects and deactivates people by WhatsApp, always confirming a summary first
  (ADR 0011). Registered people get a welcome message.
- Phase 3, done: anyone registered reports problems, complaints and suggestions, which
  become numbered rows in Ocorrências; emergencies alert the on-call contacts and the
  manager; people follow their own occurrences; the manager lists and updates them (two
  steps) and the reporter is told (ADR 0012).
- Phase 4, done: staff and the manager record packages by WhatsApp in Encomendas; the
  unit's residents (or the named recipient) are told; residents ask what's waiting for
  them; staff mark pickups and returns (ADR 0013).
- Phase 5, done: residents authorize visitors (two steps) and get a code; the desk checks
  visitors and records entries, and whoever authorized is told; for unannounced visitors
  the desk asks the unit on WhatsApp and gets the answer back (ADR 0014).
- Phase 6, done: the manager sends the regulations (PDF or .txt) in the chat; Zela saves
  them to Drive and indexes them; anyone asks about the rules and gets answers that cite
  the document (ADR 0015).

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
