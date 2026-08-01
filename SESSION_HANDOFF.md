# Session Handoff

## Current State

Latest Stage7.3.x Action Extraction Calibration is complete. Explicit
evidence-grounded requirement actions such as `需要验证`, `需要同步`,
`需要更新`, `需要排查`, `后续安排`, and `下一步完成` can remain in
`action_items`; suggestion, consideration, uncertainty, and discussion-only
statements remain blocked. New actual outputs were generated under
`data/eval/reports/stage7_golden_regression/latest_runs_stage7_3_x/`.
Latest metrics are `decision_precision=0.8000`, `task_recall=0.5000`,
`risk_recall=0.8000`, `hallucination_rate=0.0000`, and
`evidence_coverage=1.0000`. Stage7.4 RC1 Freeze is conditional because Task
Recall improved but remains the main limitation.

Latest Stage7 Golden Regression note: `project_delivery_001` now exercises the
Worker anti-hallucination validator boundary for proposal-vs-decision,
unresolved-vs-decision, suggestion-vs-action, explicit-risk evidence, and
source alignment. The validator removes unresolved/conditional statements from
`key_conclusions`, removes direction-only or weak suggestion action items,
filters inferred risks without explicit risk wording in `source_text`, and
keeps true undecided matters in `unresolved_issues`. The latest report is
`data/eval/reports/stage7_project_delivery_report.json`:
`decision_precision=1.0`, `task_recall=0.0`, `risk_recall=1.0`,
`hallucination_rate=0.0`, `evidence_coverage=1.0`. Task recall remains 0.0
because the expected task `整理数据和反馈样本` and deadline `待确认` are not supported
by `data/eval/golden_cases/project_delivery_001/transcript.txt`.

Latest evaluation note: Phase 0 Evaluation System now exists as an offline-only
framework under `data/eval/` with schema, metric notes, report location, and
`scripts/evaluate_meeting_analysis.py`. It compares existing `expected.json`
and `actual.json` files, optionally checks transcript evidence, and reports
Decision Precision, Task Recall, Risk Recall, Hallucination Rate, and Evidence
Coverage. Unit coverage is `python -m unittest tests.test_evaluate_meeting_analysis`.
It is not wired into API, Worker, DB, Mobile, ASR, Semantic Pipeline, Prompt,
RAG, or Qwen3/Ollama.

Latest mobile history page note: the full `历史会议` page now shows the loaded
meeting count in the AppHeader title as `历史会议（n）`. The separate `共 n 场会议`
subtitle above the date sections was removed, selection controls use black
text, and the history list/date section spacing is tightened upward. The
change is UI-only and does not alter meeting pagination, API contracts,
backend, Worker, Prompt/RAG/Validator, schema, or database behavior.

Latest mobile push config note: Profile `推送配置` now opens an independent
React Native page for Feishu push, email push, and SMS reminders. The page is
positioned as an AI meeting result distribution center, but the project has no
formal Feishu, email, SMS, push-config, or push-history API. All channel
switches remain disabled/off and the page shows `未配置`, `暂未开放`, and `待接入`
states only. It does not add OAuth, SMTP, SMS provider integration, backend
endpoints, database fields, push history, Worker logic, Prompt/RAG/Validator
changes, or fake connection/delivery success.

Latest mobile voiceprint note: Profile `声纹管理` now opens independent
React Native pages for voiceprint management and add-sample recording. The
management page shows `声纹识别` as unavailable, explains that future enablement
would identify and label different speakers, renders a truthful empty list
instead of prototype fake users, and links to sample recording. The add-sample
page collects a user name, shows fixed朗读文本, and uses a page-local
`expo-av` `Audio.Recording` instance to start/stop a local sample. There is no
formal voiceprint API in the project; save only reports `待接入接口` and does not
upload, register, identify, create meetings, run transcription, run AI
analysis, or touch Worker/Prompt/RAG/Validator/schema/database code.

Latest Worker title note: the formal Qwen3 + RAG call now returns internal
`meeting_type`, `meeting_type_confidence`, `meeting_title_candidate`, and
`title_basis` fields for title handling. Worker still makes no separate title
model request and still only updates unchanged fallback titles. The deterministic
title gate now requires a fixed meeting-type enum, confidence at least `0.70`,
two valid title bases, and rejects generic/explanatory/JSON/Markdown/multiline
titles plus task-like titles that combine time words and action words. Failure
keeps `YYYY-MM-DD HH:mm 实时录音/文件导入` and does not affect six-dimension summary
persistence. Version-number dots such as `V3.2` are allowed only inside the
version token.

Latest live title audit note: `services/worker/scripts/run_meeting_title_live_audit.py`
ran a controlled 24-sample live Qwen3 + RAG title audit without database writes
or separate title model calls. Final report:
`data/debug/title_regression/20260730_title_live_phase2/title_live_audit_report.md`.
Current baseline is 23 acceptable/accurate titles, 1 safe fallback, 0 local
action-item title leaks, 0 missing meeting types, 0 missing or duplicate title
bases, and all confidences in `0.90-1.00`. The only remaining fallback was a
meeting-level project weekly title containing both `下周` and `确认`; it was
left as safe fallback because it is a single rule-strictness case.

Latest title regression audit note: `services/worker/scripts/run_meeting_title_regression_audit.py`
uses existing real/debug/acceptance transcript files and deterministic title
payloads to audit the title gate without database access or Qwen3 calls. The
2026-07-30 report under `data/debug/title_regression/` covered 8 samples:
4 accepted, 4 rejected, 4 safe fallbacks, and 0 local-issue leaks after adding
the narrow role-plus-action rejection for titles such as `后端接口优化确认会`.

Latest meeting-list agenda note: the compact home/history meeting card now
reads `record.item` when extracting preview text from structured summary items.
This fixes `meeting_agenda` rows returned as `{ item: "..." }` being hidden as
empty. API summary fetching and backend payloads were not changed.

Latest mobile realtime recording note: ending a recording now reads the local
Expo recording URI before `stopAndUnloadAsync()` and no longer discards a valid
recording only because the UI elapsed timer is still under one second. The home
compact meeting list hides the `未生成摘要` status badge for unrecorded `pending`
meetings.

Latest mobile meeting-list note: the compact meeting card preview now includes
`会议总结` before `会议议程`, `核心结论`, and `待办事项`. The history/all-meetings page
uses the same compact card as the home list while retaining selection,
pagination, refresh, and swipe-delete behavior.

Latest compact card field note: completed meeting cards now support four
preview dimensions, `会议总结`, `会议议程`, `核心结论`, and `待办事项`, using the
existing summary fields. Dimensions without valid recognized text are omitted
instead of showing `暂无`, so compact cards shrink with the available content.

