# 0006: Postgres full-text search first, vectors later

**Status:** Proposed (2026-10-22). Revisit with Milestone 3 evals.

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

## Consequences
- No extra infrastructure for the MVP.
- Embedding provider choice and its LGPD processing terms are deferred.
