# Observability

## Goals

The meeting analysis pipeline must be debuggable without logging sensitive
meeting content. Runtime logs should answer:

- Which stage failed?
- Which model, prompt version, schema version, and RAG dataset were used?
- How long did each stage take?
- Was the failure caused by dependency connectivity, schema validation, model
  output, or persistence?

## Structured Log Events

Worker logs are emitted as JSON lines through `services/worker/app/observability.py`.

Important events:

- `analysis.started`
- `pipeline.stage.started`
- `pipeline.stage.completed`
- `pipeline.stage.failed`
- `ollama.request`
- `ollama.completed`
- `ollama.failed`
- `analysis.completed`
- `summary.started`
- `summary.completed`
- `summary.failed`

Key fields:

- `pipeline_stage`
- `duration_ms`
- `model_name`
- `prompt_version`
- `schema_version`
- `rag_chunk_ids`
- `rag_dataset_version`
- `rag_collection_name`
- `rag_embedding_model`
- `result_source`
- `transcript_chars`
- `rag_chunk_count`
- `prompt_chars`
- `ollama_timeout`
- `ollama_duration_ms`
- `total_duration_ms`
- `failure_reason`
- `error_type`
- `error_code`
- `retryable`

## Redaction Rules

The logger must not emit raw:

- full meeting transcripts
- full prompts
- full RAG context
- raw model output
- API keys, tokens, passwords, DB passwords
- personal phone numbers, emails, or local Windows user paths

Large content fields are represented as:

```json
{
  "sha256": "content_hash",
  "length": 1234
}
```

## Readiness Endpoints

API:

```text
GET /health
GET /ready
```

API `/ready` checks:

- PostgreSQL connectivity
- Worker `/health`

Worker:

```text
GET /health
GET /ready
```

Worker `/ready` checks:

- PostgreSQL connectivity
- Prompt registry file availability
- Ollama `/api/tags` and configured model availability
- RAG Chroma collection availability, without loading the embedding model

## Local Diagnostics

Use:

```powershell
.\scripts\check-services.ps1
```

The script is read-only. It does not start, stop, reset, or rebuild services.

## Real Production Analysis Debug

Use the single-meeting live diagnostic script when a real Qwen3 + RAG result
must be separated from fixture and semantic shadow outputs:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
```

It writes raw debug artifacts to:

```text
data/debug/real_production_analysis/<meeting_id>/
```

The `pipeline.log` records transcript length, RAG chunk count, prompt length,
Ollama model, timeout, Ollama duration, total duration, failure reason, and
`result_source=legacy_qwen_rag`.

## Known Limits

- Worker `/ready` checks RAG collection metadata only. It does not run a live
  retrieval query because that would load the embedding model.
- The default test suite uses fake model/RAG adapters. Real Qwen3 + RAG quality
  must be verified with live evaluation scripts.
- API background task errors still persist a safe text message in
  `TranscriptionTask.error_message`; full exception traces should stay in logs.
