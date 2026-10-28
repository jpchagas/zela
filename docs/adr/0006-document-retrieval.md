# 0006: Postgres full-text search first, vectors later

**Status:** Accepted (2026-10-28), implemented in Milestone 3.

## Context
The knowledge base answers from regulations, minutes and notices, usually a few dozen
documents per condominium, in Portuguese, and answers must cite sources.

## Decision
- Store chunks in `document_chunks` with a generated `tsvector` (`portuguese` config)
  and a GIN index. Retrieval is always filtered by `condominium_id` and document
  visibility. Only `ready` documents that have not been superseded are searchable.
- Add `pgvector` embeddings as a second signal (hybrid ranking) only if evals show that
  lexical search misses paraphrased questions.
- Chunks keep `document_id`, `page` and `heading`, so answers can cite "Regimento
  Interno, p. 4".

## Implementation notes (Milestone 3)
- Text search config `pt_unaccent`: Portuguese stemming plus `unaccent`, so "horario"
  matches "horário" and "piscinas" matches "piscina".
- Query terms are OR-ed and ranked with `ts_rank_cd`, so a full question still finds
  passages that share only some of its words. The top 5 excerpts go to the model.
- Chunks are about 1,200 characters, split at paragraph and section ("Capítulo", "Seção")
  boundaries and never across pages.
- PDFs are read with `pypdf`. Scanned PDFs fail indexing with a clear reason (no OCR yet).
- A replacement upload deactivates the old version only after it indexes successfully.
- Excerpts are given to the model as tool output labelled as third-party reference
  material, never as instructions.

## Consequences
- No extra infrastructure for the MVP.
- Embedding provider choice and its LGPD processing terms are deferred.
