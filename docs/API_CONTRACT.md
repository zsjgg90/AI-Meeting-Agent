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

## Task Endpoints

- `GET /tasks`

Supports:

- `limit`, max 15
- `offset`
- `meeting_id`
- `q`

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
