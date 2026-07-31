# Mobile Task Detail Reference Layout

## Goal

Restyle the Expo mobile task detail page to follow the provided reference image:
a top current-task card, grouped basic information, reminder settings, and an
attachment area. Keep the task checkbox to the left of the title, and allow the
title and description to be edited directly.

## Background

The task detail page already used real `/tasks` data and the formal task status
update endpoint. The existing layout was still a linear detail card, while the
requested direction was a compact grouped mobile form. The backend still has no
general task edit API, reminder API, or task attachment upload API.

## Implementation

`TaskDetailScreen` was rebuilt with a top `Current task` card containing the
square completion checkbox, editable task title, and editable task description.
The old linear information layout was replaced by grouped sections for basic
information, reminder settings, and attachments. The user-facing Chinese label
is `基本信息`; the previous `基本配置` wording is not used.

The status checkbox still calls the real `PATCH /tasks/{task_id}/status`
endpoint with optimistic UI and rollback. Source meeting lookup still uses
`getMeeting(meeting_id)` and opens the existing meeting detail route on the
`actions` tab with evidence anchors when available.

## Changes

- Rebuilt `apps/mobile/src/screens/TaskDetailScreen.tsx` JSX and styles.
- Kept the square checkbox to the left of the editable title.
- Made the task description directly editable inside the top task card.
- Added grouped sections for `基本信息`, reminder settings, and attachments.
- Updated `apps/mobile/scripts/test-task-detail-ui.js` to cover the new layout.
- Updated `docs/CHANGELOG.md` and `SESSION_HANDOFF.md`.

## Impact

This affects the Expo mobile task detail page and its static UI test. It does
not modify API, database, Worker, Prompt, RAG, Validator, or the six-dimension
schema.

## Tests

- `npm run typecheck`: passed.
- `npm run test:task-detail-ui`: passed.
- `npm run test:todo-ui`: passed.
- `npm run test:task-search-ui`: passed.
- `.\scripts\test-all.ps1`: passed, including Python compile, API contract
  tests, Worker unit tests, Mobile TypeScript typecheck, and mobile static UI
  checks.

## Known Limits

- Task status is still the only backend-persisted update field.
- Title, owner, due time, and priority changes sync only within the current App
  session.
- Description and note attachments remain local task-detail data and are not
  persisted.
- Reminder settings have no formal backend API and are displayed as local
  non-persistent defaults.

## Follow-Up

If these fields must persist across reloads, define formal task edit, reminder,
and attachment APIs before wiring persistence.
