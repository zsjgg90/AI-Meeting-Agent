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

1. Review and accept Agent v1.0 Phase 5 Shadow acceptance report and fixture
   coverage.
2. Prepare Phase 6 cross-meeting state tracking design only after Phase 5 is
   accepted. Do not add action execution, write-path Tools, or Agent result
   promotion yet. Phase 6 still needs an explicit formal cross-meeting state
   source and write-boundary design before implementation.
3. Import the remaining required Agent baseline meeting artifact folders under
   `data/eval/agent_v1_baseline/` when available.
4. Run `.\scripts\check-services.ps1` with local services available.
5. Continue embedding model offline/cache setup, shared API/Worker model
   strategy, live benchmark gate, and E2E demo script.
