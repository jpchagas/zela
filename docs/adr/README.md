# Architecture Decision Records

Short records of decisions that shape the codebase. Add one when a choice would be
expensive to reverse or would surprise a new contributor. Format: context, decision,
consequences. Never edit an accepted ADR's decision; supersede it with a new one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-monorepo-and-stack.md) | Monorepo, FastAPI + Postgres API, Next.js dashboard | Superseded in part by 0010 |
| [0002](0002-authentication.md) | Firebase Auth for dashboard users, invite-only, roles in Postgres | Superseded in part by 0010 |
| [0003](0003-tenancy-and-isolation.md) | Organization → condominiums, isolation in queries and FKs | Accepted |
| [0004](0004-whatsapp-integration.md) | Meta Cloud API direct, idempotent webhook ledger, async processing | Accepted |
| [0005](0005-agents-act-through-tools.md) | Agents act only through validated backend tools | Accepted |
| [0006](0006-document-retrieval.md) | Postgres full-text search first, vectors later | Accepted (reused by 0015) |
| [0007](0007-llm-provider-layer.md) | Provider-neutral LLM layer, Claude as the first adapter | Accepted |
| [0008](0008-resident-enrollment.md) | WhatsApp enrollment with a one-time code bound to the number | Superseded by 0010/0011 |
| [0009](0009-tickets-and-emergencies.md) | Deterministic ticket classification and the emergency procedure | Storage superseded by 0010/0012 |
| [0010](0010-whatsapp-first-sheets-as-records.md) | WhatsApp for every role, Google Sheets as the record, setup-only website | Accepted |
| [0011](0011-people-and-roles-over-whatsapp.md) | People and roles from the Pessoas sheet, confirmed manager number, two-step changes | Accepted |
| [0012](0012-occurrences-in-sheets.md) | Occurrences in the Ocorrências sheet, emergency alerts, sheet-guarded updates | Accepted |
| [0013](0013-deliveries-in-sheets.md) | Deliveries in the Encomendas sheet, notifying the unit, sheet-guarded notices | Accepted |
| [0014](0014-visitors-in-sheets.md) | Visitors: resident authorization with a code, desk check-in, unit asked about unannounced visitors | Accepted |
| [0015](0015-rules-from-documents-over-whatsapp.md) | Rules Q&A from documents the manager sends on WhatsApp, kept in Drive, cited answers | Accepted |
