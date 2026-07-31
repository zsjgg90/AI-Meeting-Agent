# Project State

Last reviewed: 2026-07-18

## Maintainability Phase Plan

The active seven-phase maintainability plan is documented in:

- `docs/PHASE_PLAN.md`

Current next phase:

- Phase 7: Final Verification And Session Handoff

## Product Goal

MeetMind AI is an AI meeting agent. The current product flow is:

1. User creates a meeting in Expo.
2. User records and uploads audio.
3. API stores audio and starts processing.
4. Worker transcribes audio and assigns speaker labels.
5. Worker generates six-dimension meeting analysis through Qwen3 + RAG.
6. API returns transcript, summary, action items, conclusions, issues, and risks.
7. Expo displays meeting notes, transcript, tasks, history, and profile pages.

## Active Runtime Modules

- Mobile: `apps/mobile`
- API: `services/api`
- Worker: `services/worker`
- PostgreSQL migrations: `services/api/alembic`
- Local storage: `storage`
- RAG rules: `data/rag/meeting_analyst_rag_350_chunks.jsonl`
- Chroma database: `data/vector_db`

## Deprecated Or Legacy Areas

These directories are early prototypes and should not be used for active development:

- `api`
- `mobile`

## Current AI Analysis Model

- Formal model: `qwen3:14b`
- Runtime: Ollama
- Retrieval: Chroma + `meeting_analyst_rules`
- Postprocessor: `services/worker/app/meeting_analysis_postprocessor.py`
- Validator: `services/worker/app/anti_hallucination_validator.py`
- Main entry: `services/worker/app/meeting_analyst_service.py`

## Current Independent Experimental Module

Sentence-level semantic event recognition exists as an independent module:

- `services/worker/app/semantic_event_schema.py`
- `services/worker/app/semantic_event_extractor.py`
- `services/worker/app/semantic_event_validator.py`
- `services/worker/app/semantic_clause_splitter.py`

It is not yet wired into the formal Analyze API.

## Current Analysis Schema Boundary

- Authoritative schema: `services/worker/app/meeting_analysis_schema.py`
- Formal normalization boundary: `services/worker/app/analysis_contract.py`
- Deterministic post-normalization boundary:
  `services/worker/app/meeting_analysis_postprocessor.py`
- API summary metadata exposes `schema_version=meeting-analysis-v1`.
- Prompt/RAG metadata exposes `prompt_version`, `rag_chunk_ids`, and RAG dataset metadata after migration `20260715_0011`.
- Details: `docs/SCHEMA_AND_BOUNDARIES.md`

## Current Prompt And RAG Version Boundary

- Formal prompt registry: `services/worker/app/prompt_registry.py`
- Formal prompt template: `services/worker/app/prompts/meeting_analyst_qwen3.md`
- Prompt version: `meeting-analyst-v1`
- RAG manifest: `data/rag/meeting_analyst_rag_manifest.json`
- RAG dataset version: `meeting_analyst_rag_v1`
- RAG chunk schema version: `rag-chunk-v1`
- Details: `docs/PROMPT_AND_RAG_VERSIONING.md`

## Current Testing And Observability Boundary

- Unified local checks: `scripts/test-all.ps1`
- Local dependency diagnostics: `scripts/check-services.ps1`
- Offline meeting-analysis evaluation: `scripts/evaluate_meeting_analysis.py`
  with schema/metric/report assets under `data/eval/`.
- API and Worker expose `/health` and `/ready`.
- Worker analysis logs use structured JSON events with redacted prompt,
  transcript, RAG context, and raw model output.
- Default tests use fake model/RAG adapters and do not require Ollama, Qwen3,
  Chroma, PostgreSQL, or real audio services.
- Phase 0 evaluation compares existing `expected.json` and `actual.json` files
  only; it is not connected to API, Worker, DB, Mobile, Prompt, RAG, Qwen3, ASR,
  or the semantic pipeline.
- Details: `docs/OBSERVABILITY.md`
