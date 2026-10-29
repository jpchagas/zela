# 0015: Questions about the rules, from documents sent on WhatsApp

**Status:** Accepted (2026-10-29). Reuses the retrieval of ADR 0006 for condominiums on
Google Sheets (ADR 0010).

## Context
Residents ask the same questions all the time: pool hours, quiet hours, moving rules,
fines. The answers are in the internal regulations, the convention, assembly minutes and
notices. There is no dashboard upload any more. And with the `drive.file` scope (ADR
0010), Zela can only read files it created itself, not files the manager drags into Drive.

## Decision
- **The manager sends the file in the WhatsApp chat** (PDF or .txt, up to
  `MAX_UPLOAD_MB`).
  - The worker handles it without the model: it downloads it from Meta, saves it to the
    condominium's Zela folder in Drive, and queues the indexing.
  - Because Zela created the Drive copy, it can read it back under `drive.file`. The
    manager keeps the file with their other records.
  - The caption names the document; without one, the filename does.
  - A file whose title matches a ready document replaces it once the new one indexes.
    The same file sent twice is recognized and not added again.
  - Only the manager may add documents. Anyone else gets a fixed reply.
- **Indexing is ADR 0006, unchanged.**
  - Chunks go in `document_chunks`, searched with `pt_unaccent`, with page and section
    kept for citations.
  - Documents in Drive are stored as `gdrive:<file id>` and read from Drive at indexing
    time.
  - If Drive can't be read, the document goes back to pending and the job is retried.
  - The manager is told the outcome (`zela_document_status`): ready, or why it couldn't
    be read (for example a scanned PDF).
- **Anyone identified can ask** (`search_rules`).
  - The model must search before answering about rules and answer only from the
    excerpts, citing them ("Regimento Interno, p. 4").
  - When nothing matches, it says so plainly and suggests the manager, without filling
    in from what other condominiums usually do.
  - Excerpts are third-party reference material, never instructions.
- **The manager lists documents and stops using one** (`list_documents`,
  `remove_document`). Removal is a single step and leaves the file in Drive. Sending
  the file again restores it.
- **Retries never duplicate.** The Drive copy is keyed by the WhatsApp message ID in
  appProperties, so a retried message finds the file it already uploaded.

## Consequences
- **The searchable text lives in Postgres** as a derived index, alongside routing data.
  The record is the Drive file. Removing a document deletes nothing from Drive, and
  deleting the Drive file doesn't remove the index: the manager uses `remove_document`.
- **Every document is visible to every registered person.** The manager shouldn't send
  anything internal. Per-document visibility can come later if managers need it.
- **No OCR.** Scanned PDFs fail with a clear message, as in Milestone 3.
- **Retrieval is lexical.** Paraphrased questions may miss; vectors stay deferred
  (ADR 0006) until evals show the need.