On 2026-07-29 realtime recording was refactored into a home-screen overlay.
The home `实时录音` action still creates the fallback-titled meeting first, but it
now keeps the user on the home route, expands the mounted recording overlay,
and starts the real `expo-av` recorder there. The overlay supports `expanded`
and `collapsed` display states; collapsed renders a mini recording bar above
BottomNav, and both states share the same recording object, elapsed timer,
pause/resume state, meeting id, metering-backed waveform, and stop/discard
handlers. Dragging the top handle collapses without releasing recorder
resources. The recording sheet now omits the language selector, right-side
close button, central microphone prompt, transcript placeholder copy, and
one-hour limit banner. The bottom player keeps only 10 soundprint bars, a
smaller timer, pause/resume, and direct end controls. End no longer opens a
second confirmation: it calls `stopAndUnloadAsync()`, shows
`已进入AI结构化分析` for 500 ms, clears the overlay session, returns to home, and
runs upload/process/analyze in the mobile background flow. The just-ended
meeting is now also injected into the home/all meeting lists as `processing`,
so the existing `处理中` loading badge appears immediately after the 500 ms
return-home handoff. Mobile still does
not show fake live transcripts. No backend, Worker, Prompt/RAG, Validator,
schema, file import, meeting detail, knowledge, or todo behavior was
intentionally changed.

On 2026-07-29 meeting creation and title generation were optimized. The home
Realtime Recording action now creates a meeting directly with local-time
fallback title `YYYY-MM-DD HH:mm 实时录音`, disables repeat taps while creating,
and enters `RecordingScreen` without `NewMeetingScreen`; the old route remains
available for compatibility. Audio import now creates `YYYY-MM-DD HH:mm 文件导入`
after file selection and reuses the existing `AIProcessingScreen`
upload/process/analyze flow. Alembic revision `20260729_0018` adds
`meetings.title_source` with `fallback`, `ai_generated`, and `user_edited`.
`PATCH /meetings/{id}` can update titles and marks them `user_edited`; meeting
detail exposes this through the existing more-menu modal. The Worker formal
analysis schema includes `meeting_title`, supplied by the same Qwen3 + RAG
call, then validates it in `services/worker/app/meeting_title.py` before
`save_summary()` replaces only unchanged fallback titles. Invalid, generic, or
empty title candidates are ignored and do not affect summary persistence,
meeting status, or knowledge sync.

Also on 2026-07-29 `RecordingScreen` was rebuilt from
`docs/design/meetmind-app_meeting-recording.html` without adding a new recording
pipeline. The home Realtime Recording action still creates the meeting first,
then the recording page now starts the existing `expo-av` recorder
automatically, displays the fallback title and local create time, shows a
truthful post-meeting transcription prompt instead of fake live transcript
rows, uses `pauseAsync()`/`startAsync()` for real pause/resume, uses
`stopAndUnloadAsync()` once, returns directly to the home list after ending,
and starts upload/process/analyze from the mobile background flow. It requires
confirmation only before discarding. Abandoned or under-one-second
automatic recordings call the existing meeting delete cleanup so empty
meetings do not remain in the list. Waveform rendering uses `expo-av` metering
when the platform reports it and falls back to a light status animation when
metering is unavailable. File import still uses `AIProcessingScreen`, which
displays the latest polled meeting title so successful AI title replacement can
appear on the processing screen before opening details. The mobile client still does not include
`@siteed/audio-studio` PCM streaming, so realtime ASR/speaker separation is not
shown during recording even though backend realtime endpoints exist.

On 2026-07-29 the Expo task detail page was updated for editable mobile task
details with real task-detail persistence. The page now uses a compact
reference-style layout: a top `当前任务` card contains the square checkbox,
editable title, and editable description; below it are grouped `基本信息`,
reminder-setting, and attachment sections. The detail checkbox uses
`PATCH /tasks/{task_id}/status` with optimistic UI and rollback; completed
tasks show a grey strikethrough title. The top-right edit icon was removed.
Title, description, owner, due date, priority, reminder offset, and reminder
channel now persist through `PATCH /tasks/{task_id}` and sync back to the
current App-session Todo/search data. Source meeting remains read-only and is
looked up with `getMeeting`; missing or deleted meetings show unavailable
copy and are not clickable from task detail. Task attachments are selected
with `expo-document-picker`, uploaded through
`POST /tasks/{task_id}/attachments`, and opened through the task attachment
download endpoint.

On 2026-07-28 the Expo `我的待办` home was rebuilt from
`docs/design/meetmind-app_todo.html` while staying on the existing `/tasks`
API. `TodoScreen` now renders one `FlatList` with a real top bar, search
state, real loaded-task statistics for open/completed/overdue, filters,
pull-to-refresh, load-more pagination, deadline/overdue formatting,
priority/status/owner tags, and source-meeting navigation into the existing
meeting detail `actions` tab. Task status controls are intentionally
read-only because no ordinary task update endpoint is exposed to this mobile
surface; tapping the status icon shows that the current version does not
support updating task status and does not mutate local completion state. The
page keeps the existing `BottomNav` and does not touch backend, database,
Worker, Prompt, RAG, Validator, or six-dimension schema behavior.
The separate all/open/completed/overdue tab row was later removed, while the
three statistic cards remain visible. Task status indicators now use square
checkbox styling, and both the title and checkbox enter the same read-only
status action.
The Todo search button now opens an independent `TaskSearchScreen` overlay
without bottom navigation. The page reuses `GET /tasks?q=...` through
`listTasks`, uses explicit keyboard-search submission with stale-request guards,
renders real task cards, opens source meetings on the existing detail `actions` tab, and
stores only recent non-empty keywords in AsyncStorage with a 10-item cap. No
backend search or history endpoint was added.
Todo status updates are now backed by the formal
`PATCH /tasks/{task_id}/status` API for `open` and `completed`. Todo cards and
task-search result cards render only checkbox, title, deadline, and priority;
checkbox and title presses perform optimistic real updates with per-task
loading and failure rollback. Task search no longer sends requests while the
user types; it requests results only after keyboard search submission, retry,
load-more, or recent-search selection.

On 2026-07-28 the Expo Knowledge Base home was rebuilt from
`docs/design/meetmind-app_knowledge-base.html` inside the existing
`KnowledgeBaseScreen`. It remains an API-only page and no longer renders the
Knowledge Base content overview section. The page shows the `MeetMind AI` top
bar, a disabled real-history state, a static React Native robot avatar, the
three RC1 quick questions, structured links to knowledge search, key
decisions, and issue/risk lists, and a fixed bottom input bar above the
existing `BottomNav`. Because the overview section was removed, the home does
not call `GET /knowledge/overview`, `GET /knowledge/meetings?limit=1`, or
`GET /tasks` for card data. Question submission and quick-question execution
do not call a model or generate mock answers; they show that Knowledge Base
Q&A is not open in the current version. The voice button is disabled because
no knowledge voice-input contract exists. The plus button opens the existing
audio import route. No backend, database, Worker, RAG, Prompt, Validator,
six-dimension schema, model call, document upload/index API, or chat-history
storage behavior was changed.

