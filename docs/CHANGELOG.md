# Changelog

## 2026-08-01

- Completed Stage7 Golden Regression optimization for
  `project_delivery_001`. The Worker anti-hallucination validator now removes
  unresolved or conditional follow-up statements from `key_conclusions`,
  filters suggestion/direction-only items from `action_items`, removes risks
  without explicit risk evidence in `source_text`, and keeps unresolved items
  reserved for truly undecided matters. The refreshed Stage7 report shows
  `decision_precision=1.0`, `risk_recall=1.0`, `hallucination_rate=0.0`, and
  `evidence_coverage=1.0`; `task_recall` remains `0.0` because the expected
  task owner/deadline/task text is not supported by the transcript evidence.

- Fixed the RAG v2.1.1 meeting pipeline acceptance owner/deadline hallucination
  gate. Worker action metadata cleanup now preserves `owner`/`owner_name` and
  `deadline`/`due_date` only when supported by action `source_text`,
  `evidence_text`, or semantic event attributes, and clears unsupported
  metadata before persistence/export. Semantic pipeline action export now also
  drops speaker-derived `owner_name` values when the current action
  `source_text` does not contain that owner evidence. The acceptance report now
  sets `acceptance_passed=true` when all automatic gates pass while retaining
  the manual semantic review note.

## 2026-07-31

- Added Phase 0 Evaluation System infrastructure under `data/eval/`, including
  evaluation schema, metric definitions, report location, and an RC1 baseline
  report placeholder. Added `scripts/evaluate_meeting_analysis.py` to compare
  existing `expected.json` and `actual.json` files and compute Decision
  Precision, Task Recall, Risk Recall, Hallucination Rate, and Evidence
  Coverage. Added mock-data unit tests in `tests.test_evaluate_meeting_analysis`.
  This is offline-only and does not modify ASR, Semantic Pipeline, RAG, Prompt,
  Qwen3 calls, API, database migrations, or Mobile.

## 2026-07-30

- Adjusted the mobile `历史会议` page header and spacing. The loaded meeting
  count now appears in the top title as `历史会议（n）`; the separate `共 n 场会议`
  subtitle was removed, the `选择`/batch selection text is black, and the
  history list/date section starts closer to the header. No API, backend,
  database, Worker, Prompt, RAG, Validator, schema, or meeting-analysis flow
  changes were made. The Agent auth API test fixture was also made time-stable
  by using a relative future expiry for valid bearer-token tests.

- Implemented the mobile `推送配置` page from the provided prototype as a
  React Native Profile subpage. The page presents Feishu push, email push, and
  SMS reminder cards with disabled/off switches, channel rows, and truthful
  `未配置`, `暂未开放`, and `待接入` states. The Profile entry now opens this page
  and BottomNav remains on `我的`. No OAuth, SMTP, SMS provider, backend API,
  database field, push history, Worker, Prompt, RAG, Validator, schema, or
  meeting-analysis flow changes were added.

- Implemented mobile `声纹管理` and `添加声纹样本` pages from the provided
  prototypes using React Native. The Profile entry now opens the voiceprint
  management page, which shows a disabled `未开放` recognition switch, the
  required explanatory copy, a truthful empty-state list, and add-sample
  entry points. The add-sample page collects a user name and records a local
  voice sample through a separate page-local `expo-av` `Audio.Recording`
  instance. Because no formal voiceprint API exists, save reports
  `待接入接口` and does not upload, register, identify speakers, add fake users,
  or touch backend, Worker, Prompt, RAG, Validator, schema, or database code.
- Updated the mobile `我的` help/feedback and about flows to use the new
  MeetMind blue visual style across the profile entry rows, shared subpage
  headers, help landing page, FAQ page, feedback form, and about page. The
  about page now displays `当前版本 V1.0.0`. The help/about subpage headers,
  profile entry icons, help entry icons, FAQ number badges, and about logo
  waveform were then adjusted back to black while preserving blue action and
  brand accents. The help landing page entry cards then removed their left
  icons, leaving only title, subtitle, and the right chevron.
- Stabilized the collapsed realtime recording bar timer. The mini timer and
  expanded recording timer now use tabular numbers with fixed widths, elapsed
  seconds are driven by a single JS accumulated clock so native duration/status
  updates cannot make the timer move backward, and the collapsed bar keeps
  waveform plus timer on one row beside the action buttons. Pause/resume now
  updates the player icon immediately while blocking duplicate taps during the
  native audio operation. The collapsed recording bar height was then reduced
  by about 15% while preserving the current control button hit targets.
- Fixed the meeting detail top player pause behavior while first-play audio is
  still loading. A second tap during the in-flight load now cancels the pending
  play intent instead of being ignored and allowing playback to start after the
  load completes. The home `全部会议` section spacing was also slightly relaxed
  from the previous compact values.
- Refined mobile meeting list and detail playback polish: transcript segment
  play controls now use a compact icon-sized button aligned with the timestamp,
  completed meeting cards hide the bottom-right todo badge when there are no
  action items instead of rendering `无待办`, the home `全部会议` date header
  spacing was tightened so cards sit closer to the section title, and the
  detail top player no longer renders a loading spinner inside the main play
  button while first-play audio loading is in progress.
- Optimized the meeting detail top player first-play interaction. The detail
  page now preloads the selected audio file with the existing `Audio.Sound`
  lifecycle, reuses the in-flight loading promise when the user taps play, and
  switches the play button to the pause icon immediately on play intent instead
  of waiting for the native playback status callback. No audio API, backend,
  Worker, Prompt, RAG, Validator, schema, or database behavior changed.
- Removed the inline audio failure hint from the meeting detail top player.
  Tapping play on meetings with missing or unavailable audio no longer renders
  `音频加载失败，请确认录音文件仍然存在。`; playback state still degrades without
  changing the audio loading API or backend behavior.
- Removed the extra home `全部会议` date subtitle so the home list no longer
  shows both `7月30日 今天` and the date-section header for the same day. The
  existing date section header remains the single meeting-date label.
- Added a controlled live Qwen3 title audit over 24 real/existing acceptance
  transcripts, covering project weekly, requirement review, solution review,
  risk review, retrospective, short recordings, multi-topic meetings, and poor
  ASR samples. The report is written to
  `data/debug/title_regression/20260730_title_live_phase2/` plus latest report
  aliases. The audit found no local action-item title leaks and one safe
  fallback from the time-plus-action validator. A narrow validator fix now
  allows dots only inside version-number tokens such as `V3.2` while continuing
  to reject ordinary dotted/explanatory titles.
