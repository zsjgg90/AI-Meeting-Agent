# Current Tasks

## Active Priority

1. Keep the default mobile bottom navigation on Knowledge Base instead of AI
   Assistant. The Knowledge Base MVP now uses API-side PostgreSQL knowledge
   items generated from completed meeting summaries, action items, and
   transcript segments. Do not wire RAG question answering or AI assistant
   entry points into the Knowledge Base until a later explicit task.
2. Keep Agent review auth fail-closed and hidden by default. Expo Agent review
   pages and local Agent login remain available only when the UI/config is
   explicitly re-enabled.
3. Keep real-meeting Proposal generation evidence-bound and disabled by
   default. Completed summaries may auto-create pending ActionItem proposals
   only when `AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=true`, and still only for
   same-scope historical object changes across `owner`, `due_date`,
   `priority`, and `status`; new objects, ambiguous matches, no-change items,
   and insufficient evidence must be skipped with diagnostics.
4. Keep Expo Go recent-meeting startup flow stable; uploaded meetings must not
   be displayed as active AI analysis, and stale API background tasks must be
   recovered on service restart.
5. Keep the MeetMind AI RC1 home screen on the current API-only mobile flow:
   brand/search header, real-time recording, audio import, full-page `全部会议`
   list, and fixed bottom navigation. Audio import must continue to reuse the
   existing create-meeting plus `AIProcessingScreen` upload/process/analyze
   path without backend, database, Prompt, RAG, Worker, or schema changes.
6. Keep the rebuilt meeting detail transcript page on existing API-only data:
   `audio_files`, `transcript_segments`, `speaker_mappings`, and transcript
   exports. The detail page may refine React Native UI, player ergonomics, and
   timestamp navigation, but must not add model calls, backend changes, fake
   chapters, or six-dimension schema changes for transcript display.
7. Keep the rebuilt meeting detail AI summary tab on existing API-only
   summary data. It should prefer canonical `meeting_agenda`,
   `meeting_summary`, `key_conclusions`, `action_items`,
   `unresolved_issues`, and `risks_and_focus`, preserve legacy aliases, use
   the existing `/exports/summary.{format}` backend export path, and display
   action item status as read-only until a formal update contract is exposed
   to this surface.
8. Keep the hidden Expo AI assistant review UI on top of existing Agent
   proposal/confirmation/command/audit data without expanding real-write scope.
9. Archive Agent v1.0 Phase 15 final acceptance and prepare internal controlled
   grey only under the approved Phase 13/14 scope.
10. Keep formal Qwen3 + RAG meeting analysis stable.
11. Keep Expo Go flow stable: create meeting -> record -> upload -> process -> analyze -> display.
   Recording upload now has timeout-bounded mobile requests, Chinese upload
   errors, Expo `audio/x-m4a` API regression coverage, and a local HTTP upload
   smoke check. History meeting loading remains bounded with `limit`/`offset`
   and load-more pagination.
   End-to-end summary failure recovery now requires project-venv API/Worker
   port ownership, structured Worker error persistence, and retry-only mobile
   re-analysis from existing audio/transcript.
12. Follow the seven-phase maintainability plan in `docs/PHASE_PLAN.md` for RC
   maintenance issues that remain relevant.
13. Use `data/debug/semantic_pipeline_trace/<meeting_id>/comparison.md` to locate
   semantic quality errors before considering formal semantic output again.
14. Use `data/debug/chain_audit/<meeting_id>/chain_audit.md` before debugging an
   Expo-visible summary, especially when the meeting metadata indicates a
   manual fixture such as `fixture-gold-standard`.

## Pending Engineering Tasks

- Keep Agent v1.0 work on `feature/agent-v1`; do not continue Agent work on
  `main`.
- Verify the enterprise Knowledge Base MVP against more real meetings before
  considering a separate `meeting_knowledge` Chroma collection. PostgreSQL is
  the current source of truth; project filtering remains closed until
  `project_id` is consistently present on meeting data.
