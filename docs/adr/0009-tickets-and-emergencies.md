# 0009: Deterministic ticket classification and the emergency procedure

**Status:** Accepted (2026-10-28)

## Context
PDD §5.6: AI classifications are suggestions subject to deterministic validation, and
emergency reports must follow a configured escalation procedure. A missed emergency is
far more costly than a false alarm.

## Decision
- **Categories** are one fixed list (`TicketCategory`). It's the same for every
  condominium for now and is enforced by a CHECK constraint. The model may only choose
  from it; per-condominium lists can come later.
- **Priority** is decided by `services/tickets.classify()`:
  1. Emergency keywords (gas leak or smell, fire, smoke, flooding, someone trapped in a
     lift or hurt, electric shock, collapse) are matched on accent-stripped text and force
     `emergency`, whatever the model said.
  2. Otherwise the model's suggestion is used, defaulting to `normal`. The model may raise
     a report to `emergency` on its own: we accept false alarms to avoid misses.
  3. The model's suggestion is always stored separately (`ai_suggested_*`). The dashboard
     shows it as a suggestion next to the confirmed value, which staff can correct.
- **Emergency procedure** runs from the *stored* priority, never from chat text alone.
  1. The assistant tells the resident to call 193/192/190.
  2. The conversation is escalated.
  3. Every on-call contact configured for the condominium gets a WhatsApp alert (a
     template, since they usually haven't written in).
  4. A ticket event records how many were alerted, or that none were configured.
- **Numbers** are per condominium (`#1`, `#2`, …) from `condominium_counters` using
  `INSERT … ON CONFLICT DO UPDATE … RETURNING`, so they are safe under concurrency.
- **Idempotency:** a ticket created by the concierge is keyed by the triggering message
  and title, so redelivery or a retried run never opens a duplicate.
- **Resident updates** go out when staff change the status or add a public note. The
  notification row carries a guard (the status it announces). The worker re-checks it
  against the database before sending and skips it if the ticket has moved on, so a
  resident is never told something that is no longer true.
- **Status workflow:**
  - open → in progress / waiting for information / waiting for external service /
    resolved / closed
  - waiting → in progress or resolved
  - resolved → closed, or reopened
  - closed is final

## Consequences
- The keyword list needs care in both directions. False positives page the on-call team,
  and misses rely on the model raising the priority. Each new incident should add an eval
  case and, where possible, a keyword.