- Rebuilt the Expo `我的` page from the supplied profile prototype using React
  Native components. The page keeps the title, user card, settings entry, and
  menu items for `我的记忆`, `声纹管理`, `推送配置`, `帮助与反馈`, and
  `关于 MeetMind AI`; unsupported memory, voiceprint, and push entries show a
  current-version unavailable prompt instead of fake data.
- Changed the mobile bottom navigation to
  `首页 | 知识库 | 麦克风 | 待办 | 我的` and added a raised blue center microphone
  button. The microphone tab calls the existing `App.tsx` realtime recording
  entry: it creates the fallback-titled meeting when no recording session
  exists, or expands the current recording overlay when one already exists.
  No new recording screen, recorder state, backend endpoint, Worker, Prompt,
  RAG, Validator, schema, or database behavior was added.
- Reduced the collapsed realtime recording bar height and compact recording
  controls by about 15% after the previous enlargement, while keeping the fixed
  bottom cover structure that prevents the tab bar from showing during drag.
- Updated the collapsed realtime recording bar so dragging upward no longer
  reveals the bottom tab navigation: a fixed bottom white layer keeps covering
  the tabs while only the inner recording panel moves. The compact waveform,
  timer, play/pause, and stop controls were enlarged by another 25%.
- Smoothed the collapsed realtime recording bar drag gesture. It now waits for
  intentional vertical movement before taking over touch handling, applies
  resisted upward/downward movement, adds a subtle scale response while
  dragging, and enlarges the collapsed waveform, timer, play/pause, and stop
  controls by about 25%.
- Added an offline AI meeting title regression audit over existing real/debug
  transcript samples for project weekly, requirement review, risk review, and
  retrospective meetings. The audit writes
  `data/debug/title_regression/20260730_title_regression_report.md/.json` and
  does not call Qwen3, access the database, or refactor the six-dimension
  analysis path. It found one clear deterministic gap for role-specific task
  titles without time words, so the title validator now rejects narrow
  role-plus-action candidates such as `后端接口优化确认会` while preserving valid
  whole-meeting titles.
- Refined the collapsed realtime recording bar drag interaction: the visual
  affordance is now a horizontal handle, and the whole bottom recording module
  can be dragged upward to restore the expanded recorder.
- Added a draggable expand handle to the collapsed realtime recording bar.
  Dragging upward restores the expanded recorder in the same mounted
  `RecordingScreen`, the collapsed waveform/timer row is vertically aligned
  with the play/pause control, and elapsed time now has a JS timer fallback
  instead of relying only on native `expo-av` status callbacks.
- Tightened AI meeting title generation in the formal Qwen3 + RAG path without
  adding a second model request. The prompt now asks for internal
  `meeting_type`, `meeting_type_confidence`, `meeting_title_candidate`, and
  `title_basis` fields, and Worker title replacement now requires a fixed
  meeting-type enum, confidence at least `0.70`, at least two valid title
  bases, and deterministic rejection of generic, explanatory, JSON/Markdown,
  multiline, over/under-length, and time-plus-action task titles. Failed title
  validation keeps the fallback `YYYY-MM-DD HH:mm 实时录音/文件导入` title and
  does not affect six-dimension summary persistence.
- Changed the collapsed realtime recording mini bar to a full-width bottom
  overlay that starts at the screen bottom, has enough height to cover the
  bottom tab navigation, and uses a higher native layer than the tab bar.
- Reduced the mobile bottom tab navigation height by 5% to `minHeight: 101`
  and adjusted the shared icon/label upward offset to `translateY: -8`.
- Increased the mobile bottom tab navigation height by another 15% to
  `minHeight: 106` and moved both icon and label content further upward.
- Increased the mobile bottom tab navigation height by another 15% and moved
  both icon and label content upward together inside each tab item.
- Increased the pinned mobile bottom tab navigation height by about 20% and
  shifted tab icons upward inside the taller bar.
- Pinned the mobile bottom tab navigation to the bottom edge of the app screen
  by making `BottomNav` absolute and removing its old bottom padding gap.
- Changed the mobile home/all-meetings list to render natural-day sections with
  `SectionList`. Meetings now group by `start_at` with `created_at` fallback,
  use local time for day keys and 今天/昨天 labels, sort date groups and cards
  newest-first, degrade invalid dates into `时间未知`, and reserve extra bottom
  padding when the mini recording bar is visible.
- Fixed the mobile home/history compact meeting card agenda preview by reading
  the structured summary item's canonical `item` field. API summary loading was
  unchanged; `meeting_agenda` values like `{ item: "..." }` now appear in the
  list instead of being treated as empty.
- Updated the mobile home/history compact meeting card so the four AI preview
  dimensions (`会议总结`, `会议议程`, `核心结论`, and `待办事项`) render only when the
  analysis returned valid text. Missing dimensions are omitted instead of
  showing `暂无`, allowing card height to shrink with the available content.

## 2026-07-29

- Updated the mobile home/history compact meeting card so completed meetings
  support four AI preview rows: `会议总结`, `会议议程`, `核心结论`, and
  `待办事项`. Data sources are unchanged.
- Fixed the mobile history meeting swipe-delete background overflow after the
  history list adopted the home compact card. Swipe rows now own vertical
  spacing and compact cards remove their bottom margin inside swipe containers,
  so the red delete layer no longer protrudes beyond the card.
- Added `会议总结` to the mobile meeting-card AI preview block alongside
  `会议议程`, `核心结论`, and `待办任务`. The history/all-meetings page now uses the
  same compact meeting card preview as the home list while retaining selection,
  pagination, refresh, and swipe-delete behavior.
- Fixed realtime recording save reliability by reading the Expo recording URI
  before `stopAndUnloadAsync()` and no longer discarding a valid URI only
  because the local elapsed timer has not reached one second. The home compact
  meeting list also no longer shows the `未生成摘要` status badge for unrecorded
  `pending` meetings.
- Refactored realtime recording from a standalone full-screen route into a
  home-screen expandable recording overlay with a BottomNav-adjacent mini bar.
  Expanded and collapsed views share the same mounted `expo-av` recording
  instance, elapsed timer, pause state, meeting id, metering-backed waveform,
  and stop/discard actions. Dragging the top handle collapses the sheet without
  releasing recorder resources; tapping the mini bar expands it again. The
  recording sheet was simplified by removing the language selector, right-side
  close button, central microphone prompt, transcript placeholder copy, and
  one-hour limit banner. The player now keeps only 10-bar soundprint, smaller
  timer, pause/resume, and direct end controls. End no longer opens a second
  confirmation: it stops immediately, shows `已进入AI结构化分析` for 500 ms, returns
  home, injects the just-ended meeting into the home/all meeting lists as
  `processing` so the existing `处理中` loading badge appears immediately, and
  runs upload/process/analyze in the mobile background flow. No
  streaming ASR, WebSocket, backend endpoint, Prompt/RAG, Validator, schema,
  file import, detail, knowledge, or todo behavior was added or changed for
  this refactor.