- Import the 19 required Agent v1.0 baseline meeting artifact folders under
  `data/eval/agent_v1_baseline/`.
- Keep Phase 2 meeting scenario policies as read-only contracts until a later
  Agent Runtime phase explicitly wires them in.
- Keep Phase 3 Tool Adapters as thin wrappers only. Phase 4A may register and
  execute them through static plans, but must not add Orchestrator integration,
  write-path tools, or action execution.
- Keep Phase 4B Agent Shadow Mode as a sidecar only. It may write debug audit
  files, but must not overwrite formal summaries, action items, project state,
  requirements, risks, issues, or decisions.
- Keep Phase 5 acceptance data synthetic and sanitized under
  `data/eval/agent_v1_baseline/phase5_core_scenarios/`. Generated reports must
  remain under ignored `data/debug/agent_shadow_acceptance/`.
- Keep Phase 5B live Shadow acceptance artifacts under ignored
  `data/debug/agent_shadow_live_acceptance/`. The tool is
  `services/worker/scripts/run_agent_shadow_live_acceptance.py`; default runs
  must not call real Qwen3 unless `--allow-live-model` is explicitly passed.
- Keep Phase 6 cross-meeting state tracking as Worker-internal proposal
  generation only. The module is `services/worker/app/agent_state_tracker.py`
  and supports `Requirement`, `AgentActionItem`, and `Risk` with bounded
  historical candidates, deterministic matching, and evidence-backed
  `AgentActionProposal` output.
- Phase 6 proposals must not be executed, persisted, exposed through API, or
  connected to Expo confirmation UI until a later phase defines the state
  source, confirmation contract, and controlled write boundary.
- Keep Phase 7 write control as Worker-internal offline command generation
  only. The module is `services/worker/app/agent_write_control.py` and defines
  `AuthoritativeStateProvider`, `AgentProposalConfirmation`,
  `ControlledWriteCommand`, audit records, rollback plans, permission checks,
  optimistic version checks, field whitelists, and idempotency checks.
- Phase 7 commands must not be executed, persisted, exposed through API, or
  connected to Expo confirmation UI until a later phase defines the production
  state source and controlled write service.
- Keep Phase 8 confirmation API as a minimum backend loop only. It may persist
  `AgentActionProposal`, `AgentProposalConfirmation`,
  `ControlledWriteCommand`, and `AgentAuditRecord` rows, but commands remain
  inert and must not update formal `action_items` rows or summary JSON.
- Phase 8 approval/rejection must keep proposal terminal states immutable. The
  current backend lock path uses PostgreSQL row locking and stable command
  idempotency keys; SQLite tests are functional checks only and are not
  concurrency evidence.
- `DatabaseAuthoritativeStateProvider` is the current production read source:
  `Requirement` reads from `requirements`, `AgentActionItem` reads from
  `action_items`, and `Risk` reads from `risks`. It no longer scans
  `meeting_summaries` JSON as the formal authoritative source.
- Phase 8/11 non-blocking risks to resolve before production confirmation UI or
  command execution: proposal list/detail response exposure of evidence and
  metadata, production-scale review of Phase 12 historical `action_items`
  tenant/project backfill results, duplicated API/Worker Agent contract drift,
  foreign-key `ondelete` policy, and the minimal Agent auth tables needing
  integration with the broader product identity system.
- Keep Phase 9 command execution as dry-run only. The API command sandbox may
  read persisted ready commands, re-read authoritative state, validate version,
  permission, idempotency, and target state, and write dry-run audit records
  with rollback previews. It must not update `action_items`, summary JSON,
  Requirement, or Risk state.
- Expo AI assistant review UI is now a productized review surface under the AI
  tab. It must call the API only, use review aggregation endpoints for display,
  use approve/reject confirmation endpoints for human decisions, and must not
  construct `expected_version`, `ControlledWriteCommand`, tenant/project scope,
  reviewer identity, permissions, or idempotency keys on the client.
