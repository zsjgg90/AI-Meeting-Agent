# ADR 0005: Testing and Observability Boundary

## Status

Accepted

## Context

The formal Meeting Analyst pipeline depends on PostgreSQL, Chroma, an embedding
model, Ollama, Qwen3, prompt templates, and the persistence contract. Default
local tests must be repeatable and must not require those runtime services.

At the same time, production failures must be diagnosable by stage and version:
RAG retrieval, prompt build, model inference, JSON parsing, validation, and
persistence.

## Decision

1. Default automated tests use fake model/RAG adapters for pipeline contract
   checks.
2. Live Qwen3 + RAG checks remain separate from default unit tests.
3. Worker emits structured JSON logs with sensitive content redacted.
4. API and Worker expose `/health` for liveness and `/ready` for dependency
   readiness.
5. A read-only `scripts/check-services.ps1` script validates local runtime
   dependencies before manual Expo testing.

## Consequences

- Default tests remain fast and deterministic.
- Debugging can identify the failed pipeline stage without logging full meeting
  transcripts or prompts.
- Real model quality still requires live evaluation; fake tests only prove
  wiring, schema, and metadata behavior.
- Readiness checks are intentionally shallow for RAG and do not run embedding
  inference.
