# ADR 0002: Keep API And Worker As Separate Runtime Boundaries

Date: 2026-07-15

## Status

Accepted

## Context

The product needs responsive mobile/API behavior while transcription, diarization, and LLM analysis may take longer. The current implementation separates public API responsibilities from heavy processing responsibilities.

## Decision

API Service owns:

- Public HTTP contracts.
- Upload acceptance.
- Task creation.
- Calling Worker.
- Read endpoints for mobile.

Worker Service owns:

- ASR.
- Speaker diarization.
- Transcript persistence.
- RAG retrieval.
- Ollama calls.
- Validator execution.
- Summary/action item persistence.

Expo must call API Service only.

## Consequences

- Worker endpoints are internal.
- API can remain mobile-facing and stable.
- Long-running processing can be isolated.
- API and Worker currently duplicate DB models; this is accepted for now but should be cleaned up later.