- Keep Phase 10 as a pre-real-write safety layer only. Agent APIs must use the
  server-side `AgentPrincipal` auth adapter and must not trust
  `X-Agent-Reviewer` or `X-Agent-Permissions` headers. The current adapter
  fails closed until a production auth/session provider is wired in; tests use
  dependency overrides only.
- Phase 10 permissions are explicit operation scopes:
  `proposal_view`, `proposal_review`, `command_dry_run`, `command_execute`,
  `audit_view`, and `rollback_execute`. Authorization must check user identity,
  project scope, object scope, operation type, and risk level; high-risk
  approvals require elevated role/permission.
- Keep rollback execution in Phase 10 as dry-run only. Rollback dry-run must
  require a persisted command id and original dry-run audit, re-read
  authoritative state, validate version/idempotency, generate a rollback
  command preview, write audit records with `writes_performed=false`, and must
  not update formal business tables.
- `services/api/scripts/run_agent_phase10_security_acceptance.py` is the
  PostgreSQL safety acceptance script for auth fail-closed, scope/risk denial,
  dry-run idempotency, rollback dry-run, conflict rejection, and formal
  business-row isolation.
- Keep Phase 11 as read-only authoritative-state foundation only. Production
  Agent auth comes from `agent_auth_sessions` and `agent_users`; missing,
  expired, revoked, or inactive sessions return 401, while tenant/project/object
  scope failures return 403. Requirement/Risk first-class tables are migration
  targets and read sources only; Agent must not modify `requirements`, `risks`,
  `action_items`, or summary JSON in this phase.
- `services/api/scripts/run_agent_phase11_postgres_acceptance.py` is the
  PostgreSQL migration and isolation acceptance script for production token
  auth, expired/revoked denial, Requirement/Risk migration, review fallback,
  migration idempotency, rollback, tenant/project/object isolation, summary JSON
  retention, and formal business-row isolation.
- Keep Phase 12 as real-write preparation only. Historical `action_items`
  tenant/project backfill may only use a unique, non-default, verifiable
  Requirement/Risk scope from the same summary or meeting; unverifiable or
  conflicting rows must enter review and must not be guessed from defaults.
- Phase 12 transaction rehearsal may lock commands, re-read authoritative
  state, validate permissions/version/idempotency, and write Agent audit
  records, but it must not mutate `requirements`, `risks`, `action_items`, or
  summary JSON business fields.
- `services/api/scripts/run_agent_phase12_postgres_acceptance.py` is the
  PostgreSQL safety acceptance script for synthetic Phase 12 data. Run it only
  against a database where Phase 12 downgrade/upgrade rehearsal is acceptable;
  do not run it directly on production data.
- Keep Phase 13 as a restricted internal pilot only. Real execution is allowed
  only when `AGENT_COMMAND_EXECUTION_ENABLED=true`,
  `AGENT_COMMAND_DRY_RUN_ONLY=false`, `AGENT_COMMAND_PILOT_ENABLED=true`, and
  the target tenant/project is explicitly listed in
  `AGENT_COMMAND_PILOT_TENANTS` / `AGENT_COMMAND_PILOT_PROJECTS`.
- Phase 13 may write only `AgentActionItem` rows in whitelisted internal test
  projects, only for `update` / `complete`, only fields `owner`, `due_date`,
  `priority`, and `status`, and only low/medium risk commands that are already
  manually approved and `ready`. Existing high-risk approval rules still apply
  to `complete`.
- Phase 13 rollback execution is limited to successful Phase 13 pilot commands.
  It requires independent confirmation, `rollback_execute`, current version
  match, and same-transaction rollback audit. Conflicts must be rejected.
