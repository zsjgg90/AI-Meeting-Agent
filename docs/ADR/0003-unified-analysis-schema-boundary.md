# ADR 0003: Unified Analysis Schema Boundary

Date: 2026-07-15

## Status

Accepted

## Context

The formal meeting analysis path already uses Qwen3 + RAG and validator logic, but the validated result was still a raw dictionary before persistence. API, database, and Expo also carried compatible but overlapping field names.

## Decision

Use `services/worker/app/meeting_analysis_schema.py` as the authoritative six-dimension business schema.

Add `services/worker/app/analysis_contract.py` as the formal boundary:

```text
raw model/validator dict -> MeetingAnalysisSchema -> DB-compatible payload
```

Expose `metadata.schema_version = meeting-analysis-v1` from the API summary response.

## Consequences

- Model output is no longer mapped directly to persistence payload in the formal Qwen3 + RAG path.
- API and frontend remain backward compatible.
- No database migration is required.
- Full prompt and RAG version tracking remains Phase 5.