- Optimized meeting creation and title generation. Realtime recording now
  creates a meeting directly from the home action with a local
  `YYYY-MM-DD HH:mm 实时录音` fallback title and enters `RecordingScreen`
  without opening `NewMeetingScreen`; audio import now uses
  `YYYY-MM-DD HH:mm 文件导入`. Meetings track `title_source`
  (`fallback`, `ai_generated`, `user_edited`) through Alembic revision
  `20260729_0018`. The formal Worker analysis schema now accepts a
  `meeting_title` candidate from the same Qwen3 + RAG call, validates it, and
  replaces only unchanged fallback titles after successful analysis. Manual
  title edits through meeting detail are marked `user_edited` and are not
  overwritten by re-analysis, export, refresh, or knowledge reindex.
- Rebuilt `RecordingScreen` from `docs/design/meetmind-app_meeting-recording.html`
  while staying on React Native / Expo. The page now starts real `expo-av`
  recording automatically after meeting creation, shows title/create time,
  recording or paused state, a truthful no-realtime-transcript prompt, timer,
  metering-backed waveform with animation fallback, real pause/resume, direct
  end without a second confirmation, discard confirmation, rapid-action guards,
  and cleanup for abandoned or too-short automatic recordings. Realtime
  recording now returns to the home list immediately after stop and starts
  upload/process/analyze in the mobile background flow; file import still
  reuses `AIProcessingScreen`. It does not add streaming ASR, WebSocket mobile
  capture, backend contracts, Prompt/RAG, Validator, or schema changes. The AI
  processing page now renders the latest polled meeting title so successful AI
  title replacement is visible before opening details.
- Refined the realtime recording finish feedback. After tapping end, the mobile
  app now shows a strong `已进入AI结构化分析` notice for 500 ms, then returns to
  the home list while background upload/transcription/analysis continues. Home
  and history meeting cards now show a small loading indicator to the left of
  processing status badges.
- Adjusted home meeting cards so the lower-right todo badge is hidden while a
  meeting is still processing and appears only after AI generation completes.
- Added real task-detail persistence for the mobile detail page. The API now
  exposes `PATCH /tasks/{task_id}` for title, description, owner, due date,
  priority, reminder offset, and reminder channel; task attachments are stored
  on the server through `POST /tasks/{task_id}/attachments` and opened through
  the attachment download endpoint. The Todo and task-search deadline display
  now uses the compact `7-15 14:00` style for parseable date-times.
- Restyled the Expo task detail page to match the provided compact mobile
  reference: the editable title and editable description now live in a top
  `当前任务` card, with the same square completion checkbox placed to the left
  of the task title. The previous linear detail-card layout was replaced with
  grouped sections for `基本信息`, reminder settings, and attachments. The
  former `基本配置` label is intentionally not used.
- Updated the Expo task detail page for the latest mobile task-detail
  interaction requirements. The detail status control is now a square checkbox
  backed by the existing `PATCH /tasks/{task_id}/status` API with optimistic UI
  and rollback. The right header edit icon was removed. Title editing updates
  the current App-session task object and persists through the task edit API
  so Todo and task-search views show the changed title after returning.
  Description, owner, deadline, priority, reminder setting, and attachment
  changes now use real API persistence. Source meeting is looked up through
  the existing meeting detail API and remains read-only in task detail.

## 2026-07-28

- Added the independent Expo task detail page from
  `docs/design/meetmind-app_task-detail.html` without backend changes. Todo
  and task-search cards now open a full-screen detail overlay first, preserving
  the underlying list/search state and hiding bottom navigation. The page uses
  real `TaskListItem` data from `GET /tasks`, refreshes best-effort through the
  existing list/search endpoint, displays read-only completion status,
  title, missing-description fallback, source meeting, owner, deadline,
  priority, evidence, and attachment fallback, and opens the source meeting
  through the existing meeting detail route with `initialTab='actions'` plus
  available evidence anchors. No task detail endpoint, edit API, attachment
  API, backend, database, Worker, Prompt, RAG, Validator, or schema changes
  were added.
- Fixed the task-card touch target for Expo by making the right-side task
  content area the explicit detail `Pressable` and keeping the left checkbox
  as the only status-update control. This avoids relying on nested Pressable
  propagation, so tapping title, deadline, priority, or right-side blank space
  opens task detail while tapping the checkbox only completes/reopens the task.

- Rebuilt the Expo `我的待办` home from
  `docs/design/meetmind-app_todo.html` on top of the existing `/tasks` API.
  The page now uses one `FlatList`, real task pagination, pull-to-refresh,
  keyword search, all/open/completed/overdue filters, real loaded-task
  statistics, source-meeting navigation into the existing meeting detail
  actions tab, deadline/overdue formatting, priority/status/owner tags, and
  the existing fixed bottom navigation. Task status controls are read-only
  because there is no ordinary task update API for this surface; tapping them
  shows a clear unsupported-version message instead of locally faking
  completion. No backend, database, Worker, Prompt, RAG, Validator, or
  six-dimension schema changes were made.
- Refined the Todo home controls by removing the separate all/open/completed/
  overdue tab row and changing task status indicators to square checkbox
  styling. The task title and checkbox now share the same status action entry,
  which remains read-only until a formal task update API exists.
- Added the independent Expo task search page from
  `docs/design/meetmind-app_task-search.html`. It is reached from the Todo
  home search button, uses the existing `GET /tasks?q=...` API after explicit
  keyboard search submission with stale-request guards, renders real task result cards without
  bottom navigation, opens source meetings on the existing detail `actions`
  tab, and stores only recent search keywords in AsyncStorage. No backend,
  database, Worker, Prompt, RAG, Validator, or schema changes were made.
- Enhanced `GET /tasks?q=...` to use fuzzy Chinese/English keyword matching
  within the existing endpoint. Search now matches split mixed-language terms
  across task title, evidence text, owner, owner name, status, priority, and
  meeting title, with common Chinese status/priority labels mapped to stored
  enum values.
- Added the formal Todo status update API `PATCH /tasks/{task_id}/status` for
  `open` and `completed`, and wired the Expo Todo cards to real checkbox
  updates with per-task loading, optimistic UI, and failure rollback. Todo
  cards and task-search result cards now display only checkbox, title,
  deadline, and priority. Task search no longer performs typing-time
  suggestions; it requests results only after the keyboard search action,
  retry, load-more, or a recent-search selection.
- Fixed Todo and task-search completion visuals so completing an item
  immediately shows the selected square checkbox plus grey strikethrough title
  during the optimistic update. Rebuilt the task-search input flow so typing
  clears stale submitted results and cancels stale requests; only the keyboard
  search action, the explicit search button, retry, load-more, or recent-search
  selection can request `/tasks?q=...`.
