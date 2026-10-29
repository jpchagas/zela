# 0013: Deliveries in the Encomendas sheet

**Status:** Accepted (2026-10-29). Builds on ADR 0010 (Sheets as the record) and ADR 0011
(people and roles).

## Context
Packages arrive at the front desk all day. Today the doorman writes them in a notebook and
calls or messages the unit. Zela should let staff record a package in one WhatsApp message,
tell the right people, and keep the Encomendas sheet as the record of what is waiting and
who took it.

## Decision
- **Staff and the manager record packages.**
  - `record_delivery` writes one row in Encomendas, numbered by the Postgres counter
    `delivery`.
  - Unit is required; block, recipient name and description are optional.
  - It is a single step, without a confirmation summary. It happens many times a day at a
    busy desk, and the only consequence is a "your package arrived" message.
- **The unit is read against Pessoas.**
  - Without a block, a unit number that exists in more than one block is refused, and the
    model asks which block.
  - A unit nobody is registered on is still recorded as typed: the package did arrive.
    Nobody is notified, and the staff member is told so.
- **Who is notified** (template `zela_delivery_arrived`), from the active Pessoas rows of
  that unit that have a WhatsApp:
  1. the named recipient, if their name matches someone registered there;
  2. otherwise the unit's residents (Morador);
  3. otherwise everyone on the unit, so an owner-occupied unit registered only as
     Proprietário is still told.
  Owners who rent the unit out aren't told about their tenants' packages.
- **The notice is guarded by the sheet.** At send time Zela re-reads the row and skips the
  message if the package is no longer waiting, for instance when it was picked up minutes
  after arriving.
- **Anyone can ask about their own units** (`get_my_deliveries`): the packages waiting for
  any unit on their own Pessoas rows. People on the same unit see the same packages.
- **Staff and the manager close packages by number** (`close_delivery`): Retirada, with who
  collected it, or Devolvida. `find_deliveries` lists what is waiting, by unit or name.
- **Retries never duplicate.** The Zela ID comes from the triggering message, unit,
  recipient and description; a retried message finds its row and notifies nobody again.
- **Audit events** (`delivery.received`, `delivery.closed`) hold the number, counts and
  outcome, never names, units or descriptions.

## Consequences
- **No reminder for packages left waiting.** A daily reminder would cost one message per
  package per day; it can be added if managers ask for it.
- **Nobody is told when a package is picked up.** A "your package was collected by X"
  message would help against theft, at the cost of a message per package. Left for later.
- **"Morador avisado em" is when the notice was queued**, not when WhatsApp delivered it.
  Delivery status stays in Postgres with the notification.
- **Rows typed by hand work**: a blank status counts as waiting, and the row gets a Zela ID
  (`E-ROW<n>`) the first time Zela closes it.
- **Zela doesn't check who collects a package.** Staff type the name they were told; any
  identity check stays at the desk.
