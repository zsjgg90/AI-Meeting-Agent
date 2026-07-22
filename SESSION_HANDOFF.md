# Session Handoff

## Current State

The project is in Release Candidate verification state after completing the seven-phase maintainability hardening plan.
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

1. Review Phase 14 grey safety guardrails, PostgreSQL grey acceptance, audit
   evidence, and `/agent/ops/preflight` output before considering Phase 15 final
   acceptance.
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