- Removed the remaining inline search state from the Todo home so the home no
  longer sends `GET /tasks?q=...` while typing; its search button only opens
  the independent task-search page. The task-search static check now fails if
  input changes call `runSearch` or `listTasks` directly.
- Restarted the local API listener on port 8002 after the status API change and
  verified that OpenAPI now exposes both `/tasks` and
  `/tasks/{task_id}/status`; the previous local process was still serving the
  old route table and caused mobile checkbox updates to return 404.
- Adjusted Todo completion interaction so tapping the checkbox or title first
  shows a checked square box plus grey strikethrough title for 300 ms, then
  clears the transition state without automatically switching the top filter
  to the completed view. The first statistics card is now `全部任务` and counts
  all loaded tasks, including active, completed, and overdue tasks.
- Removed the explicit in-field search submit button from task search. Search
  now reads the final `onSubmitEditing` text from the user's IME search action,
  updates the search box with that submitted keyword, and then calls
  `GET /tasks?q=...`; typing or Chinese IME composition still does not call the
  search API.

- Rebuilt the Expo Knowledge Base home from
  `docs/design/meetmind-app_knowledge-base.html` while staying on the existing
  API-only Knowledge Base MVP. The page now has the `MeetMind AI` top bar,
  disabled real-history state, static maintainable robot avatar, quick
  questions that fill the real `TextInput`, structured links to existing
  knowledge search, key decisions, and issue/risk pages, and a fixed input bar
  above the existing bottom navigation. The Knowledge Base content overview
  section was removed per product direction, so the home no longer loads
  `/knowledge/overview`, `/knowledge/meetings`, or `/tasks` just to render
  overview cards. Submitting questions now shows that Knowledge Base Q&A is
  not open instead of generating a fake answer. The plus button reuses the
  existing audio import flow. No backend, database, Worker, Prompt, RAG,
  Validator, six-dimension schema, model call, or new chat-history storage
  changes were made.

- Rebuilt the Expo meeting detail `Agent工具` tab from
  `docs/design/meeting-agent.html` while reusing the existing detail top
  navigation, inline player, and three-tab bar. The tab now shows four tool
  cards with availability/status labels, real knowledge-base reindex access
  through the existing `/meetings/{id}/knowledge/reindex` API, disabled states
  for email, Feishu, and mind map tools, a dashed "more features" placeholder,
  and an empty generation-record state because no persisted tool execution log
  endpoint exists for these tools. No backend, Worker, database, Prompt, RAG,
  Validator, OAuth, SMTP, Feishu, or model-generation changes were made.

- Finalized acceptance fixes for the Expo meeting detail `AI纪要` tab: summary
  text now preserves paragraph breaks, evidence timestamps accept seconds,
  `mm:ss`, and `hh:mm:ss`, evidence jumps defer transcript scrolling until the
  transcript tab is visible, missing segment anchors degrade with a clear
  message, all-empty six-dimension results show an overall empty state, and
  empty action objects no longer render blank todo rows. Static checks and
  summary export API regression coverage were expanded.
- Rebuilt the Expo meeting detail `AI纪要` tab from
  `docs/design/meeting-minutes.html` while reusing the existing detail top
  navigation, inline player, and three-tab bar. The tab now shows a meeting
  base card, real summary export entry for `summary` MD/PDF/DOCX/TXT, basic
  information, canonical six-dimension sections, read-only action item status,
  and available evidence/time anchors with legacy summary fallback preserved.
  No backend, Worker, database, Prompt, RAG, Validator, or six-dimension schema
  changes were made.
- Rebuilt the Expo meeting detail transcript tab from
  `docs/design/meetmind-app_meeting-detail.html` using React Native styles and
  a single vertical `FlatList`. The page now contains an in-page top nav,
  inline `expo-av` audio player, three-tab bar (`会议原文`, `AI纪要`, `Agent工具`),
  transcript quick look, transcript export entry, and a timeline rendering
  real `transcript_segments`.
- Added transcript playback controls on the detail page: play/pause,
  draggable progress, centered 15-second backward/forward seek, timestamp
  seek, bounded segment play, ended state handling, and explicit
  loading/missing/failed audio states. Audio still uses the existing
  `meetingAudioUrl()` and `expo-av` playback path.
- Updated segment playback so tapping the active segment icon pauses that
  segment, the preview stops at the segment end, and top-level playback no
  longer exposes a speed control.
- Added final transcript-player acceptance fixes: mobile audio selection no
  longer relies on `audio_files[0]`; meeting detail and the standalone audio
  player now share a playable-audio selector, release stale `expo-av` sounds
  when switching meetings/audio files, and guard rapid playback/seek actions.
- Fixed player progress dragging by switching progress bars to `PanResponder`:
  dragging now updates the displayed time/thumb immediately and commits a
  single bounded seek when the gesture ends.
- Kept AI summary rendering on the existing summary data path and left
  `Agent工具` as a placeholder for this stage. No API, Worker, database,
  Prompt, RAG, Validator, or six-dimension schema changes were made.

- Updated the Expo home screen to match the MeetMind AI RC1 home prototype:
  brand/search header, real-time recording and file import primary actions,
  `全部会议` cards, and the existing fixed bottom navigation.
- Replaced the previous home insight block with a single full-page `FlatList`
  so long meeting lists scroll vertically as part of the page, without
  nesting `ScrollView` and `FlatList`.
- Added a real file import screen using `expo-document-picker`. It creates a
  meeting, then reuses the existing `AIProcessingScreen` upload, process, and
  analyze flow; no backend, database, Prompt, RAG, Worker, or six-dimension
  schema changes were made.
- Home meeting cards now show title, status, start time, duration, AI summary
  state, todo count, and for completed summaries the first
  `meeting_agenda`, `key_conclusions`, and `action_items` entries with legacy
  `agenda`, `decisions`, and `next_steps` fallback.
- Fixed the mobile API timeout message text to the expected Chinese
  user-facing copy while keeping the existing request timeout behavior.
- Adjusted the home action label from `导入文件` to `导入音频`, removed the
  import action plus marker, changed the section date to `M月D日 今天/周X`,
  renamed `浏览全部` to `更多`, tightened the `全部会议` spacing, and made
  completed-card preview rows black, single-line, and content-height adaptive.

## 2026-07-27

- Refactored the Expo home screen to follow the MeetMind AI home prototype with
  a brand header, real-time recording action, file-import placeholder, weekly
  insight cards, and recent meeting cards.
