# 0004: Meta Cloud API direct, idempotent webhook ledger, async processing

**Status:** Accepted (2026-10-22). Receiver and worker implemented in Milestone 2. Pub/Sub delivery arrives with deployment.

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

- The worker (`app/workers/inbound.py`) holds a Postgres advisory lock per contact while it
  processes a message, so one contact's messages are handled in order.
  - The inbound message is unique by provider ID.
  - The agent run is unique by trigger message.
  - The reply is unique by `reply:<inbound id>`.
  - It is committed as `pending` **before** sending, so a redelivery resends only a
    reply that never left (at-least-once) and never one already sent.
- Free-form messages are only sent inside WhatsApp's 24-hour customer-service window,
  measured from `conversations.last_inbound_at`. Notifications outside it need approved
  templates (Milestone 3).
- Locally, `JOBS_MODE=inline` runs jobs on a thread pool in the API process.

## Consequences
- If publishing fails after commit, the event stays `received`.
  `python -m app.workers.sweep` re-queues stale `received` and `failed` events (up to 5
  attempts). Schedule it with Cloud Scheduler in production.
- `webhook_events.payload` contains message content and falls under the conversation
  retention policy.