On 2026-07-28 the Expo meeting detail Agent tools tab was rebuilt from
`docs/design/meeting-agent.html` inside the existing `MeetingDetailScreen`.
It reuses the same detail top navigation, inline `expo-av` player, and
three-tab bar as the transcript and AI summary tabs, so tab switching does not
create a second player. The tab now renders four tool cards: email push,
Feishu tasks, mind map, and Knowledge Base. Only Knowledge Base is connected
to a real existing capability: completed meetings with a formal summary can
call `POST /meetings/{id}/knowledge/reindex`, then enter the existing
Knowledge Base route. Email, Feishu, and mind map remain explicitly disabled
because the project has no complete SMTP/Gmail, Feishu Open Platform, or
formal mind-map generation/preview contract. The generation-record section
shows `暂无工具使用记录` because no persisted execution-log endpoint exists for
these four tools. This work did not modify backend services, database schema,
Worker, Prompt, RAG, Validator, six-dimension schema, OAuth, SMTP, Feishu, or
model calls.

On 2026-07-28 the Expo meeting detail AI summary tab was rebuilt from
`docs/design/meeting-minutes.html`. It still lives inside
`MeetingDetailScreen`, reuses the detail top navigation, inline `expo-av`
player, and three-tab bar, and remains in the same single vertical `FlatList`
page structure. The tab now shows a real meeting base card, `summary` export
buttons for MD/PDF/DOCX/TXT through the existing
`/meetings/{id}/exports/summary.{format}` API, basic info from meeting data and
speaker labels, canonical six-dimension fields with legacy alias fallback,
read-only action item status, owner/deadline/priority metadata when available,
and existing evidence/time anchors where the summary payload includes
`source_text`, `evidence`, `timestamp`, `start_time`, `segment_id`, or
`source_segment_id`. It does not add action status writes, Agent tools,
backend endpoints, database migrations, Worker calls, Prompt/RAG/Validator
changes, or schema changes.
Final acceptance tightened this tab so paragraph breaks in `meeting_summary`
are preserved, `timestamp` accepts numeric seconds plus `mm:ss` and `hh:mm:ss`,
evidence jumps wait until the transcript tab is visible before scrolling,
missing segment anchors degrade with a clear inline message, six empty
dimensions show an overall empty state, and empty action objects do not render
blank todo rows. Summary export regression now verifies MD, TXT, PDF, and DOCX
responses through the existing API endpoint.

On 2026-07-28 the Expo meeting detail page was rebuilt for the transcript
stage. `MeetingDetailScreen` now owns its own top navigation for the detail
route, defaults to `会议原文`, and uses one vertical `FlatList` with an inline
`expo-av` player, three-tab bar (`会议原文`, `AI纪要`, `Agent工具`), transcript
quick look, transcript export entry, and real `transcript_segments` timeline.
The player reuses `meetingAudioUrl()` and supports play/pause, draggable
progress, centered 15-second seek controls, timestamp jumps, bounded segment
play, ended-state handling, and loading/missing/failed audio states. Segment
playback can be paused by tapping the active segment icon and stops at the
segment end; the top player no longer exposes a speed control. Final
acceptance tightened audio resource selection so detail playback no longer
uses `audio_files[0]`; both detail playback and the standalone audio player use
a shared playable-audio selector, release stale `expo-av` sounds on
meeting/audio switches, and guard rapid play/pause/seek actions.
Quick look is derived only from real transcript segments; no model calls,
backend endpoints, database schema, Worker, Prompt, RAG, Validator, or
six-dimension schema were changed. AI summary rendering remains on the
existing summary data path, while `Agent工具` is a placeholder for this stage.

On 2026-07-28 the Expo home screen was updated to the MeetMind AI RC1 home
prototype. The current home route still uses `MeetingListScreen mode="home"`
and real `GET /meetings` data. Completed-meeting summaries are fetched only for
home card preview data and degrade to no preview if a summary request fails.
The page is a single full-page `FlatList` with brand/search header, real-time
recording, audio import, `全部会议`, and the existing fixed bottom navigation.
Completed cards prefer canonical `meeting_agenda`, `key_conclusions`, and
`action_items` fields, then fall back to legacy `agenda`, `decisions`, and
`next_steps`. The home section date renders as `M月D日 今天` for the current
day and `M月D日 周X` otherwise; completed-card preview rows are black,
single-line, tail-ellipsized, and card height adapts to the number of available
preview rows.

The real-time recording action still uses the existing create-meeting and
recording flow. The audio import action opens `ImportMeetingScreen`, uses
`expo-document-picker` to select one local audio file, creates a meeting,
and then reuses the existing `AIProcessingScreen` upload/process/analyze flow.
No backend, database, Worker, RAG, Prompt, Validator, or six-dimension schema
behavior was changed. The history list mode, refresh, pagination, delete,
detail navigation, Knowledge Base, Todo, Profile, and existing bottom tab
keys/routes remain intact.

The Enterprise Meeting Knowledge Base MVP is now implemented as an API-side
PostgreSQL read model. Alembic revision `20260724_0016` adds
`meeting_knowledge_items` and `meeting_knowledge_syncs`. The API
`knowledge_sync_service` runs after successful Worker process/analyze responses
and maps completed `MeetingSummary`, persisted `ActionItem`, and
`TranscriptSegment` rows into active knowledge items. Re-analysis updates the
same `meeting_id + content_type + source_item_key`, removed source keys become
`stale`, and meeting deletion marks knowledge rows `deleted` before preserving
the existing hard-delete meeting behavior. Sync failures are recorded in
`meeting_knowledge_syncs.status=failed` and do not block meeting completed
state, summaries, tasks, or meeting detail reads.

Knowledge APIs are registered as `/knowledge/overview`, `/knowledge/meetings`,
`/knowledge/decisions`, `/knowledge/issues`, `/knowledge/risks`, and
`/knowledge/search`, plus `POST /meetings/{meeting_id}/knowledge/reindex` for
manual retry. MVP search is PostgreSQL keyword search over generated knowledge
items and joined meeting titles. Project filtering is intentionally not
exposed because `project_id` is not yet stable on meeting rows. Worker models,
Prompt, RAG rules, Validator, Shadow, and Agent formal write boundaries remain
unchanged.

Expo now has knowledge home, meeting record list, key decision list,
issue/risk tabs, search home, search results, filter sheet, cards, empty/error
states, and skeleton loading. The Knowledge Base home keeps only four entries
and a large search box, with no recent meetings, AI Q&A, or AI assistant entry.
Knowledge result clicks reuse `MeetingDetailScreen` with `initialTab`,
`sourceSegmentId`, `startTime`, and `evidenceText` to open the source meeting
and narrow transcript evidence.

Knowledge Base verification on 2026-07-24 used real completed meeting
`ffe4d629-05ea-4578-ac92-816e69751fb7` with audio
`recording-CAA3FDFB-3B64-4A44-9336-DF621A8A4D9C.m4a`. The meeting had 47
transcript segments, a persisted Summary, and 3 ActionItems. Manual
`/meetings/{id}/knowledge/reindex` completed with `item_count=60`; running it
twice kept the count at 60. `/knowledge/search?query=接口` returned 15 results
with structured results ranked before transcript evidence, and transcript-only
search returned timestamped source segments. `.\scripts\test-all.ps1` and
`.\scripts\check-services.ps1` passed; the services check still reports Redis
port 6379 as WARN, but the script completed successfully.