- Phase 13 must not write Requirement/Risk rows, must not run `cancel`,
  high/critical, non-whitelisted tenant/project, automatic approval, batch
  execution, Prompt/RAG/Validator changes, Shadow promotion, production
  release, or production-wide real writes.
- `services/api/scripts/run_agent_phase13_postgres_acceptance.py` is the
  PostgreSQL pilot acceptance script for synthetic `phase13_pg_` data. Run it
  only against a disposable or explicitly safe test database where
  downgrade/upgrade rehearsal is acceptable.
- Keep Phase 14 as production safety hardening and grey acceptance only. It may
  add grey guardrails, monitoring, audit search, circuit breaker status/reset,
  preflight checks, and failure drills around the Phase 13 ActionItem pilot,
  but must not expand the object, operation, field, or risk scope.
- Phase 14 real execution is still allowed only for Phase 13
  `AgentActionItem` `update` / `complete`, low/medium risk, and fields
  `owner`, `due_date`, `priority`, and `status`, after explicit tenant/project
  pilot whitelist and explicit grey tenant/project/user whitelist, percentage,
  quota, and concurrency settings.
- Phase 14 defaults reject real execution because grey is disabled and all
  limits are 0. It must not enable production grey by default.
- `services/api/scripts/run_agent_phase14_postgres_acceptance.py` is the
  PostgreSQL grey acceptance script for synthetic `phase14_pg_` data. Run it
  only against a disposable or explicitly safe test database.
- Agent v1.0 Phase 15 final decision is `GO` for internal controlled grey only.
  This is not production-wide enablement. The approved scope remains
  `AgentActionItem`, `update` / `complete`, fields `owner`, `due_date`,
  `priority`, `status`, low/medium risk, manual approval, and explicit
  tenant/project/user grey whitelists with quotas, concurrency limits,
  preflight, audit, metrics, circuit breakers, pause, and kill switch.
- `services/api/scripts/run_agent_phase15_final_acceptance.py` is the Phase 15
  final API/DB acceptance script for synthetic `phase15_pg_` data. It validates
  real Bearer token auth, proposal approval, controlled execute, duplicate
  execute idempotency, audit query, metrics, controlled rollback, preflight,
  and unchanged Requirement/Risk/summary data.
- Phase 5 calibrated only scenario context requirements for
  `requirement_review` and `cross_department` so their static plans load meeting
  history as required by acceptance. Prompt, RAG, Validator, API, DB, Expo, and
  formal analysis behavior remain unchanged.
- Defer `get_project_context` and `get_active_risks` until a formal Project
  state source and independent risk state model exist.
- Decide whether to archive or remove legacy `api` and `mobile` directories.
- Move backup Worker files out of active source paths.
- Keep API, Worker, AI, and Expo schemas aligned through the Phase 4 schema boundary.
- Align API contract docs with actual OpenAPI contracts.
- Run Alembic migration `20260715_0011` in local and Docker databases.
- Add end-to-end recording/upload/process/analyze/display smoke test.
- Add migration verification script.
- Fix the sentence-level SemanticEvent intent classifier before changing mapper
  or validator rules. Current gold trace shows the first errors at
  `02_semantic_events_raw`.
- Reproduce Expo summary issues through the real production path before tuning
  analysis logic. The latest Expo fixture result was manually inserted from a
  gold answer and is not valid evidence for Qwen3 + RAG or semantic output
  quality.
- Use `metadata.result_source` in Expo/API responses to distinguish
  `fixture`, `legacy_qwen_rag`, and `semantic_pipeline` before judging quality.
- Use `services/worker/scripts/run_real_production_analysis.py` for single
  V3.2 production-chain diagnostics under
  `data/debug/real_production_analysis/<meeting_id>/`.
- The current `meeting_001` legacy Qwen3 + RAG quality audit is under
  `data/debug/real_production_analysis/meeting_001/quality_audit.md`.
  It found first semantic errors in `model_raw_output.json`; normalized output
  preserved those errors rather than creating new ones.
