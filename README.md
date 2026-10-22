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

## Checks

```bash
make test        # API tests against real Postgres, including tenant-isolation tests
make lint        # ruff
make web-check   # tsc, eslint, next build
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

Next: Milestone 2. That covers the inbound worker, resident enrollment, the concierge
agent, and human escalation.
