# 0014: Visitors in the Visitantes sheet

**Status:** Accepted (2026-10-29). Settles the visitor workflow left open in PDD §16:
WhatsApp and the front desk, with no intercom or access-control integration for now.
Builds on ADR 0010, 0011 and 0013.

## Context
A visitor reaches the gate in one of two ways. Either someone in the building said they
were coming, or they just show up and the doorman calls the unit on the intercom. Both
should work over WhatsApp, with the Visitantes sheet as the record of who was let in, by
whom and when.

## Decision
- **Residents, owners and the manager authorize visitors ahead of time.**
  - `authorize_visitor` takes two steps (ADR 0011), because it lets someone into the
    building.
  - It covers one day, or up to 30 days for regular visitors (a cleaner, a building
    job), starting at most 60 days ahead.
  - The unit comes from the sender's own Pessoas rows. The manager may name any unit, or
    none for a visit to the condominium itself.
  - Each authorization gets a random 6-digit code to share with the visitor.
- **The desk checks and lets visitors in** (staff and the manager).
  - `check_visitor` finds what is valid today by name, code or unit.
  - `record_visitor_entry` lets one in by code. A one-day authorization ends as Entrou;
    a longer one stays Autorizado and logs each entry in Observações.
  - Whoever authorized it is told the visitor arrived (`zela_visitor_arrived`).
- **Visitors who weren't announced are asked about.**
  - `announce_visitor` writes a row as Aguardando morador and asks the unit's people
    (`zela_visitor_at_gate`, chosen like ADR 0013), with the code.
  - The first person on that unit to answer (`answer_visitor`) settles it: Autorizado for
    today, or Recusado. The desk member who asked is told (`zela_visitor_answer`).
  - Answering is a single step: the notice is the summary, and the visitor is waiting.
  - The other people's notices are guarded by the sheet: once someone answered, or the
    desk resolved it by hand, they aren't sent.
  - A code belonging to another unit gets the same reply as one that doesn't exist.
- **Expiry is read, not written.** An authorization or unanswered announcement past its
  last day reads as Expirado, whatever the sheet says, so nobody needs to clean up the
  sheet for the gate to stay shut.
- **Notices stay in the conversation.** The agent's history now keeps automatic notices
  even when one opens the conversation. That way "pode subir" answers the gate notice
  the resident just got.
- **Privacy:** residents see only their own units' visitors. The desk sees visitor, unit,
  dates and notes, not who authorized them. Audit events hold IDs and counts, never names.

## Consequences
- **No intercom or access-control integration.** The doorman still opens the gate. An
  integration can come later behind the same records.
- **An unanswered announcement just waits.** If nobody answers, the doorman decides as
  they do today: calling the unit, or the manager.
- **Codes aren't secret.** The desk still checks the name, and a code only works on the
  days it covers.
- **Sheets created before this phase** keep their old Status dropdown. It is non-strict,
  so Aguardando morador and Recusado are still written; Sheets only flags them.
- **Rows typed by hand work.** A blank status reads as Autorizado for its dates, and the
  row gets a Zela ID (`V-ROW<n>`) the first time Zela changes it.