- Add live Qwen3 + RAG evaluation gate outside default unit tests.
- Phase 5B full live acceptance has completed locally under
  `data/debug/agent_shadow_live_acceptance/20260720-163624` with 9/9 meetings
  passed and `overall_passed=true`; keep those artifacts ignored and treat
  quality scoring as rule-assisted with manual review required.
- Review the 2026-07-18 `prompt_stability_eval` artifacts before production
  rollout. The deterministic PostProcessor fixed proposal leakage and metadata
  cleanup, but duplicate-run semantic stability still fails for agenda/action
  consistency and the risk-review meeting.
- Continue monitoring local `qwen3:14b` latency; long meetings now use the
  rule-based semantic fast path, while small meetings and legacy comparison can
  still expose local model latency issues.
- Keep Worker RAG embedding startup in local-cache mode
  (`RAG_EMBEDDING_LOCAL_FILES_ONLY=true`) and avoid holding
  `transcript_segments` row locks during long RAG/Qwen analysis. The
  2026-07-20 Expo failure for meeting `73c47be6-0ea0-41eb-ac73-81e458574abd`
  was repaired after terminating stale transcript update locks and rerunning
  Worker `/analyze` successfully.

## Explicit Non-Goals For Current Phase

- No business logic rewrite.
- No database migration unless a future phase explicitly requires one.
- No Qwen3/RAG prompt or validator changes.
- No Phase 15 production-wide enablement, default grey enablement, or scope
  expansion beyond internal controlled grey.
- No UI redesign.
- No queue system migration.
- No cross-meeting object persistence or Agent action execution until later
  Agent phases.
- No real meeting classifier or Agent action execution in Phase 2.
- No Tool Registry, Agent Runtime, write-path Tool, ASR Tool, diarization Tool,
  project-state update Tool, or cross-meeting object matching in Phase 3.
- No Shadow Mode wiring, Orchestrator integration, model free planning,
  multi-Agent execution, write-path Tool, Action execution, project-state
  update, or formal-chain integration in Phase 4A.
- No Agent result promotion, action execution, database persistence for Agent
  business objects, API exposure, frontend confirmation flow, or semantic
  comparison scoring in Phase 4B.
- No Agent result promotion, action execution, write-path Tool, cross-meeting
  state persistence, real classifier, Prompt/RAG/Validator change, API change,
  database migration, or Expo change in Phase 5.
- No Agent result promotion, action execution, write-path Tool,
  cross-meeting state persistence, real classifier, Prompt/RAG/Validator
  change, API change, database migration, Expo change, or Phase 6 work in
  Phase 5B.
- No Agent result promotion, action execution, write-path Tool,
  cross-meeting state persistence, real classifier, Prompt/RAG/Validator
  change, API change, database migration, Expo change, or frontend
  confirmation flow in Phase 6.
- No Agent result promotion, action execution, write-path Tool,
  cross-meeting state persistence, real classifier, Prompt/RAG/Validator
  change, API change, database migration, Expo change, frontend confirmation
  flow, automatic approval, or command execution in Phase 7.
- No Agent Action execution, automatic approval, Expo confirmation UI,
  Prompt/RAG/Validator change, Shadow promotion, or formal business object
  write in Phase 8.
- No real Agent command execution, automatic approval, production permission
  replacement, rollback executor, Prompt/RAG/Validator change, Shadow
  promotion, or formal Requirement/ActionItem/Risk write in Phase 9.
- No real Agent command execution, automatic approval, real production auth
  provider, real rollback execution, Prompt/RAG/Validator change, Shadow
  promotion, production release, or formal Requirement/ActionItem/Risk write in
  Phase 10.
- No real Agent command execution, automatic approval, real business object
  mutation, real rollback execution, Prompt/RAG/Validator change, Shadow
  promotion, production release, or formal Requirement/ActionItem/Risk write in
  Phase 11.