The project is in Release Candidate verification state after completing the seven-phase maintainability hardening plan.
The default Expo bottom navigation now exposes Knowledge Base instead of AI
Assistant. Knowledge Base calls API-side PostgreSQL knowledge endpoints only;
it does not call RAG, Worker, Ollama, Chroma, or any question-answering API.
Existing AI Assistant, Agent review records, local Agent login, Proposal,
Command, Audit, and Rollback code and database structures remain in place but
are hidden/closed by default. The relevant switches are
`EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=false`,
`EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI=true`, and
`AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=false`. Local Agent login also remains
closed by default through `AGENT_LOCAL_AUTH_ENABLED=false`, including local API
startup defaults.
Expo recent-meeting startup loading has a targeted RC fix: the mobile recent
list no longer treats `audio_uploaded`/`uploaded` as active AI analysis, the
home statistics summary fetch only requests completed meetings, local Expo
configuration points to API port 8002, and API startup recovers stale
`queued`/`running` meeting tasks so service restarts do not leave meetings
permanently in `processing`/`summarizing`.
The Expo AI assistant review UI has been productized on top of Agent v1.0-rc1
review data. The AI tab now shows pending suggestions, approve/reject
confirmation flows, recent records, paginated all-records filters, and record
details. API added read-only `/agent/review/overview`,
`/agent/review/records`, and `/agent/review/records/{record_id}` DTO endpoints
that aggregate existing proposal, confirmation, command, audit, authoritative
object, and meeting data with server-side Bearer-token scope checks. This did
not expand Agent write scope, did not enable grey or real execution by default,
and did not modify Prompt, RAG, Validator, or Shadow.
Meeting detail summary fallback display was fixed after a regression where
legacy `meeting_outputs.summary` content could render with raw
`result_source=unknown` and a failed badge. The summary fallback now receives
display metadata, the mobile detail page shows user-facing source text, and
available summary content is not marked failed solely because the meeting row
has stale `failed` or `summary_failed` status. `npm run test:meeting-detail-ui`
is now part of `scripts/test-all.ps1`.
History meeting loading was also bounded after reports of repeated timeouts.
`GET /meetings` now supports `limit` and `offset` with a default cap, Expo
loads only the first page initially, the full history page supports load-more,
and mobile JSON requests abort with a Chinese timeout message instead of
waiting indefinitely. `npm run test:meeting-history-ui` is part of
`scripts/test-all.ps1`.
Recording upload was hardened after Expo recording uploads failed without a
clear bounded error path. Mobile `uploadAudio` and `uploadAudioChunk` now use
the shared request timeout wrapper, keep Expo `.m4a` uploads as `audio/x-m4a`,
and map upload failures to Chinese user-facing messages. API upload coverage
now verifies `audio/x-m4a` acceptance, `audio_uploaded` persistence, audio file
metadata persistence, and empty-recording rejection without losing the meeting
row. Realtime chunk transcription Worker calls now use the configured finite
Worker request timeout.
End-to-end summary failure recovery was validated against real uploaded audio.
Local API/Worker startup now rejects non-project Python uvicorn owners, Worker
non-2xx errors are persisted as structured task JSON, `summary_failed`
meetings can be re-analyzed from existing transcript/audio, and the mobile AI
processing screen stops on the real failed stage with retry-only analysis.
Agent review auth and real Proposal generation now have a minimal RC path.
Local Agent login is fail-closed by default and enabled only by the local API
startup environment; it creates real `agent_users` and `agent_auth_sessions`
rows with scoped server-side permissions. Expo stores the Bearer session in
AsyncStorage, restores it on AI assistant entry, injects Authorization for
`/agent/*` only, clears expired sessions on 401, and shows distinct
unauthenticated/forbidden/empty/data/error states. Completed meeting analysis
now invokes an API-side Proposal generator after summary and ActionItems are
persisted. The generator only creates pending `AgentActionProposal` rows for
same tenant/project historical `AgentActionItem` matches with transcript-backed
`owner`, `due_date`, `priority`, or `status` changes; it skips new objects,
ambiguous matches, no-change candidates, unsupported fields, insufficient
evidence, and duplicates with diagnostics.
Agent v1.0 upgrade preparation has started at Phase 0 baseline freeze. The
baseline document is `docs/AGENT_V1_PHASE_0_BASELINE.md`.
The Phase 0 runtime diagnostic currently fails because API port 8002 is not
reachable; Worker 8001, PostgreSQL, Ollama, RAG, and Alembic head are OK.
Agent v1.0 Phase 1 adds Worker-internal contract schemas in
`services/worker/app/agent_contract.py` with schema version
`agent-contract-v1`. These contracts are not wired into API responses,
database persistence, Prompt/RAG, Validator, or the formal Qwen3 + RAG analysis
path.
Agent v1.0 Phase 2 adds Worker-internal meeting scenario policies in
`services/worker/app/meeting_scenarios/` with schema version
`meeting-scenario-policy-v1`. The registry covers eight formal meeting types
plus safe `unknown` and remains pure in-memory. It does not classify meetings,
call models, read databases/RAG, execute actions, or modify the formal analysis
path.
Agent v1.0 Phase 3 first-batch Tool Adapters are in
`services/worker/app/agent_tools/`. They wrap existing read/context, RAG,
analysis, action-item read, history-search, and validator capabilities with
structured `ToolResult` output, timeout/call-limit policy, and dependency
injection. They do not implement Tool Registry, Agent Runtime, Orchestrator
integration, ASR/diarization tools, write tools, project state updates, action
execution, or formal-chain integration.
Phase 3 caveats: the outer synchronous Tool timeout returns a structured
`timeout` result but cannot forcibly stop a blocking underlying synchronous
call; `analyze_meeting` still relies on the existing `OLLAMA_TIMEOUT_SECONDS`
for the real model request. `search_meeting_history` is currently deterministic
database search only. `get_project_context` and `get_active_risks` remain
unimplemented until authoritative project and risk state sources exist.
Agent v1.0 Phase 4A adds Worker-internal Tool Registry and controlled Runtime
infrastructure in `services/worker/app/agent_runtime/`. It registers the six
Phase 3 tools, validates read-only ToolPolicy boundaries, executes caller
supplied static `ExecutionPlan` steps, and records in-memory `AgentRunState`
and `AgentStepResult` output. It is not wired into the formal meeting analysis
entry, Shadow Mode, Orchestrator, API, database writes, project-state updates,
or Agent action execution.
Agent v1.0 Phase 4B adds a controlled Worker-internal Orchestrator in
`services/worker/app/agent_orchestrator.py`. When `AGENT_SHADOW_MODE=true`, it
runs after `save_summary()` has persisted the formal result, maps meeting
scenario policy context to a static Runtime plan, writes audit JSON under
`data/debug/agent_shadow_trace/<meeting_id>/`, and records deterministic
formal-vs-shadow comparison data. It never overwrites `MeetingSummary` or
`ActionItem`, never executes Agent actions, and is not exposed through the API
or Expo UI. `AGENT_MODE_ENABLED=true` is recorded but ignored in Phase 4B, so
Agent output is never promoted. With `AGENT_SHADOW_MODE=true`, the static plan
includes `analyze_meeting` and may call the existing model analysis path one
additional time. There is still no real meeting classifier; if no meeting type
is available from metadata, the Orchestrator uses the safe `unknown` minimal
plan.
Agent v1.0 Phase 5 adds offline-by-default Shadow acceptance for
`project_weekly`, `requirement_review`, and `cross_department`. The 9 sanitized
synthetic fixtures are under
`data/eval/agent_v1_baseline/phase5_core_scenarios/`; generated acceptance
reports are under ignored `data/debug/agent_shadow_acceptance/<timestamp>/`.
The local run `phase5-local-acceptance` completed all 9 fixtures with plan hit
rate 1.0, Shadow completion rate 1.0, Tool failure rate 0.0, fallback rate 0.0,
six-dimension field completeness 1.0, average offline Shadow duration 0.15 ms,
and real model call count 0. The 0.15 ms fixture duration is not a real
Qwen3/RAG performance measurement. Phase 5 only
calibrated scenario context policy to enable meeting history for
`requirement_review` and `cross_department`; it did not change Prompt, RAG,
Validator, formal API, database, Expo, Tool core logic, action execution, or
project state persistence.
Agent v1.0 Phase 5B adds the live Shadow acceptance tool
`services/worker/scripts/run_agent_shadow_live_acceptance.py`. It is
offline-by-default and will not call Qwen3 unless `--allow-live-model` is
passed. The tool supports smoke/full modes, `--meeting-id`, `--scenario`,
`--ollama-timeout`, optional `nvidia-smi` GPU monitoring, stop-on-failure
gates, per-meeting layer artifacts, quality score templates, GPU summaries,
and formal-result snapshot hashes under ignored
`data/debug/agent_shadow_live_acceptance/<run_id>/`. Phase 5B implementation
did not run the real model and did not modify Prompt, RAG data/retrieval rules,
Validator, API, database, migrations, Expo, Agent result promotion, or action
execution.
Phase 5B live runs should start Worker with stdout/stderr redirected to
`data/debug/agent_shadow_live_acceptance/worker-phase5b.log` or an equivalent
ignored log file. If Worker keeps port 8001 open but `/health` or `/ready`
timeout after live smoke/full, preserve the Worker log and collect a
process/thread stack snapshot before changing Worker business logic.
Phase 5B full live acceptance was completed locally under
`data/debug/agent_shadow_live_acceptance/20260720-163624` as ignored evidence
only. Results: 9/9 meetings completed, `overall_passed=true`, average quality
score 95.78, minimum quality score 90, cold start about 42.69 seconds, warm
start average about 28.96 seconds, timeout/fallback/error all 0, CUDA OOM 0,
formal-result isolation 9/9 passed, Worker and Ollama healthy after the run,
and meetings 2-9 showed no sustained monotonic GPU memory growth. RAG retrieval
hit the same 8 chunks in all 9 meetings; keep this as a retrieval diversity
observation for later phases. Quality scoring remains rule-assisted and keeps
`manual_review_required=true`.
Agent v1.0 Phase 6 adds the Worker-internal cross-meeting state tracker in
`services/worker/app/agent_state_tracker.py`. It supports only
`Requirement`, `AgentActionItem`, and `Risk`, reads bounded historical
candidates from `AgentContext` or explicit in-memory inputs, normalizes objects,
uses deterministic matching plus similarity-assisted ordering, classifies
`new`, `update`, `complete`, `defer`, `cancel`, `duplicate`, and `uncertain`,
and emits evidence-backed `AgentActionProposal` objects. Phase 6 does not write
formal business tables, add write-path Tools, expose API contracts, modify
database migrations, change Prompt/RAG/Validator, alter Expo UI, promote
Shadow results, or execute Agent actions.
Agent v1.0 Phase 7 adds Worker-internal write-control contracts in
`services/worker/app/agent_write_control.py`. It defines the read-only
`AuthoritativeStateProvider`, `AuthoritativeStateSnapshot`,
`AgentProposalConfirmation`, `ControlledWriteCommand`, `AuditRecord`,
`RollbackPlan`, `InMemoryAuthoritativeStateProvider`, and offline
`ControlledWritePlanner`. The planner re-reads a bounded authoritative object,
checks approved confirmation, expected version, permissions, field whitelist,
idempotency, high-risk confirmation, evidence, and audit context, then produces
an inert command plus audit and rollback information. Phase 7 does not execute
database writes, add write-path Tools, expose API contracts, modify migrations,
change Prompt/RAG/Validator, alter Expo UI, promote Shadow results, implement
automatic approval, or execute Agent actions.
Agent v1.0 Phase 8 adds the minimum API-side confirmation loop. The read-only
production `DatabaseAuthoritativeStateProvider` in
`services/api/app/authoritative_state.py` reads `AgentActionItem` from
`action_items` and reads `Requirement`/`Risk` snapshots from existing
`meeting_summaries` JSON fields. Alembic revision `20260720_0012` adds
`agent_action_proposals`, `agent_proposal_confirmations`,
`controlled_write_commands`, and `agent_audit_records`. The new
`/agent/action-proposals` API supports saving proposals, listing pending
proposals, reading details, approving, and rejecting. Approval re-reads
authoritative state, uses the stored expected object version, checks reviewer
permissions, proposal expiry, field whitelist, evidence, audit context, and
idempotency through `ControlledWritePlanner`, then persists an inert command
and audit record. Phase 8 does not execute Agent actions, does not write formal
Requirement/ActionItem/Risk state, does not connect Expo UI, does not change
Prompt/RAG/Validator, and does not promote Shadow output.
Phase 8 approval/rejection was hardened after read-only acceptance: PostgreSQL
proposal reads now use row locks, stable idempotency keys exclude
confirmation-specific ids, terminal proposal states are immutable, approved
confirmations are created only after planner success, and database
unique-constraint conflicts are recovered as idempotent duplicate results.
Agent v1.0 Phase 9 adds the minimum Expo Agent Review workbench and API
dry-run command sandbox. The AI tab now lists proposal statuses, shows proposal
detail evidence/changes/confidence/risk/version state, uses second confirmation
dialogs for approve/reject, lists ready commands, runs dry-run, and displays
audit records plus rollback previews. API command routes under
`/agent/commands` read persisted commands, run dry-run, and read command
audits. The dry-run executor re-reads authoritative state, checks command
`ready` status, optimistic version, permissions, idempotency key, target
existence, and expected changes, then writes dry-run audit records only.
Runtime flags default to `AGENT_COMMAND_EXECUTION_ENABLED=false` and
`AGENT_COMMAND_DRY_RUN_ONLY=true`. Phase 9 still does not update `action_items`,
summary JSON, Requirement, Risk, Prompt, RAG, Validator, Shadow promotion, or
real rollback state.
Agent v1.0 Phase 10 adds the production-permission safety layer before any
real writes. Agent APIs now use the server-side `AgentPrincipal` adapter in
`services/api/app/agent_security.py` and no longer trust client-provided
`X-Agent-Reviewer` or `X-Agent-Permissions`. Because there is still no
production auth/session/JWT module, the default adapter fails closed with 401;
tests and the PostgreSQL safety script inject principals through dependency
overrides only. The permission model includes `proposal_view`,
`proposal_review`, `command_dry_run`, `command_execute`, `audit_view`, and
`rollback_execute`, with user, project, object, operation, and risk-level
checks. High-risk approval requires elevated role/permission.
Phase 10 also adds rollback dry-run at
`POST /agent/commands/{command_id}/rollback/dry-run`, requiring a persisted
command id and original dry-run audit before generating a rollback command
preview and audit with `writes_performed=false`. The future real-write executor
contract is documented as a rejecting stub; it specifies authoritative re-read,
expected-version optimistic lock, ready-state validation, idempotency recovery,
single-transaction write plus audit, failure rollback, and success state
transition for a later phase. Runtime flags are
`AGENT_COMMAND_EXECUTION_ENABLED=false`, `AGENT_COMMAND_DRY_RUN_ONLY=true`, and
`AGENT_ROLLBACK_EXECUTION_ENABLED=false`. Phase 10 still does not update
`action_items`, summary JSON, Requirement, Risk, Prompt, RAG, Validator,
Shadow output, or production business state.
Agent v1.0 Phase 11 adds production identity and first-class authoritative
state foundations while keeping real writes disabled. API Agent auth now uses
`Authorization: Bearer <token>` only: the token is hashed, matched against
`agent_auth_sessions`, checked for expiry/revocation, joined to active
`agent_users`, and converted into `AgentPrincipal` with `user_id`, `tenant_id`,
`roles`, `permissions`, `project_scope`, `object_scope`, and
`authentication_source`. Missing, invalid, expired, revoked, or inactive
sessions return 401; permission/scope denials return 403. Tests may still use
dependency overrides.
Phase 11 Alembic revision `20260721_0013` adds `requirements`, `risks`,
`agent_users`, `agent_auth_sessions`, and tenant/project columns on
`action_items`. Migration copies Requirement/Risk candidates from existing
summary JSON into first-class tables, puts incomplete candidates into `review`,
keeps source meeting/summary/field/index plus raw references, preserves the
original summary JSON, and supports downgrade. `DatabaseAuthoritativeStateProvider`
now reads `Requirement` from `requirements`, `AgentActionItem` from
`action_items`, and `Risk` from `risks`; it no longer scans summary JSON as the
formal authoritative source. Provider reads validate server-side principal
tenant, project, object type, object id, and operation permission. Phase 11
still does not update `requirements`, `risks`, `action_items`, summary JSON,
Prompt, RAG, Validator, Shadow output, or production business state.

