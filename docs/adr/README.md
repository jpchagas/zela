# Architecture Decision Records

Short records of decisions that shape the codebase. Add one when a choice would be
expensive to reverse or would surprise a new contributor. Format: context, decision,
consequences. Never edit an accepted ADR's decision; supersede it with a new one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-monorepo-and-stack.md) | Monorepo, FastAPI + Postgres API, Next.js dashboard | Accepted |
| [0002](0002-authentication.md) | Firebase Auth for dashboard users, invite-only, roles in Postgres | Accepted |
| [0003](0003-tenancy-and-isolation.md) | Organization → condominiums, isolation in queries and FKs | Accepted |
| [0004](0004-whatsapp-integration.md) | Meta Cloud API direct, idempotent webhook ledger, async processing | Accepted |
| [0005](0005-agents-act-through-tools.md) | Agents act only through validated backend tools | Accepted |
| [0006](0006-document-retrieval.md) | Postgres full-text search first, vectors later | Accepted |
| [0007](0007-llm-provider-layer.md) | Provider-neutral LLM layer, Claude as the first adapter | Accepted |
| [0008](0008-resident-enrollment.md) | WhatsApp enrollment with a one-time code bound to the number | Accepted |
| [0009](0009-tickets-and-emergencies.md) | Deterministic ticket classification and the emergency procedure | Accepted |