- Kept home data connected to existing `GET /meetings` and completed-meeting
  summary requests. Summary fetch failures now degrade to empty counts and are
  cached as `null` for the current screen state so repeated requests for the
  same completed meeting are avoided.
- Preserved the existing recording, meeting detail navigation, history page,
  refresh, pagination, deletion, and bottom-tab route structure. The file
  import action is intentionally a clickable placeholder that shows
  "文件导入功能开发中" and does not add dependencies or backend upload behavior.

## 2026-07-24

- Added the Enterprise Meeting Knowledge Base MVP as an API-side PostgreSQL
  read model. Alembic revision `20260724_0016` creates
  `meeting_knowledge_items` and `meeting_knowledge_syncs`.
- Added idempotent `knowledge_sync_service` that maps completed
  `MeetingSummary`, persisted `ActionItem`, and `TranscriptSegment` rows into
  active knowledge items. Re-analysis updates matching source keys, marks
  removed old items `stale`, and meeting deletion marks knowledge `deleted`.
- Knowledge sync runs after successful Worker process/analyze responses and
  is isolated from the meeting completed state, Summary, ActionItems, and
  MeetingDetail reads. Worker models, Prompt, RAG, Validator, Shadow, and Agent
  write boundaries were not changed.
- Added Knowledge APIs: `/knowledge/overview`, `/knowledge/meetings`,
  `/knowledge/decisions`, `/knowledge/issues`, `/knowledge/risks`,
  `/knowledge/search`, plus `POST /meetings/{meeting_id}/knowledge/reindex`.
  MVP search uses PostgreSQL keyword matching and preserves project filtering
  as closed until meeting data has stable project scope.
- Replaced the basic Knowledge Base empty state with mobile pages for the
  knowledge home, meeting records, key decisions, issue/risk tabs, search home,
  search results, filter sheet, cards, empty/error states, and skeletons.
  The home page keeps four entries and a large search box only, with no recent
  meetings, AI Q&A, or AI assistant entry.
- Extended `MeetingDetailScreen` with `initialTab`, `sourceSegmentId`,
  `startTime`, and `evidenceText` so knowledge results can open the source
  meeting and narrow the transcript to the evidence text or segment.
- Added API knowledge tests and expanded the mobile Knowledge Base static test.

## 2026-07-23

- Replaced the default Expo bottom navigation AI Assistant entry with a
  Knowledge Base entry. The Knowledge Base screen currently provides only a
  basic page and empty state; full RAG question answering is not implemented.
- Added frontend feature switches:
  `EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=false` by default and
  `EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI=true` by default. Existing AI
  Assistant, Agent review records, Proposal, Command, Audit, and Rollback UI
  code remains in the codebase and can be re-exposed by configuration.
- Added API switch `AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=false` so completed
  meeting analysis no longer auto-creates Agent review proposals by default.
  Existing manual Agent proposal, confirmation, command, audit, rollback, auth,
  and review APIs remain registered.
- Changed local API startup defaults so `AGENT_LOCAL_AUTH_ENABLED=false` unless
  explicitly overridden for local RC validation.
- Added a fail-closed local Agent login/session flow for Expo acceptance.
  Mobile stores the Bearer session in AsyncStorage, restores it on AI assistant
  entry, injects `Authorization` only for `/agent/*` requests, clears expired
  sessions on 401, and separates unauthenticated, forbidden, empty, data, and
  error states.
- Added real-meeting AgentActionProposal generation for completed meeting
  summaries with persisted ActionItems. The generator reads existing
  `action_items`, matches only same tenant/project historical ActionItems,
  emits auditable diagnostics, and creates pending proposals only for
  evidence-backed `owner`, `due_date`, `priority`, or `status` changes. It does
  not write Requirement, Risk, or Summary business objects and remains
  idempotent.
- Fixed real end-to-end meeting analysis failures after upload/transcript
  success by preventing local API/Worker startup scripts from reusing
  non-project Python uvicorn processes, preserving Worker structured
  `error_code`/`error_stage`/`error_message` responses in
  `transcription_tasks.error_message`, mapping post-transcript failures to
  `summary_failed`, and updating the mobile AI processing screen to show the
  actual failed stage with retry-only analysis.
- Productized the Expo AI assistant review UI with a Chinese home page,
  safety banner, expandable pending proposal cards, approve/reject
  confirmation flows, recent records, all-records pagination, status filtering,
  time sorting, and record detail pages.
- Added read-only Agent review aggregation APIs:
  `GET /agent/review/overview`, `GET /agent/review/records`, and
  `GET /agent/review/records/{record_id}`. They return display DTOs from
  existing proposal, confirmation, command, audit, authoritative object, and
  meeting data, with server-side Bearer-token scope checks and metadata
  redaction.
- Kept Agent write scope unchanged. The UI still uses existing
  approve/reject APIs for human decisions, approval only creates a ready
  command, and this change does not modify Prompt, RAG, Validator, Shadow,
  production config, Requirement/Risk writes, or default grey/real execution
  switches.
- Fixed the meeting detail summary fallback display for legacy
  `meeting_outputs` rows. Summary fallback responses now include display
  metadata, the mobile summary card no longer exposes raw `result_source=...`,
  and stale failed meeting status no longer makes an available summary look
  failed. Added `npm run test:meeting-detail-ui` to the full local test script.
- Fixed history meeting loading timeouts by bounding `GET /meetings` with
  `limit`/`offset`, adding mobile request timeout handling, loading only the
  first home/history page initially, and adding load-more support plus
  `npm run test:meeting-history-ui`.
- Fixed recording upload regressions by routing mobile recording uploads
  through the shared timeout wrapper, mapping upload failures to Chinese user
  messages, preserving Expo `m4a` metadata as `audio/x-m4a`, adding API upload
  regression coverage, and using a finite Worker timeout for realtime chunk
  transcription requests.

## 2026-07-22

- Fixed Expo recent-meeting cards that stayed in the analyzing/loading state
  after service startup when the latest meeting was only `audio_uploaded`.
  Uploaded meetings now render as `已上传`/`待处理`, completed-meeting summaries
  are the only ones fetched for home statistics, and API startup recovers stale
  `queued`/`running` meeting tasks left by a service restart.

- Added Agent v1.0 Phase 15 final acceptance and release decision artifacts.
- Added `services/api/scripts/run_agent_phase15_final_acceptance.py` for a
  synthetic PostgreSQL API acceptance using real Bearer token auth,
  AgentActionProposal approval, controlled ActionItem execute, duplicate
  execute idempotency, audit query, metrics, controlled rollback, release
  preflight, and Requirement/Risk/summary isolation checks.
- Updated Phase 12 PostgreSQL acceptance data generation to use the current
  authoritative `AgentActionItem` version after Phase 13 introduced
  `action_items.version`.
