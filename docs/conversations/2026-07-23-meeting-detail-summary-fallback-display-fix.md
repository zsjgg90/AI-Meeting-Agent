# Meeting Detail Summary And History Loading Fix

## Development Goal

Fix two related historical meeting issues:

- A meeting detail page could show available summary content with a failed
  badge and raw `result_source=unknown` technical metadata.
- The history meeting page could time out because it loaded the full meeting
  list in one request and mobile fetches had no timeout guard.

## Background

The reported screenshot showed a meeting detail page with visible summary text,
but the summary card displayed a failed state and raw source metadata. The
backend fallback path for legacy `meeting_outputs.summary` returned an empty
metadata object, and the mobile page displayed raw metadata plus the meeting row
status even when summary content was available.

The history timeout came from the same area of the product: Expo requested the
unbounded `/meetings` list for history, and stalled network/API requests could
leave the screen waiting indefinitely.

## Implementation

- Added fallback summary metadata for legacy `MeetingOutput` responses in the
  `/meetings/{meeting_id}/summary` API.
- Changed the mobile meeting detail summary card to show user-facing source
  labels instead of raw `result_source=...`.
- Added summary-content-aware display status so stale `failed` or
  `summary_failed` meeting status does not make an available summary card look
  failed.
- Added `limit`/`offset` pagination to `GET /meetings`.
- Updated Expo history loading to fetch a bounded first page and load more on
  demand.
- Added mobile request timeout handling with a Chinese timeout error message.
- Added mobile static regression checks for meeting detail and history loading,
  both wired into the full local test script.

## Modified Content

- `services/api/app/routers/meetings.py`
- `services/api/tests/test_api_contract.py`
- `apps/mobile/src/api.ts`
- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
- `apps/mobile/src/screens/MeetingListScreen.tsx`
- `apps/mobile/scripts/test-meeting-detail-ui.js`
- `apps/mobile/scripts/test-meeting-history-ui.js`
- `apps/mobile/package.json`
- `scripts/test-all.ps1`
- `README.md`
- `docs/API_CONTRACT.md`
- `docs/CHANGELOG.md`
- `docs/TESTING.md`
- `SESSION_HANDOFF.md`

## Impact Scope

The fix affects meeting summary fallback DTO metadata and mobile meeting
detail/history display and loading logic. It does not change Prompt, RAG,
Validator, Shadow, meeting analysis generation, Agent write scope, production
config, or formal business write behavior.

## Testing Result

- `services\api\.venv\Scripts\python.exe -m unittest tests.test_api_contract`: passed, 11 tests.
- `cd apps\mobile; npm run typecheck`: passed.
- `cd apps\mobile; npm run test:meeting-detail-ui`: passed.
- `cd apps\mobile; npm run test:meeting-history-ui`: passed.
- `cd apps\mobile; npm run test:agent-review-ui`: passed.
- `.\scripts\test-all.ps1`: passed, including API contract tests, Agent API
  tests, Worker tests, mobile typecheck, Agent review UI static checks, and
  meeting detail/history UI static checks.

## Known Limits

This is a DTO/display/loading correction. It does not retroactively rewrite
stale meeting row statuses in the database.

## Follow-Up Suggestions

Add live mobile UI automation for meeting detail and history loading when the
React Native or device test harness is expanded.
