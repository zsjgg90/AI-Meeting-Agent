# ADR 0001: Use Qwen3 + RAG As Formal Meeting Analyst

Date: 2026-07-15

## Status

Accepted

## Context

The project previously had OpenAI-based summary logic and rule-based fallback logic. The current formal analysis path uses Qwen3 through Ollama, enhanced by RAG rules and validator checks.

## Decision

The formal six-dimension meeting analysis engine is:

```text
Transcript
-> RAG Retrieval
-> Qwen3 via Ollama
-> Anti-hallucination Validator
-> MeetingSummary + ActionItem persistence
```

The model name must come from configuration. Current default:

```text
qwen3:14b
```

## Consequences

- Expo never calls Ollama directly.
- API never calls Ollama directly.
- Worker owns the model call.
- Prompt, RAG, and validator should not be modified during unrelated product/UI tasks.
- Future model upgrades should use config, not business logic edits.