- Added Phase 15 final acceptance report, release decision, risk/open-item
  list, grey checklist, rollback/emergency runbook, and conversation document.
- Final decision is `GO` for internal controlled grey only; production-wide
  writes, Requirement/Risk writes, summary JSON writes, cancel, high/critical,
  batch execution, automatic approval, Prompt/RAG/Validator changes, Shadow
  promotion, and default grey enablement remain out of scope.

- Added Agent v1.0 Phase 14 production safety hardening and grey acceptance
  guardrails without expanding the Phase 13 write contract.
- Added fail-closed grey settings for tenant/project/user whitelists, grey
  percentage, per-project and per-user daily execution limits, concurrency
  limit, UTC time window, manual pause, tenant/project pause, global kill
  switch, circuit thresholds, and manual audit-backed recovery.
- Added `services/api/app/agent_phase14_guardrails.py` and wired it before the
  Phase 13 pilot mutation step. Unconfigured grey execution is rejected and
  audited with `writes_performed=false`.
- Added operational APIs under `/agent/ops` for scoped metrics, redacted audit
  search, circuit status, circuit reset, and preflight release-gate checks.
- Added `services/api/scripts/run_agent_phase14_postgres_acceptance.py` for
  PostgreSQL grey acceptance on synthetic `phase14_pg_` data, covering default
  rejection, whitelist rejection, quota/concurrency, circuit breakers, kill
  switch, tenant/project pause, restart-persistent circuit state, audit tenant
  isolation, controlled rollback after emergency close, and unchanged
  Requirement/Risk/summary JSON.
- Requirement/Risk writes, summary JSON writes, cancel, high/critical commands,
  non-whitelisted writes, automatic approval, batch execution,
  Prompt/RAG/Validator changes, Shadow promotion, default grey enablement, and
  production-wide release remain disabled.

- Added Agent v1.0 Phase 13 restricted real-write pilot for internal
  tenant/project scopes only.
- Added Alembic revision `20260721_0015` with `action_items.version`, and
  switched `AgentActionItem` authoritative versions to that integer field.
- Added fail-closed pilot switches:
  `AGENT_COMMAND_PILOT_ENABLED=false`,
  `AGENT_COMMAND_PILOT_TENANTS=`, and
  `AGENT_COMMAND_PILOT_PROJECTS=`, while keeping execution disabled and
  dry-run-only enabled by default.
- Implemented pilot execution for `AgentActionItem` `update` / `complete` only,
  with low/medium risk, field whitelist `owner`, `due_date`, `priority`,
  `status`, tenant/project whitelist validation, row locks, expected-version
  checks, `version + 1`, same-transaction audit, and idempotent duplicate
  handling.
- Implemented pilot rollback execution for successful Phase 13 commands only,
  requiring rollback permission, confirmation comment, execution-audit version
  match, same-transaction rollback audit, conflict rejection, and idempotent
  duplicate rollback.
- Added `POST /agent/commands/{command_id}/execute` and
  `POST /agent/commands/{command_id}/rollback/execute`, plus Agent Review UI
  controls that display internal pilot scope, before/after values, and rollback
  status without allowing the client to submit changes, permissions, versions,
  or idempotency keys.
- Added Phase 13 unit coverage and
  `services/api/scripts/run_agent_phase13_postgres_acceptance.py` for
  PostgreSQL pilot acceptance on synthetic `phase13_pg_` data, covering
  default rejection, whitelist denial, real ActionItem write, transaction
  rollback, concurrency, restart idempotency, rollback success/conflict, and
  unchanged Requirement/Risk/summary JSON.
- Requirement/Risk writes, cancel, high/critical commands, non-whitelisted
  projects, automatic approval, batch execution, Prompt/RAG/Validator changes,
  Shadow promotion, and production-wide release remain disabled.

## 2026-07-21

- Added Agent v1.0 Phase 12 real-write preparation without enabling real
  writes.
- Added Alembic revision `20260721_0014` with
  `action_item_scope_backfill_audits` for historical `action_items`
  tenant/project backfill audit, review, idempotency, and rollback evidence.
- Added `services/api/app/action_item_scope_backfill.py`. Backfill applies
  tenant/project only from a unique, non-default, verifiable Requirement/Risk
  scope for the same summary or meeting; existing valid scopes are preserved
  and unverifiable/conflicting rows enter `review`.
- Added Phase 12 transaction rehearsal in `agent_command_executor.py`. It locks
  the command row, re-reads authoritative state, validates ready/version/scope,
  and writes Agent audit records with `business_writes_performed=false`; it
  does not update Requirement, Risk, ActionItem, or summary JSON business data.
- Added `services/api/scripts/run_agent_phase12_postgres_acceptance.py` for
  PostgreSQL safety acceptance on synthetic prefixed data, covering backfill
  success/review/idempotency/rollback, existing-scope preservation, migration
  rollback, transaction failure rollback, concurrent idempotency, restart
  idempotency, rollback conflict rejection, isolation, and unchanged formal
  business data.
- Added Agent v1.0 Phase 11 production identity and first-class authoritative
  state foundation.
- Added Alembic revision `20260721_0013` with `requirements`, `risks`,
  `agent_users`, and `agent_auth_sessions`, plus `tenant_id` and `project_id`
  columns on `action_items`.
- Added server-side Bearer token/session authentication for Agent APIs.
  `AgentPrincipal` is now built from `agent_auth_sessions` and `agent_users`
  and includes `user_id`, `tenant_id`, `roles`, `permissions`,
  `project_scope`, `object_scope`, and `authentication_source`. Missing,
  unknown, expired, revoked, or inactive sessions return 401.
- Updated `DatabaseAuthoritativeStateProvider` so `Requirement` reads from
  `requirements`, `AgentActionItem` reads from `action_items`, and `Risk` reads
  from `risks`. Requirement/Risk provider reads no longer scan
  `meeting_summaries` JSON.
- Added migration extraction from summary JSON into first-class Requirement/Risk
  tables. Complete candidates keep source status, incomplete candidates enter
  `review`, source meeting/summary/field/index and raw source references are
  retained, original summary JSON is preserved, and source uniqueness prevents
  duplicate migration.
- Expanded API tests for valid token authentication, expired/revoked token 401,
  Requirement/Risk formal table reads, Provider no-summary-JSON behavior,
  tenant/project/object isolation, and unchanged formal business data.
- Added `services/api/scripts/run_agent_phase11_postgres_acceptance.py` for
  PostgreSQL migration and isolation acceptance covering token auth,
  expired/revoked denial, Requirement/Risk migration, review fallback,
  idempotency, rollback, tenant/project/object isolation, summary JSON
  retention, and no Agent business writes.
