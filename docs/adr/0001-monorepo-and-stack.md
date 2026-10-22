# 0001: Monorepo, FastAPI + Postgres API, Next.js dashboard

**Status:** Accepted (2026-10-22)

## Context
PDD §10.2 proposes Next.js, FastAPI, PostgreSQL, SQLAlchemy/Alembic and GCP. One small
team will build the API, the dashboard and the agent layer together.

## Decision
- One repository: `apps/api` (Python, FastAPI, SQLAlchemy 2, Alembic) and `apps/web`
  (Next.js App Router, TypeScript, Tailwind v4, shadcn/ui).
- PostgreSQL is the only system of record (PDD §16.5 resolved: no Firebase-centred data).
- The API uses synchronous SQLAlchemy sessions. Throughput needs are modest, and sync
  code is simpler to test and reason about transactionally. Revisit if profiling shows
  otherwise.
- Business logic lives in `app/services`. Routes stay thin. Agent tools (ADR 0005) call
  the same services.
- Target deployment is Cloud Run + Cloud SQL + Pub/Sub + Cloud Storage, but nothing in
  the code depends on GCP yet beyond the Firebase Admin SDK.

## Consequences
- Types are duplicated between `apps/api/app/schemas` and `apps/web/src/lib/types.ts`.
  Generate the TS types from OpenAPI once the API surface settles.
- Python 3.10+ is supported locally. The container uses 3.12.
