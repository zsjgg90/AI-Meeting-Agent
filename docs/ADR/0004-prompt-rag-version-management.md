# ADR 0004: Prompt And RAG Version Management

Date: 2026-07-15

## Status

Accepted.

## Context

The formal Meeting Analyst chain depends on three versioned assets:

- The Qwen3 prompt.
- The RAG rule dataset.
- The `meeting-analysis-v1` output schema.

Before this ADR, the formal prompt was embedded in Python code and RAG retrieval
returned only text context, so summary metadata could not identify the exact
prompt version or retrieved RAG chunks.

## Decision

1. The formal prompt body is stored in
   `services/worker/app/prompts/meeting_analyst_qwen3.md`.
2. `services/worker/app/prompt_registry.py` owns prompt id, prompt version, and
   schema version binding.
3. RAG dataset metadata is stored in
   `data/rag/meeting_analyst_rag_manifest.json`.
4. `RagRetriever.build_context_payload()` returns both prompt context text and
   retrieved chunk metadata.
5. Analysis metadata persists `prompt_version` and actual `rag_chunk_ids`.
6. API summary metadata exposes the persisted prompt/RAG trace fields.

## Consequences

- Future prompt upgrades require a new prompt version and registry update, not
  changes across business logic.
- Future RAG dataset upgrades require a new manifest/dataset version and import.
- Existing six-dimension API fields remain compatible.
- A small Alembic migration is required because previous persistence did not
  have prompt/RAG metadata columns.