Agent v1.0 Phase 12 adds real-write preparation and historical action-item
scope backfill support while keeping real writes disabled. Alembic revision
`20260721_0014` adds `action_item_scope_backfill_audits`; the backfill service
only applies tenant/project to default-scoped historical `action_items` when
the same summary or meeting has exactly one non-default first-class
Requirement/Risk tenant/project pair. Existing valid scopes are preserved.
Unverifiable or conflicting data is recorded as `review` with source references
and no scope change. The backfill utility is explicit operator-run tooling and
does not automatically act on production data.

Phase 12 also adds transaction rehearsal for the future command executor. The
rehearsal locks the `controlled_write_commands` row, checks `ready`, re-reads
the authoritative provider, validates permission and `expected_version`, and
writes an Agent audit record in one transaction. It intentionally skips
business mutation and records `business_writes_performed=false`; it does not
update `requirements`, `risks`, `action_items`, or summary JSON. The real write
executor and real rollback executor remain unsupported. Phase 12 is sufficient
only for Phase 13 pilot preparation, not for directly enabling production real
writes.

Agent v1.0 Phase 13 adds a restricted real-write pilot for internal test
tenant/project scopes only. Alembic revision `20260721_0015` adds
`action_items.version`, which is now the authoritative `AgentActionItem`
version. Default switches remain closed:
`AGENT_COMMAND_EXECUTION_ENABLED=false`,
`AGENT_COMMAND_DRY_RUN_ONLY=true`,
`AGENT_COMMAND_PILOT_ENABLED=false`,
`AGENT_COMMAND_PILOT_TENANTS=`,
`AGENT_COMMAND_PILOT_PROJECTS=`, and
`AGENT_ROLLBACK_EXECUTION_ENABLED=false`. The pilot executor can write only
`AgentActionItem` `update` / `complete` commands in whitelisted internal
projects, only low/medium risk, and only `owner`, `due_date`, `priority`, and
`status`. It locks command and action item rows, revalidates server-side
principal permission/scope, checks `expected_version`, updates the action item,
increments `version`, writes execution audit, and marks the command
`succeeded` in one PostgreSQL transaction. Pilot rollback is limited to Phase
13 succeeded commands, requires rollback permission and confirmation comment,
checks the execution-audit version, restores recorded before values, writes
rollback audit, and marks the command `rolled_back` in one transaction.
Requirement/Risk writes, cancel, high/critical commands, non-whitelisted
projects, automatic approval, batch execution, Prompt/RAG/Validator changes,
Shadow promotion, and production-wide release remain disabled.