- Added Agent v1.0 Phase 10 production-permission safety layer before any real
  writes. Agent APIs no longer trust client-submitted `X-Agent-Reviewer` or
  `X-Agent-Permissions`; authorization now goes through the server-side
  `AgentPrincipal` adapter in `services/api/app/agent_security.py`.
- The default Agent auth adapter fails closed with 401 because the project has
  no production auth/session/JWT module yet. Tests and local acceptance scripts
  inject principals through FastAPI dependency overrides only.
- Added operation permissions `proposal_view`, `proposal_review`,
  `command_dry_run`, `command_execute`, `audit_view`, and `rollback_execute`
  with user identity, project scope, object scope, operation, and risk-level
  checks. High-risk approvals require elevated role/permission.
- Added rollback dry-run support under
  `POST /agent/commands/{command_id}/rollback/dry-run`. It requires a persisted
  command id and original dry-run audit, re-reads authoritative state, checks
  version/idempotency, generates a rollback command preview, and writes audit
  records with `writes_performed=false`.
- Added the explicit real-write transaction contract stub in
  `agent_command_executor.py`; it documents authoritative re-read,
  expected-version optimistic locking, ready-state check, idempotency recovery,
  single-transaction business write plus audit, failure rollback, and success
  status transition, but Phase 10 deliberately rejects real writes.
- Added `AGENT_ROLLBACK_EXECUTION_ENABLED=false` and kept
  `AGENT_COMMAND_EXECUTION_ENABLED=false` plus
  `AGENT_COMMAND_DRY_RUN_ONLY=true` as default safety flags.
- Expanded API tests for unauthenticated access, forged client permission
  headers, insufficient permission, project/object isolation, high-risk
  approval denial, dry-run/audit permissions, audit-failure rollback,
  service-restart idempotency, rollback dry-run success/duplicate/conflict,
  and business-row isolation.
- Added `services/api/scripts/run_agent_phase10_security_acceptance.py` for
  PostgreSQL safety acceptance covering auth fail-closed, scope/risk denial,
  idempotent dry-run, rollback dry-run, conflict rejection, and unchanged
  formal business data.

- Added Agent v1.0 Phase 9 minimum Expo Agent Review workbench under the AI tab.
- The UI lists proposal states including `pending`, `approved`, `rejected`,
  `expired`, `conflict`, `duplicate`, and `ready`; shows target object, current
  state, suggested changes, evidence, confidence, risk level, confirmation
  requirement, version state, ready commands, dry-run results, audit records,
  and rollback previews.
- Approval and rejection actions use second confirmation dialogs and call the
  existing Phase 8 proposal confirmation API.
- Added API command routes under `/agent/commands` for command read, dry-run,
  and command audit reads. These routes do not accept client-submitted
  commands, expected versions, changes, or idempotency keys.
- Added `services/api/app/agent_command_executor.py`, a dry-run-only command
  sandbox that re-reads authoritative state, validates command `ready` status,
  optimistic version, permissions, idempotency key, target existence, and
  expected changes, then writes dry-run audit records with rollback previews.
- Added runtime switches `AGENT_COMMAND_EXECUTION_ENABLED=false` and
  `AGENT_COMMAND_DRY_RUN_ONLY=true`. Default configuration rejects command
  execution; tests explicitly enable dry-run only.
- Added API tests for dry-run success, execution switch rejection, non-ready
  command rejection, version-conflict rejection, repeated dry-run idempotency,
  audit and rollback preview generation, and formal business-row isolation.
- Added Mobile type/static checks for the Agent Review UI and ensured the
  client does not submit `expected_object_version` or `idempotency_key`.

## 2026-07-20

- Added Agent v1.0 Phase 8 minimum API-side confirmation loop.
- Added `DatabaseAuthoritativeStateProvider` for read-only production snapshots:
  `AgentActionItem` from `action_items`, and `Requirement`/`Risk` from existing
  `meeting_summaries` JSON fields.
- Added Alembic revision `20260720_0012` with
  `agent_action_proposals`, `agent_proposal_confirmations`,
  `controlled_write_commands`, and `agent_audit_records`.
- Added `/agent/action-proposals` endpoints for saving proposals, listing
  pending proposals, reading proposal details, approving proposals, and
  rejecting proposals.
- Approval now re-reads authoritative state, uses the saved expected object
  version, checks permissions, expiry, idempotency, evidence, audit context, and
  field whitelists through `ControlledWritePlanner`, then persists an inert
  command and audit record. It still does not execute formal business writes.
- Hardened Phase 8 approval/rejection consistency: command idempotency keys no
  longer include per-request confirmation ids; approval/rejection reads lock the
  proposal row with PostgreSQL `SELECT ... FOR UPDATE`; only
  `pending -> approved/rejected/expired/conflict` is allowed; approved
  confirmations are persisted only after planner success; repeated
  approve/reject calls reuse existing results; and database unique-constraint
  conflicts are recovered as idempotent duplicate results instead of 500s.
- Added offline API tests for provider reads, proposal persistence and query,
  approve/reject, unauthorized confirmation rejection, idempotent duplicate
  approval, version conflict, expiry, missing target, non-whitelisted fields,
  command/audit persistence, formal business object isolation, and OpenAPI
  compatibility.
- Added `services/api/scripts/run_agent_phase8_postgres_checks.py` for
  PostgreSQL Alembic head, migration, command idempotency uniqueness,
  concurrent approval, and formal business-row isolation checks.
- Added Agent v1.0 Phase 7 Worker-internal write-control contracts in
  `services/worker/app/agent_write_control.py`.
- Phase 7 defines `AuthoritativeStateProvider`,
  `AuthoritativeStateSnapshot`, `AgentProposalConfirmation`,
  `ControlledWriteCommand`, `AuditRecord`, `RollbackPlan`, and offline
  `ControlledWritePlanner` support.
- Added safety checks for approved confirmations, expired/rejected decisions,
  optimistic version conflicts, permission denial, object-not-found cases,
  field whitelist violations, duplicate idempotency keys, missing evidence,
  missing audit context, high-risk confirmation, audit record generation, and
  rollback plan generation. Commands remain inert and record
  `writes_performed=false`.
- Added Phase 7 unit tests to the default Worker test gate without calling real
  Qwen3, Ollama, Chroma, PostgreSQL, external network, API, or Expo.
- Added Agent v1.0 Phase 6 Worker-internal cross-meeting state tracker in
  `services/worker/app/agent_state_tracker.py`.
- Phase 6 supports bounded candidate reading, object normalization,
  deterministic matching, state-change classification, evidence-backed
  `AgentActionProposal` generation, proposal validation, and human-confirmation
  flags for `Requirement`, `AgentActionItem`, and `Risk`.
