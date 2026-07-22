# Recording Upload And End-to-End Regression

## Development Goal

Fix the recording upload regression and re-run the relevant local checks for the
meeting flow from creation and upload through analysis display and Agent
review/control boundaries.

## Background

Expo recording upload failed in the mobile flow, and history meeting loading had
recently timed out after prior changes. The fix had to stay within the existing
API/Worker/Expo boundaries and must not modify Prompt, RAG, Validator, Shadow,
production config, or Agent write scope.

## Implementation

- Routed `uploadAudio` and `uploadAudioChunk` through the shared mobile request
  timeout wrapper.
- Added Chinese user-facing upload error mapping for unsupported audio, empty
  recordings, missing meetings, server errors, and generic upload failures.
- Preserved Expo `.m4a` upload metadata as `audio/x-m4a`.
- Switched realtime chunk transcription calls from an unbounded Worker HTTP
  request to the configured finite Worker request timeout.
- Added API regression tests for Expo-style m4a upload success and empty upload
  rejection.
- Added mobile static checks for upload timeout/error handling and the
  record-upload-process-analyze call sequence.
- Kept the bounded meeting history loading fix in place with mobile static
  coverage.

## Modified Files

- `apps/mobile/src/api.ts`
- `apps/mobile/package.json`
- `apps/mobile/scripts/test-recording-upload-ui.js`
- `apps/mobile/scripts/test-meeting-detail-ui.js`
- `apps/mobile/scripts/test-meeting-history-ui.js`
- `services/api/app/routers/meetings.py`
- `services/api/tests/test_meeting_upload_api.py`
- `scripts/test-all.ps1`
- `docs/CHANGELOG.md`
- `docs/CURRENT_TASKS.md`
- `docs/TESTING.md`
- `SESSION_HANDOFF.md`

## Impact Scope

Recording uploads now fail faster with readable Chinese messages instead of
waiting indefinitely or surfacing raw backend bodies. Backend upload persistence
still only writes `meetings` status/end time and `audio_files` metadata for the
uploaded recording. Realtime chunk transcription still delegates to Worker, but
now uses a finite timeout.

No Prompt, RAG data, Validator logic, Shadow promotion, Agent write scope,
Requirement writes, Risk writes, or production config were changed.

## Tests

- `npm run typecheck`
- `npm run test:meeting-detail-ui`
- `npm run test:meeting-history-ui`
- `npm run test:recording-upload-ui`
- `services/api/.venv/Scripts/python.exe -m unittest tests.test_meeting_upload_api`
- `services/api/.venv/Scripts/python.exe -m unittest tests.test_api_contract tests.test_agent_config tests.test_agent_confirmation_api tests.test_meeting_upload_api`
- `scripts/test-all.ps1`
- Local API HTTP smoke: `POST /meetings`, `POST /meetings/{id}/audio`, `GET /meetings/{id}`, `DELETE /meetings/{id}`
- `services/api/.venv/Scripts/python.exe services/api/scripts/run_agent_phase15_final_acceptance.py`
- `services/api/.venv/Scripts/python.exe services/api/scripts/run_agent_review_postgres_acceptance.py`
- `scripts/check-services.ps1`
- `git diff --check`

## Results

All targeted upload, history loading, API, Agent review, Phase 15, service
health, and full local checks passed. The local HTTP upload smoke confirmed a
created meeting accepted an `audio/x-m4a` multipart upload and transitioned to
`audio_uploaded`; the smoke meeting was deleted afterward.

The live `run_meeting_pipeline_acceptance.py --limit 1 --ollama-timeout 120`
run produced a report where legacy Qwen3 + RAG succeeded, but the independent
semantic pipeline quality gate failed with one owner/deadline hallucination.
That quality failure is outside this upload/history fix and was not modified
because Prompt, RAG, Validator, and Shadow are out of scope for this task.

## Known Limits

The upload smoke uses synthetic bytes to validate HTTP upload and persistence;
it does not prove production ASR quality for a real recorded voice file. Live
semantic pipeline quality remains a separate follow-up before considering any
formal semantic output promotion.
