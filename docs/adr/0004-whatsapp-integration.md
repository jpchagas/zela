# 0004: Meta Cloud API direct, idempotent webhook ledger, async processing

**Status:** Accepted (2026-10-22). Receiver implemented. Processing lands in Milestone 2.

## Context
PDD §16.4: direct Meta Cloud API or a BSP. Webhooks are retried and duplicated (PDD §10.3).

## Decision
- Integrate directly with the Meta Cloud API. Keep provider-specific code in
  `app/integrations/whatsapp/` so a BSP adapter could replace it.
- `POST /webhooks/whatsapp`:
  1. Verify `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret).
     An unsigned or bad request gets 401, and nothing is stored.
  2. Split the payload into events. Each message is one event (`msg:<wamid>`), and each
     status transition is another (`status:<wamid>:<status>`).
  3. `INSERT … ON CONFLICT DO NOTHING` into `webhook_events`. Only new rows are
     published to the `whatsapp-inbound` topic.
  4. Return 200 immediately. Agent runs, replies and notifications happen in workers.
- Workers use the webhook event ID as the idempotency key for anything they create, and
  business tables (`maintenance_tickets`, `visitor_authorizations`,
  `notification_events`) have a `(condominium_id, idempotency_key)` unique constraint.
- Inbound messages are routed to a tenant by `condominiums.whatsapp_phone_number_id`.
  Access tokens live in Secret Manager, never in the database.

## Consequences
- If publishing fails after commit, the event stays `received`. A sweeper must
  republish stale `received` rows (Milestone 2).
- `webhook_events.payload` contains message content and falls under the conversation
  retention policy.
