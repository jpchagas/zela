# 0012: Occurrences in the Ocorrências sheet

**Status:** Accepted (2026-10-28). Moves Milestone 3 tickets (ADR 0009) to the sheet
for condominiums that use Google Sheets (ADR 0010).

## Context
Complaints, maintenance problems and suggestions are the first operational records that
residents create. ADR 0009's rules still apply: the AI only suggests category and
priority, keywords force emergencies, and emergencies alert the on-call contacts. There
is no dashboard to escalate to any more, and the record lives in a sheet the manager can
edit by hand.

## Decision
- **Anyone identified (ADR 0011) can report.**
  - `report_occurrence` writes one row in Ocorrências.
  - Type is Manutenção, Reclamação, Sugestão or Outro.
  - Each occurrence gets a number from the Postgres counter `occurrence`, so numbers are
    never shared.
  - "In my unit" is resolved against the sender's own Pessoas rows; with several units,
    the model must say which.
  - Reporting is a single step: emergencies can't wait for a confirmation round-trip.
- **Classification is `tickets.classify()`, unchanged.** The model's suggestion goes in
  "Sugestão da IA", separate from Categoria and Prioridade.
- **Emergencies alert people on WhatsApp.**
  - Recipients: the on-call contacts and the confirmed manager, never the reporter.
  - Template: `zela_occurrence_emergency`. It names the reporter by first name and unit
    so whoever is on call knows where to go.
  - The conversation is not escalated: there is no dashboard to hand it to.
- **People follow only their own occurrences** (`get_my_occurrences`), matched by the
  reporter's Pessoas ID. Only the manager lists everyone's (`find_occurrences`).
- **The manager changes occurrences in two steps** (`update_occurrence`, like ADR 0011).
  - Status, assignee, category and priority can change, and internal notes go in
    Observações.
  - A status change notifies the reporter (`zela_occurrence_update`), with an optional
    note for them.
  - The notification is guarded by the sheet itself. At send time Zela re-reads the row,
    and skips the message if the status has changed since.
  - If the sheet can't be read, the send fails and the notification stays pending for a
    retry.
- **Retries never duplicate.** Each row's Zela ID comes from the triggering message and
  the description; a retried report finds its row and alerts nobody again.

## Consequences
- **Edits made directly in the sheet don't notify anyone.** Zela doesn't watch the sheet.
  Watching for changes (Drive push notifications or polling) can come later if managers
  want it.
- **Rows typed by hand can be updated by number.** They get a Zela ID (`O-ROW<n>`) the
  first time Zela changes them.
- **Statuses are free to move between any values.** Milestone 3's transition rules don't
  apply, because the sheet can hold anything a person types. Zela treats Resolvida and
  Cancelada as closed.
- **The reporter's phone is never copied into Ocorrências.** It's looked up in Pessoas
  when a notification is sent, so a deactivated reporter isn't messaged.