- Extended the internal `AgentActionProposal` contract with Phase 6 fields:
  `action_type`, `confidence`, `risk_level`, `requires_confirmation`, `reason`,
  and `metadata`, while preserving existing `proposal_type` and
  `needs_confirmation` compatibility.
- Added Phase 6 unit tests to the default Worker test gate. The tests cover same
  object matching, new object detection, complete/defer/cancel classification,
  duplicate detection, uncertain review flags, owner/deadline confirmation,
  insufficient evidence confirmation, historical conflicts, high-risk closure
  confirmation, and no database/model/RAG/network side effects.
- Added Agent v1.0 Phase 5B live Shadow acceptance tooling in
  `services/worker/scripts/run_agent_shadow_live_acceptance.py`.
- The Phase 5B tool supports offline-by-default runs, explicit
  `--allow-live-model`, smoke/full selection, `--meeting-id`, `--scenario`,
  per-run `--ollama-timeout`, optional `nvidia-smi` GPU monitoring,
  stop-on-failure gates, quality scoring templates, formal-result snapshot
  hashes, and per-meeting debug artifacts under
  `data/debug/agent_shadow_live_acceptance/<run_id>/`.
- Added Phase 5B unit tests to the default Worker test gate. The tests cover
  default no-real-model behavior, smoke/full and filtered fixture selection,
  serial stop-on-failure behavior, timeout propagation, GPU monitor failure
  degradation, artifact structure, unavailable layer markers, and formal-result
  isolation checks without calling real Qwen3, Chroma, PostgreSQL, or external
  network services.
- Added Agent v1.0 Phase 5 Shadow acceptance fixtures for three core
  scenarios: `project_weekly`, `requirement_review`, and `cross_department`.
- Added `run_agent_shadow_acceptance.py`, an offline-by-default acceptance
  script that writes `acceptance_report.json/.md`, per-meeting summaries, and
  Shadow audit files under `data/debug/agent_shadow_acceptance/<timestamp>/`.
- Calibrated Phase 2 scenario context policy for `requirement_review` and
  `cross_department` so Phase 4B static plans include meeting history for the
  Phase 5 core scenario acceptance gate.
- Added Phase 5 acceptance tests to the default Worker test gate, covering
  scenario plan selection, manual meeting type control, safe degradation for
  missing history/RAG results, failure/timeout/fallback statistics, report
  serialization, and default no-real-model behavior.
- Added Agent v1.0 Phase 4B controlled Worker-internal Orchestrator and Shadow
  Mode sidecar execution after formal summary persistence.
- Added file audit output under `data/debug/agent_shadow_trace/<meeting_id>/`
  with Agent run status, steps, result source, shadow analysis, validator audit,
  fallback reason, and deterministic comparison summary.
- Added Agent Orchestrator tests for Shadow switches, static plan generation,
  unknown minimal plans, audit writing, timeout/failure isolation, fallback
  preservation, deterministic comparisons, and import-side-effect boundaries.
- Added Agent v1.0 Phase 4A Worker-internal Tool Registry and controlled
  Runtime infrastructure.
- Added `ExecutionPlan`, `ExecutionStep`, `AgentRunState`, and
  `AgentStepResult` contracts for static, in-memory Tool execution.
- Added Agent Runtime unit tests for registry behavior, ordered execution,
  optional skips, stop/continue failure handling, timeout/deadline/call limits,
  fallback preservation, and import-side-effect boundaries.
- Added Agent v1.0 Phase 3 first-batch Worker-internal Tool Adapters:
  `get_meeting_context`, `search_meeting_history`,
  `search_project_knowledge`, `get_open_action_items`, `analyze_meeting`, and
  `validate_meeting_analysis`.
- Added Tool contracts for `AgentTool`, `ToolExecutionContext`, `ToolResult`,
  `ToolError`, `ToolPolicy`, and `ToolStatus`, with unified duration, timeout,
  call-limit, structured-error, and result-source handling.
- Added Agent Tool tests to the default Worker test gate.
- Added Agent v1.0 Phase 2 Worker-internal meeting scenario policies with
  schema version `meeting-scenario-policy-v1`.
- Added eight formal meeting scenario policies plus safe `unknown` defaults,
  an immutable policy contract, a deterministic in-memory registry, and a
  `MeetingClassificationResult` contract that reuses `EvidenceRef`.
- Added Phase 2 meeting scenario tests to the default Worker test gate.
- Added Agent v1.0 Phase 1 Worker-internal contract schemas:
  `EvidenceRef`, `Requirement`, `Decision`, `AgentActionItem`, `Issue`, `Risk`,
  `Dependency`, `Milestone`, `CustomerRequest`, `ProjectState`,
  `AgentActionProposal`, and `AgentContext`.
- Added `agent-contract-v1` schema version metadata and tests for Agent contract
  serialization, enum validation, evidence validation, mutable defaults, and
  isolation from the formal `MeetingAnalysisSchema`.
- Added Agent v1.0 Phase 0 baseline freeze documentation and baseline dataset
  directory specification.
- Added API and Worker Agent rollout guardrail settings:
  `AGENT_MODE_ENABLED=false`, `AGENT_SHADOW_MODE=true`, and
  `AGENT_ACTIONS_ENABLED=false`.
- Fixed a production analysis stall where stale `transcript_segments`
  `speaker_name` update locks blocked subsequent summary analysis runs.
- Changed Worker summary orchestration to commit speaker-name backfill before
  RAG/Qwen inference so long model calls do not hold transcript row locks.
- Added `RAG_EMBEDDING_LOCAL_FILES_ONLY=true` Worker setting and made
  `RagRetriever` load the embedding model from local cache by default to avoid
  blocking on Hugging Face metadata requests during manual Worker starts.
- Repaired meeting `73c47be6-0ea0-41eb-ac73-81e458574abd` by rerunning Worker
  analysis successfully; generated summary
  `33db99a1-634d-4d57-b28b-f720c4d9bcde`.

## 2026-07-15

- Added Phase 4 unified meeting analysis schema boundary.
- Added Worker analysis contract normalization before persistence.
- Added summary response `metadata.schema_version`.
- Added schema boundary documentation and ADR 0003.
- Added Phase 5 prompt and RAG version management.
- Moved the formal Qwen3 Meeting Analyst prompt into a versioned prompt template and registry.
- Added RAG dataset manifest, configurable RAG settings, retrieved chunk id tracking, and summary metadata persistence.
- Added Alembic migration `20260715_0011` for prompt/RAG metadata fields.
- Added Phase 6 testing and observability improvements.
- Added Worker/API `/ready` checks, structured Worker analysis logs with redaction, and local service diagnostics.
- Added fake Qwen/RAG Meeting Analyst service tests and regression fixture shape checks.
- Added observability documentation and ADR 0005.
