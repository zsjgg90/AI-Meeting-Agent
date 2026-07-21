# Changelog

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
