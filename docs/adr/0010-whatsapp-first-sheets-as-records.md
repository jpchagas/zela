# 0010: WhatsApp for every role, Google Sheets as the record, setup-only website

**Status:** Accepted (2026-10-28). Supersedes parts of 0001, 0002, 0003, 0006, 0008 and 0009
(listed under Consequences).

## Context
Milestones 1–3 built a dashboard-centred product: Postgres held every business record and
managers worked in the web app, while WhatsApp served residents only. That is not the
product. Zela is meant to be **low cost**, and the original concept is:

- WhatsApp is the interface for **everyone**: the manager (síndico or administradora),
  owners, residents and staff.
- The condominium's records are **spreadsheets in the manager's own cloud drive**. The
  manager can open, read and fix them without Zela.
- The website exists only for initial setup, and only the manager uses it.

## Decision
1. **Website: setup only, manager only.** The manager signs in (Firebase Auth, as in 0002),
   connects the condominium's WhatsApp number, and connects Google Drive. The site has no
   screens for day-to-day work.
2. **WhatsApp for every role.** Zela identifies the sender by their WhatsApp number,
   looked up in the condominium's Pessoas sheet. Their role (manager, owner, resident or
   staff) decides which tools the agent may use. Typical flows:
   - The manager registers people.
   - Residents report problems and authorize visitors.
   - Staff log deliveries and check visitor authorizations.
3. **Google Sheets is the system of record for condominium data.** Each register is a
   spreadsheet: Pessoas, Ocorrências, Visitantes, Encomendas, and later others. Zela finds
   or creates each one in a "Zela" folder in the manager's Drive.
   - Columns are read by header name, never by position. The header row is protected.
   - Every row carries a Zela ID column. A write first looks the ID up, so a retried
     WhatsApp message can't add the same row twice.
   - Writes to one condominium's spreadsheets are serialized behind a per-condominium lock.
   - Zela re-reads a row before acting on it. It never reports an action as done until
     the Sheets API has confirmed the write.
4. **Google Drive only, for now.** Excel on OneDrive is the next candidate, since its API
   can also read and change single rows. Dropbox only stores whole files, so every change
   means rewriting the file and concurrent writes can overwrite each other. It is out of
   scope unless customers ask for it.
5. **Postgres keeps only setup and plumbing data**, never condominium registers:
   - which WhatsApp number belongs to which condominium, and the manager account;
   - Drive OAuth tokens, encrypted, and the IDs of the condominium's spreadsheets;
   - the webhook ledger, message idempotency keys and the job queue;
   - short-lived conversation state: the 24-hour window and recent turns for the agent,
     with a retention limit;
   - audit events for tool calls (IDs and field names only, as before).
6. **Default model: `claude-haiku-5-5`.** It is the cheapest Claude model and fits short
   WhatsApp turns. The model is still a setting (`LLM_MODEL`). Haiku has no server-side
   refusal fallback, so the adapter sends `fallbacks` only to models that support it.

## Consequences
- **Superseded parts of earlier ADRs:**
  - 0001: Postgres is no longer the system of record, and the dashboard is no longer the
    work surface.
  - 0002: there are no staff roles on the web; only the manager signs in.
  - 0008: there is no enrollment code. A person exists once the manager adds them.
  - 0009: tickets and their events live in the Ocorrências sheet. The classification and
    emergency rules carry over unchanged.
- **Still in force:**
  - 0003: tenant isolation. Every condominium uses its own Drive credentials and
    spreadsheet IDs, and the agent tools still act only for the identified sender.
  - 0004: the WhatsApp integration (signature checks, deduplication, async processing).
  - 0005: agents act only through validated tools.
  - 0007: the provider-neutral LLM layer.
- **Deferred:** 0006, document Q&A. It may come back reading a Regimento from the Drive
  folder.
- **Authorization moves into the spreadsheet.** Anyone who can edit the Pessoas sheet can
  change roles. That person is the manager, who owns the Drive, which is acceptable.
  Zela validates every row it reads (phone format, a role from the allowed list) and
  ignores rows that fail validation.
- **Hand edits are expected.** Zela must tolerate reordered columns, extra columns, blank
  rows and deleted rows, and tell the manager on WhatsApp when a sheet can't be read.
- **Google OAuth scope:** the aim is to use `drive.file`, a non-sensitive scope that avoids
  Google's paid security review. That scope only reaches files Zela created or that the
  manager picked in the Google Picker. Using an existing spreadsheet therefore goes
  through the Picker during setup.
- **Rate limits:** the Sheets API allows about 60 write requests per minute per user,
  which is enough for one condominium's WhatsApp traffic. Writes are batched where
  possible and retried with backoff.
- **LGPD:** personal data stays in the customer's own Drive, which makes Zela a data
  processor. Postgres holds phone numbers only as the routing key, plus short-lived
  conversation text with a retention limit.
- **Code from M1–M3** stays on its branches. On `feat/sheets-pivot` we keep the WhatsApp
  layer, the LLM layer, the agent and tool framework, the prompts and the classification
  rules. We remove the dashboard work screens, the four-role RBAC, and the business tables
  as their sheet-backed replacements arrive.
