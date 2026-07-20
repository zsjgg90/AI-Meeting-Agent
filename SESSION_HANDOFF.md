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

1. Review Phase 9 dry-run audit and rollback preview output before adding any
   real command execution service.
2. Keep the Phase 8/9 non-blocking risks visible: proposal list/detail evidence
   and metadata exposure, Requirement/Risk JSON scan behavior, duplicated
   API/Worker Agent contracts, FK `ondelete` policy, and header permissions as
   development-only authorization.
3. Decide whether Requirement and Risk need independent production business
   tables before any write execution phase; Phase 8 reads them only from
   existing summary JSON snapshots.
4. Keep Agent action execution disabled until a real write service, production
   authorization integration, command persistence semantics, and rollback
   transactions are specified.
5. Import the remaining required Agent baseline meeting artifact folders under
   `data/eval/agent_v1_baseline/` when available.
6. Run `.\scripts\check-services.ps1` with local services available.
7. Continue embedding model offline/cache setup, shared API/Worker model
   strategy, live benchmark gate, and E2E demo script.
