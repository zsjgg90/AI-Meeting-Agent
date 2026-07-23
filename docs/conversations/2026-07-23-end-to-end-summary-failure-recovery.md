# End-to-End Summary Failure Recovery

## Development Goal

Fix the real meeting flow where uploaded recordings completed ASR and speaker
diarization but failed at meeting-summary generation.

## Background

The latest failed meeting was
`6387afc1-1287-4a45-b1e0-a2d33b8ca777`. It had one uploaded audio file, 49
transcript segments, 1344 transcript characters, and 5 speakers, but no
`meeting_summaries` row or generated action items. Direct Worker venv
diagnostics proved the formal Qwen3 + RAG path could analyze the same
transcript successfully.

## Root Cause

Local ports 8001 and 8002 were being served by stale uvicorn child processes
from the system Python runtime instead of the repository virtual environment
process tree. API background tasks also discarded Worker error response bodies,
so `transcription_tasks.error_message` only stored generic HTTP 500 text.
The mobile AI processing screen derived progress from partial meeting data and
could not show the real failed stage or retry summary analysis without upload.

## Implementation

- Added Worker structured error responses for `/meetings/{id}/process` and
  `/meetings/{id}/analyze`.
- Added API parsing of Worker non-2xx response bodies and JSON storage in the
  existing `transcription_tasks.error_message` column.
- Mapped processing failures with no transcript to `transcription_failed` and
  failures after transcript generation to `summary_failed`.
- Added API/Worker startup and service-check port owner validation that accepts
  Windows venv child processes only when their parent is the project venv
  Python process.
- Reworked `AIProcessingScreen` to use meeting status, latest task state, and
  structured task errors for stage display, retry, and safe error details.

## Impact Scope

The change affects API task orchestration, Worker HTTP error DTOs, local
service scripts, and the mobile AI processing screen. It does not modify
Prompt, RAG data, Validator rules, Shadow behavior, Agent write scope, or
production configuration defaults.

## Verification

- `npm run typecheck`
- `node apps/mobile/scripts/test-ai-processing-ui.js`
- `node apps/mobile/scripts/test-meeting-detail-ui.js`
- API upload and structured error tests
- Worker contract and structured endpoint error tests
- `.\scripts\test-all.ps1`
- `.\scripts\check-services.ps1`
- Real recovery of meeting `6387afc1-1287-4a45-b1e0-a2d33b8ca777`
- Real new meeting `5683fa7d-268d-4f2a-ac27-aadcc0df8a42` from uploaded `.m4a`
- `run_agent_phase15_final_acceptance.py`
- `run_agent_review_postgres_acceptance.py`

## Known Limitations

`run_meeting_pipeline_acceptance.py --limit 1 --ollama-timeout 120` still fails
the existing semantic shadow quality gate because
`owner_deadline_hallucination_count` is 1. This is separate from the formal
Qwen3 + RAG summary path fixed here and was not changed because this task
forbids Prompt, RAG, Validator, and Shadow modifications.

Two empty meetings were created by failed local acceptance script attempts
before the correct audio storage path was used. They were not processed and no
audio or summary was attached to them.