Agent v1.0 Phase 14 adds production safety guardrails and grey acceptance
without expanding the Phase 13 write contract. The API now has
`agent_phase14_guardrails.py` and `/agent/ops` endpoints for metrics, redacted
audit search, circuit status/reset, and release preflight. Real execution must
pass Phase 13 pilot switches plus explicit Phase 14 grey settings:
tenant/project/user whitelist, non-zero grey percentage, non-zero per-project
and per-user daily limit, non-zero concurrency limit, optional UTC time window,
no manual pause, no tenant/project pause, no global kill switch, and no open
audit-backed circuit. Defaults remain closed. Emergency close rejects new
command execution but still allows audit queries and controlled rollback of
already successful Phase 13 pilot commands. Phase 14 uses existing tables and
does not add an Alembic revision; Alembic head remains `20260721_0015`.
Requirement/Risk writes, summary JSON writes, cancel, high/critical commands,
batch execution, automatic approval, Prompt/RAG/Validator changes, Shadow
promotion, default grey enablement, production-wide release, and Phase 15 work
remain out of scope.

Agent v1.0 Phase 15 completes final acceptance and release decision. The final
decision is `GO` for internal controlled grey only, under the existing Phase
13/14 scope and guardrails. Phase 15 added final acceptance tooling
`services/api/scripts/run_agent_phase15_final_acceptance.py` and archive docs:
`docs/AGENT_PHASE15_FINAL_ACCEPTANCE_REPORT.md`,
`docs/AGENT_PHASE15_RELEASE_DECISION.md`,
`docs/AGENT_PHASE15_RISKS_AND_OPEN_ITEMS.md`,
`docs/AGENT_PHASE15_GREY_CHECKLIST.md`, and
`docs/AGENT_PHASE15_ROLLBACK_EMERGENCY_RUNBOOK.md`. Validation passed
`test-all.ps1`, Phase 11-14 PostgreSQL acceptance, Phase 5B full live Qwen3 +
RAG Shadow acceptance, `meeting_001` real production analysis, and Phase 15
API/DB final acceptance. Phase 15 did not enable default grey, change
production config, expand write scope, or approve production-wide writes.

