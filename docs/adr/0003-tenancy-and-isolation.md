# 0003: Organization → condominiums, isolation in queries and FKs

**Status:** Accepted (2026-10-22)

## Context
PDD §16.1 asked whether a customer is one condominium or a management company with many.
Cross-condominium leakage is the most damaging failure mode for this product.

## Decision
- An **organization** owns one or more **condominiums** from day one. Org owners and
  admins act in every condominium of their org. Managers and staff are granted per
  condominium. Only org admins can appoint or remove managers.
- Every tenant-owned table carries `condominium_id`. Child rows reference parents through
  **composite foreign keys** `(condominium_id, parent_id)`, so the database rejects a
  unit in another condominium's building, a membership linking another condominium's
  unit, and so on.
- Every condominium route resolves a `CondoContext` (`app/rbac/context.py`) from the
  path and the caller's memberships, then checks a permission. Services load rows only
  through `get_scoped()` or queries filtered by `ctx.condominium_id`.
- A foreign or nonexistent condominium or record returns the same **404**, so IDs can't
  be probed. A member lacking a permission gets 403.
- **Residents are scoped to one condominium.** A person with units in two condominiums
  has two resident records, which keeps one condominium's data invisible to the other's
  managers. A resident can hold several units within a condominium.
- `tests/test_tenant_isolation.py` covers every read endpoint across org and condominium
  boundaries. It has been checked to fail when either the membership check or the scoped
  query filter is removed.

## Consequences
- A future resident portal that spans condominiums must join records by verified phone,
  not by a shared resident ID.
- Postgres Row-Level Security would add defense in depth. It is deferred until the
  query layer settles, and the composite FKs already cover the riskiest writes.
