# 0011: People and roles over WhatsApp

**Status:** Accepted (2026-10-28). Builds on 0010 and replaces 0008 (enrollment codes) for
condominiums that use Google Sheets.

## Context
Under ADR 0010, the manager registers people by WhatsApp and their records live in the
Pessoas sheet. Zela must know who is writing and what they may do, without a dashboard
and without trusting what a message claims about its sender.

## Decision
- **The manager's number is set on the setup page and confirmed from the phone.**
  - Zela sends the `zela_manager_confirmation` template; the manager answers SIM.
  - Until then, that number has no manager rights. A request expires after 7 days.
  - A notification guard skips the message if the number was changed before it went out.
  - WhatsApp authenticates the sender's number, so a reply from it proves possession.
- **Everyone else is identified from the Pessoas sheet.** A sender matches the active rows
  whose WhatsApp number, normalized to E.164, is theirs.
  - Roles are read from Papel, tolerant of wording: "Síndica", "Moradora", "inquilino" and
    "porteiro" all count.
  - With several rows, the broadest role applies: manager, then staff, owner, resident.
  - Rows with an unreadable number or role, or Situação "Inativo", grant nothing.
  - "Síndico" in the sheet also gives manager rights. The manager owns the sheet (ADR 0010).
- **Unknown numbers get a fixed reply without calling the model:** no cost, and nothing for
  the model to reveal.
- **Tools depend on the role,** decided by the backend:
  - Everyone gets `get_my_registration`.
  - The manager also gets `register_person`, `find_people` and `update_person`.
  - Other roles never receive the manager tools, whatever the message says.
- **Changes to people take two steps, enforced in code.** First the tool is called with
  `confirmed=false`; it validates the request and returns a summary. Then it is called
  with `confirmed=true`, and the write happens only if both hold:
  - an earlier agent run in the same conversation showed a summary for exactly these
    normalized arguments;
  - that summary is less than 30 minutes old.

  One message therefore can't both request and confirm, and a confirmation with changed
  details is refused.
- **Each row's Zela ID is derived from the triggering message and the arguments,** so a
  retried confirmation writes one row. A person registered by the manager gets a
  `zela_person_welcome` template.
- **Sheet mode is decided per condominium.** With a Drive connection, the new agent (`zela`)
  answers and conversations are never escalated to a dashboard. Without one, the
  Milestone 2–3 flow still runs until later phases remove it.

## Consequences
- **Each inbound message from a known person reads the Pessoas sheet** (one Sheets API
  read). That's within quota for a condominium. A short cache can come later if needed.
- **Deactivating someone takes effect on their next message.** No session outlives the
  sheet.
- **Typing errors in the sheet only ever remove access.** A typo can't give access to a
  number nobody wrote down.
- **The two-step rule depends on the agent-run log.** Summaries are matched through
  `agent_runs.tool_calls`, so that log must keep `preview_key` for as long as the
  30-minute window lasts.