Repository freeze metadata:

- Repository: `https://github.com/zsjgg90/AI-Meeting-Agent`
- Baseline branch: `main`
- Baseline commit: `85dca9cb6e2944bfed2926d0a26b5f40d64ffc10`
- Baseline tag: `agent-v1-phase0-baseline`
- Agent development branch: `feature/agent-v1`
- Freeze date: `2026-07-20`

Completed phases:

1. Project audit
2. Project memory and documentation entry
3. Unified configuration management
4. Unified schema and module boundaries
5. Prompt and RAG version management
6. Testing, logging, and observability
7. RC final validation

## Active Paths

- Mobile: `apps/mobile`
- API: `services/api`
- Worker: `services/worker`
- RAG source: `data/rag`
- Chroma DB: `data/vector_db`
- Docs: `docs`

Legacy paths remain but should not be modified for active work:

- `api`
- `mobile`

## Formal Analysis Chain

```text
Expo -> API -> Worker -> RAG Retrieval -> Qwen3 14B -> Validator -> MeetingAnalysisSchema -> PostgreSQL -> API -> Expo
```

Formal model:

```text
qwen3:14b
```

Formal schema:

```text
meeting-analysis-v1
```

Formal prompt:

```text
meeting-analyst-v1
```

## Commands To Reproduce RC Checks

```powershell
.\scripts\test-all.ps1
.\scripts\check-services.ps1
```

## Important RC Finding

The local API startup script was updated so Docker-style `WORKER_URL=http://worker:8001` is converted for Windows local development. This fixes API readiness when the root `.env` contains Docker hostnames.

Modified files from RC:

- `scripts/local-env.ps1`
- `services/api/start-api-local.ps1`

## 2026-07-20 Production Analysis Repair

Meeting `73c47be6-0ea0-41eb-ac73-81e458574abd` (`周会5`) failed because an
earlier timed-out summary run left `transcript_segments` speaker-name updates
locked. Later Worker `/analyze` calls waited on those locks and never reached
RAG or Qwen. The stale Postgres backends were terminated and Worker analysis was
rerun successfully, generating summary
`33db99a1-634d-4d57-b28b-f720c4d9bcde` in about 40.35 seconds.

Code changes:

- `services/worker/app/summary_agent.py` now commits speaker-name backfill
  before long RAG/Qwen analysis.
- `services/worker/app/rag_retriever.py` now loads the embedding model with
  `local_files_only=True` by default through Worker settings.

Runtime note: this desktop session has API listening on port 8000 while
`scripts/check-services.ps1` checks the historical 8002 port. Worker 8001 is
healthy after restart.

## Next Recommended Work

Do not continue broad refactoring immediately. First stabilize:

1. Archive Phase 15 final acceptance with an explicit tag after review; the
   suggested tag is `agent-v1-phase15-final-acceptance`.
2. Decide how `agent_users` and `agent_auth_sessions` should integrate with the
   broader product identity/session system before exposing Agent APIs broadly.
3. Keep the remaining Agent risks visible: proposal list/detail evidence and
   metadata exposure, production-scale historical tenant/project backfill
   rollout, duplicated API/Worker Agent contracts, FK `ondelete` policy, and
   the pilot-only rollback executor not being production-wide rollback.
4. Review first-class Requirement/Risk lifecycle semantics before any command
   executor can mutate those tables.
5. Keep Agent action execution disabled outside explicit Phase 13 pilot
   whitelists until production authorization integration, command persistence
   semantics, rollback transactions, and failure drills are approved.
6. Import the remaining required Agent baseline meeting artifact folders under
   `data/eval/agent_v1_baseline/` when available.
7. Run `.\scripts\check-services.ps1` with local services available.
8. Continue embedding model offline/cache setup, shared API/Worker model
   strategy, live benchmark gate, and E2E demo script.

## 2026-07-28 Todo Mobile Runtime Note

The Todo home no longer has inline search state; its search button should only
open the independent task-search route. The task-search page should not call
`GET /tasks?q=...` from `onChangeText`; search requests are submitted only by
the IME keyboard search action, retry, load-more, or recent-search selection.
Todo completion uses a 300 ms visual transition: after tapping the checkbox or
title, the item first shows a checked square checkbox and grey strikethrough
title, then clears the transition after the real API succeeds without
automatically switching the top filter to completed.

If mobile checkbox completion returns 404 after code changes, first verify the
running API route table. In this session the local 8002 listener was still
serving the old OpenAPI with only `/tasks`; restarting
`services/api/start-api-local.ps1` restored `/tasks/{task_id}/status`.

## 2026-07-28 Task Detail Runtime Note

Todo and task-search task cards now open `TaskDetailScreen` as a full-screen
overlay instead of navigating directly to meeting detail. The overlay keeps the
underlying Todo or search screen mounted so filters, search text, results, and
scroll state are preserved after back. The detail page has no bottom
navigation, reads the task object supplied by the entry card, and attempts a
best-effort refresh through `GET /tasks` with `meeting_id` and the task title
before matching by id. There is still no dedicated `GET /tasks/{id}` endpoint.

Task detail status now uses the formal `PATCH /tasks/{task_id}/status`
endpoint from a square checkbox. Inline title, description, owner, deadline,
priority, and reminder controls persist through `PATCH /tasks/{task_id}`.
Task attachments persist through `POST /tasks/{task_id}/attachments` and open
through `GET /tasks/{task_id}/attachments/{attachment_id}`. Title/status/edit
changes are reflected in the current App-session Todo/search data through
`taskOverrides`. Missing task description, owner, deadline, priority,
evidence, source meeting, and attachments degrade to explicit empty copy and
do not use prototype static data. Source meeting is displayed as read-only in
task detail and no longer navigates to meeting detail from that row.

## 2026-07-30 Home Meeting List Date Sections

The mobile home and all-meetings lists now use `SectionList` sections generated
from `apps/mobile/src/utils/meetingDateSections.ts`. Meetings group and sort by
`start_at`, falling back to `created_at`; local date fields determine natural
days and 今天/昨天 labels. Invalid or missing dates are isolated under
`时间未知`. A midnight timer refreshes section labels after local 00:00, and the
mini recording bar path adds extra bottom padding so the final section/card can
scroll above the overlay.

Verification run: `npm run test:meeting-date-sections`, `node
apps/mobile/scripts/test-meeting-history-ui.js`, `npm run typecheck`, and
`.\scripts\test-all.ps1` all passed on 2026-07-30.

## 2026-07-30 Bottom Navigation Position

