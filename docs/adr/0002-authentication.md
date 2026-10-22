# 0002: Firebase Auth for dashboard users, invite-only, roles in Postgres

**Status:** Accepted (2026-10-22)

## Context
Managers and staff sign in to the dashboard. Residents use WhatsApp and do not have
dashboard accounts in the MVP. PDD §16.3 left the identity provider open.

## Decision
- Firebase Authentication proves *who* someone is. The API verifies ID tokens with the
  Admin SDK (`check_revoked=True`).
- Postgres decides *what* they may do: `users`, `organization_memberships`,
  `staff_memberships`. No custom claims, so a revoked membership takes effect on the next
  request instead of after token expiry.
- Access is invite-only. A manager invites an email. On first sign-in, a verified token
  email matching an unlinked `users` row links the Firebase UID. Unknown identities get 403.
- `is_platform_admin` grants no tenant data access by itself (PDD §3.5).
- `AUTH_MODE=dev` accepts `Bearer dev:<email>` for local work. Settings refuse to load it
  unless `ENV` is `development` or `test`.
- Residents are identified through WhatsApp enrollment (Milestone 2), not Firebase.
  Phone match alone is not sufficient for sensitive operations (PDD Journey A).

## Consequences
- Each request costs a membership lookup. This is cheap and indexed, and the price buys
  immediate revocation.
- Moving off Firebase later means replacing `FirebaseTokenVerifier` only.
