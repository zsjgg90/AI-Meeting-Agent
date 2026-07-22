# Mobile Recent Meetings Loading Fix

## Development Goal

Fix the issue where recent meetings stayed in a loading/analyzing state after
starting local services.

## Background

The latest local meeting returned by the API had status `audio_uploaded`. The
Expo recent-meeting list normalized `audio_uploaded` and `uploaded` to
`analyzing`, displayed the AI analysis progress block, and blocked opening the
meeting detail page. Separately, API background tasks do not survive service
restart, so stale `queued` or `running` task rows could leave meetings in
`processing` or `summarizing`.

## Implementation

- Added a distinct mobile display status for uploaded meetings.
- Limited home summary-stat fetches to completed meetings.
- Updated local Expo API base URL to port 8002.
- Added API startup recovery for stale active meeting tasks.
- Added unit coverage for uploaded, summarizing, and completed recovery paths.

## Modified Content

- `apps/mobile/src/screens/MeetingListScreen.tsx`
- `apps/mobile/.env`
- `services/api/app/main.py`
- `services/api/app/services/meeting_task_recovery.py`
- `services/api/tests/test_meeting_task_recovery.py`
- `docs/CHANGELOG.md`
- `docs/CURRENT_TASKS.md`
- `docs/TESTING.md`
- `SESSION_HANDOFF.md`

## Impact

Uploaded meetings now display as `已上传` and show `待处理` duration text. Only
true active processing statuses display the AI analysis progress UI. On API
startup, stale active tasks are marked failed and affected meetings are returned
to the most accurate retryable or terminal state based on existing summary,
transcript, and audio rows.

## Tests

- `npm run typecheck` in `apps/mobile`
- `services/api/.venv/Scripts/python.exe -m compileall -q services/api/app`
- `services/api/.venv/Scripts/python.exe -m unittest tests.test_meeting_task_recovery`

## Known Limits

This fix does not automatically start processing or analysis for uploaded
meetings. Users still need to use the existing process/analyze flow.