`apps/mobile/src/components/BottomNav.tsx` now pins the tab bar with
`position: 'absolute'`, `bottom: 0`, `left: 0`, and `right: 0`, and removes the
previous `paddingBottom: 12` visual gap. `apps/mobile/scripts/test-bottom-nav-ui.js`
checks this layout and is included in `.\scripts\test-all.ps1`.

Verification run: `npm run test:bottom-nav-ui`, `npm run typecheck`, and
`.\scripts\test-all.ps1` all passed on 2026-07-30.

Follow-up adjustment: the pinned bottom tab bar was raised from `minHeight: 66`
to `minHeight: 80`, each tab item from `minHeight: 54` to `minHeight: 66`, and
the icon wrapper now uses `transform: [{ translateY: -5 }]` so icons sit higher
inside the taller bar. The same checks passed again.

Second follow-up adjustment: the tab bar was raised again by about 15% from
## 2026-08-01 RAG v2.1.1 Acceptance Owner/Deadline Fix

Fixed the RAG v2.1.1 acceptance failure where semantic pipeline action items
kept speaker-derived `owner_name` values that were not present in the action
`source_text`. The cleanup rule now keeps action owner/deadline metadata only
when supported by `source_text`, `evidence_text`, or semantic event attributes,
and semantic pipeline export clears unsupported owners before writing the final
meeting analysis payload. The acceptance script now reports
`acceptance_passed=true` when all automatic gates pass, while still noting that
manual semantic review is required.

Changed files:

- `services/worker/app/anti_hallucination_validator.py`
- `services/worker/app/meeting_analysis_pipeline.py`
- `services/worker/scripts/run_meeting_pipeline_acceptance.py`
- `services/worker/tests/test_anti_hallucination_validator.py`
- `services/worker/tests/test_meeting_analysis_pipeline_output.py`
- `docs/CHANGELOG.md`
- `docs/CURRENT_TASKS.md`
- `docs/conversations/2026-08-01-rag-v2-1-1-owner-deadline-acceptance.md`

Verification:

- `python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_postprocessor services.worker.tests.test_meeting_analysis_pipeline_output`
- `python .\services\worker\scripts\run_meeting_pipeline_acceptance.py`
- `.\scripts\test-all.ps1`

Latest acceptance artifacts:

- `data/debug/meeting_pipeline_acceptance/20260801_173351/`
- `owner_deadline_hallucination_count=0`
- `auto_gates_passed=true`
- `acceptance_passed=true`

`minHeight: 80` to `minHeight: 92`, tab items from `minHeight: 66` to
`minHeight: 76`, and the transform moved from icon-only to the whole tab item
with `transform: [{ translateY: -6 }]` so icons and labels move upward
together. The same checks passed again.

Third follow-up adjustment: the tab bar was raised again by about 15% from
`minHeight: 92` to `minHeight: 106`, tab items from `minHeight: 76` to
`minHeight: 87`, and the whole tab item offset increased to
`transform: [{ translateY: -10 }]`. The same checks passed again.

Fourth follow-up adjustment: the tab bar was reduced by about 5% from
`minHeight: 106` to `minHeight: 101`, tab items from `minHeight: 87` to
`minHeight: 83`, and the whole tab item offset was softened to
`transform: [{ translateY: -8 }]`. The same checks passed again.

## 2026-07-30 Realtime Recording Mini Bar Overlay

The collapsed realtime recording bar in
`apps/mobile/src/screens/RecordingScreen.tsx` now renders as a bottom overlay
instead of a smaller floating pill above BottomNav. Its `miniBar` style uses
`bottom: 0`, `left: 0`, `right: 0`, `minHeight: 140`, `zIndex: 95`, and
`elevation: 24`, so it spans the screen width and visually covers the pinned
bottom tab navigation while recording is collapsed. The nested `miniPanel`
owns the top radius and content padding.

Follow-up adjustment: the collapsed bar now has a centered horizontal handle
at the top. `miniPanResponder.panHandlers` is attached to the whole `miniBar`,
so the entire collapsed bottom recording module can be dragged upward to call
the existing `onExpand` callback and restore the expanded recorder in the same
mounted `RecordingScreen`; no route transition is involved. The handle is only
a visual cue. The collapsed content is split into a centered `miniContentRow`,
so the waveform/timer block aligns vertically with the play/pause and stop
controls. The elapsed timer also has a JS wall-clock interval fallback while
`state === 'recording'`, so it keeps advancing even if Expo's native recording
status callback does not fire reliably in collapsed mode.

Second follow-up adjustment: the collapsed bar drag gesture now waits for
intentional vertical movement before taking responder ownership, applies
resisted upward/downward movement, and uses a spring with `tension: 170` and
`friction: 20` to return naturally when the drag does not expand. The module
also gets a subtle `miniScale` response while dragging. The collapsed
waveform, timer, play/pause, and stop controls were enlarged by about 25%:
compact waveform is `56 x 22`, timer font is `19`, and action controls use
`scale: 0.95` instead of the previous smaller `0.76`.

Third follow-up adjustment: dragging no longer moves the fixed bottom cover
itself. `miniBar` remains fixed at `bottom: 0` with a white background and
`minHeight: 164` to keep the pinned BottomNav hidden, while a nested
`miniPanel` receives the `miniDragY` and `miniScale` transform. This prevents
the bottom tab navigation from appearing during upward drag. The collapsed
controls were enlarged by another 25%: compact waveform is now `70 x 28`,
compact waveform bars use `Math.max(10, baseHeight * 0.72)`, timer font is
`24`, and action controls use `scale: 1.19`.

Fourth follow-up adjustment: after reviewing the visual weight, the collapsed
bar and controls were reduced by about 15% while keeping the fixed-cover
structure. Current compact values are: `miniBar`/`miniPanel` `minHeight: 140`,
compact waveform `60 x 24`, compact waveform bars
`Math.max(9, baseHeight * 0.61)`, timer font `20`, and action controls
`scale: 1.01`.

Verification run: `node apps/mobile/scripts/test-recording-upload-ui.js`,
`npm run typecheck`, and `.\scripts\test-all.ps1` passed on 2026-07-30.

## 2026-07-30 Profile And Center Recording Entry

`apps/mobile/src/screens/ProfileScreen.tsx` now matches the supplied `我的`
prototype with a centered title, top settings button, retained user card, and
the menu entries `我的记忆`, `声纹管理`, `推送配置`, `帮助与反馈`, and
`关于 MeetMind AI`. Only existing settings, help/feedback, and about routes are
wired. Memory, voiceprint, and push configuration show an unsupported-version
prompt instead of fake data.

`apps/mobile/src/components/BottomNav.tsx` now uses the fixed five-item layout
`首页 | 知识库 | 麦克风 | 待办 | 我的`. The center microphone is a raised blue
button. In `apps/mobile/App.tsx`, clicking it reuses the existing realtime
recording entry: if a recording session exists, it expands the mounted
`RecordingScreen`; otherwise it calls the existing `createRecordingMeeting()`.
No new `RecordingScreen`, recording object, recorder state store, backend,
Worker, Prompt, RAG, Validator, schema, or database change was introduced.
