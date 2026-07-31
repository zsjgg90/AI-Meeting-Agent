# Task Detail Real API Persistence

## Development Goal

Connect the mobile task detail page to real backend persistence for editable
task fields, reminders, and task attachments.

## Background

The mobile task detail page already opened from Todo and task-search cards and
used the real task list data. The remaining editable fields and attachments
needed to stop being local-only UI state.

## Implementation

- Added persistent task detail fields on `action_items`: `description`,
  `reminder_offset_minutes`, and `reminder_channel`.
- Added a `task_attachments` table and server storage path under
  `storage/tasks/{task_id}/attachments`.
- Added `PATCH /tasks/{task_id}` for title, description, owner, due date,
  priority, reminder offset, and reminder channel.
- Added `POST /tasks/{task_id}/attachments` and
  `GET /tasks/{task_id}/attachments/{attachment_id}`.
- Updated the mobile API client with task edit, attachment upload, and
  attachment URL helpers.
- Updated `TaskDetailScreen` so title, description, owner, due date, priority,
  reminder time, and attachments use real APIs.
- Changed associated meeting in task detail to read-only display.
- Updated Todo and task-search due-date rendering to compact local display such
  as `7-15 14:00`.

## Modified Files

- `services/api/app/models.py`
- `services/api/app/schemas.py`
- `services/api/app/routers/tasks.py`
- `services/api/app/services/storage.py`
- `services/api/alembic/versions/20260729_0017_task_detail_editing_and_attachments.py`
- `services/api/tests/test_tasks_api.py`
- `services/api/tests/test_api_contract.py`
- `apps/mobile/src/api.ts`
- `apps/mobile/src/screens/TaskDetailScreen.tsx`
- `apps/mobile/src/screens/TodoScreen.tsx`
- `apps/mobile/src/screens/TaskSearchScreen.tsx`
- `apps/mobile/scripts/test-task-detail-ui.js`
- `docs/API_CONTRACT.md`
- `docs/CURRENT_TASKS.md`
- `docs/CHANGELOG.md`
- `apps/mobile/README.md`
- `SESSION_HANDOFF.md`

## Impact

Task detail edits now persist across refreshes and are reflected in Todo and
task-search after returning from the detail overlay. Attachments are stored on
the API server and associated with the current task. The source meeting row is
not a navigation control.

## Tests

- `npm run typecheck`
- `npm run test:task-detail-ui`
- `npm run test:todo-ui`
- `npm run test:task-search-ui`
- `.venv\Scripts\python.exe -m compileall -q app alembic\versions`
- `.venv\Scripts\python.exe -m unittest tests.test_tasks_api tests.test_api_contract`

## Known Limits

- There is still no dedicated `GET /tasks/{task_id}` endpoint; task detail
  refresh remains a best-effort lookup through `GET /tasks`.
- SMS delivery is not implemented. The task detail page persists
  `reminder_channel="sms"` only as the selected reminder channel for later SMS
  integration.
- Task attachment delete is not exposed because no delete API was added.
