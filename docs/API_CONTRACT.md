# API Contract

Base URL in local Windows development is usually:

```text
http://127.0.0.1:8002
```

For Expo Go on a real phone, use the computer LAN IP:

```text
http://{LAN_IP}:8002
```

## Meeting Endpoints

- `POST /meetings`
- `GET /meetings`
- `GET /meetings/{meeting_id}`
- `PATCH /meetings/{meeting_id}`
- `DELETE /meetings/{meeting_id}`
- `POST /meetings/bulk-delete`
- `POST /meetings/{meeting_id}/audio`
- `POST /meetings/{meeting_id}/audio-chunks`
- `GET /meetings/{meeting_id}/audio/{audio_file_id}`
- `POST /meetings/{meeting_id}/process`
- `POST /meetings/{meeting_id}/analyze`
- `GET /meetings/{meeting_id}/transcript`
- `GET /meetings/{meeting_id}/summary`
- `GET /meetings/{meeting_id}/exports/{kind}.{file_format}`
- `PUT /meetings/{meeting_id}/speakers/{speaker_label}`
- `POST /meetings/{meeting_id}/knowledge/reindex`

## Task Endpoints

- `GET /tasks`

Supports:

- `limit`, max 15
- `offset`
- `meeting_id`
- `q`

## Knowledge Endpoints

Knowledge APIs are API-side read models over PostgreSQL. They read only active
knowledge items generated from completed meetings that have a formal
`meeting_summaries` row. They do not call Worker, Ollama, Chroma, Prompt, RAG,
Validator, or Agent write paths.

- `GET /knowledge/overview`
- `GET /knowledge/meetings`
- `GET /knowledge/decisions`
- `GET /knowledge/issues`
- `GET /knowledge/risks`
- `GET /knowledge/search`

List endpoints return:

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

Supported MVP filters:

- `query`
- `content_type`
- `meeting_type`
- `date_from`
- `date_to`
- `limit`
- `offset`

`meeting_type` is accepted for contract stability, but project and meeting
type filtering remain effectively closed until those fields are consistently
present on meeting data. Project filtering is intentionally not exposed in MVP.

Knowledge item fields:

- `id`
- `content_type`
- `title`
- `content`
- `meeting_id`
- `meeting_title`
- `meeting_date`
- `evidence_text`
- `source_segment_id`
- `speaker_label`
- `start_time`
- `end_time`
- `highlight`

Manual retry:

- `POST /meetings/{meeting_id}/knowledge/reindex`

The retry requires a completed meeting and a formal summary. It re-runs the
same idempotent sync path and returns the `meeting_knowledge_syncs` row.

## Feedback Endpoints

- `POST /feedback`

## Worker Endpoints

Worker endpoints are internal and should be called by API, not Expo:

- `GET /health`
- `POST /warmup`
- `POST /meetings/{meeting_id}/process`
- `POST /meetings/{meeting_id}/analyze`
- `POST /meetings/{meeting_id}/transcribe-chunk`

## Processing Task Behavior

`POST /meetings/{meeting_id}/process` and `POST /meetings/{meeting_id}/analyze` are idempotent while a task is active for the same meeting. If a `queued` or `running` task already exists, API returns that task instead of creating a duplicate.

API calls to Worker use `WORKER_REQUEST_TIMEOUT_SECONDS`. When the timeout is reached, the task is marked `failed` and the meeting is moved to `failed` or `summary_failed` instead of staying in `processing` or `summarizing` indefinitely.

## Summary Response Contract

`GET /meetings/{meeting_id}/summary` returns the canonical six-dimension analysis fields:

- `meeting_agenda`
- `meeting_summary`
- `key_conclusions`
- `action_items`
- `unresolved_issues`
- `risks_and_focus`
- `topics`
- `metadata.schema_version`

Current `metadata.schema_version`:

```text
meeting-analysis-v1
```

`metadata.result_source` distinguishes summary provenance:

- `fixture`: manual gold answer fixture, not AI quality evidence
- `legacy_qwen_rag`: formal production Qwen3 + RAG result
- `semantic_pipeline`: semantic shadow/debug result
- `unknown`: legacy or incomplete metadata

Legacy aliases such as `overview`, `agenda`, `decisions`, `risks`, and `open_questions` remain for compatibility. New frontend code should prefer the canonical fields.

Expo currently renders list-style summary dimensions as ordered lists: meeting
agenda, key conclusions, action items, unresolved issues, and risks/focus. The
mobile formatter accepts arrays or packed strings, strips embedded list markers
such as `1.` and `1、`, and splits only on numbering, newlines, or semicolons.
It must not split ordinary sentences on commas or periods.
