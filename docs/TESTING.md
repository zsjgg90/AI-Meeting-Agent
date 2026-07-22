# Testing

## Unified Local Check

Run the default local checks:

```powershell
.\scripts\test-all.ps1
```

Default checks:

1. Compile API Python modules.
2. Compile Worker Python modules.
3. Run API contract tests.
4. Run Worker unit tests.
5. Run Mobile TypeScript typecheck.

Optional health checks against already-running local services:

```powershell
.\scripts\test-all.ps1 -Health
```

`-Health` checks both `/health` and `/ready` for API and Worker. `/ready`
validates runtime dependencies such as database connectivity, Worker
connectivity, prompt availability, Ollama model availability, and RAG collection
availability where applicable.

Useful fast variants:

```powershell
.\scripts\test-all.ps1 -SkipMobile
.\scripts\test-all.ps1 -SkipApiTests
.\scripts\test-all.ps1 -SkipWorkerTests
```

## Individual Checks

Backend syntax check:

```powershell
services\api\.venv\Scripts\python.exe -m compileall -q services\api\app
services\worker\.venv\Scripts\python.exe -m compileall -q services\worker\app
```

Mobile type check:

```powershell
cd apps/mobile
npm run typecheck
npm run test:numbered-list
npm run test:agent-review-ui
```

## Existing Worker Tests

## Existing API Tests

```powershell
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_api_contract
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config
```

These tests validate route registration and response schemas through OpenAPI. They do not require a live database.

## Existing Worker Tests

```powershell
python -m unittest services.worker.tests.test_anti_hallucination_validator
python -m unittest services.worker.tests.test_meeting_analyst_pipeline
python -m unittest services.worker.tests.test_meeting_analyst_service_fake
python -m unittest services.worker.tests.test_observability
python -m unittest services.worker.tests.test_regression_fixtures
python -m unittest services.worker.tests.test_worker_contract
python -m unittest services.worker.tests.test_volcengine_speaker_diarization
python -m unittest services.worker.tests.test_agent_config
python -m unittest services.worker.tests.test_agent_contract
python -m unittest services.worker.tests.test_meeting_scenarios
python -m unittest services.worker.tests.test_agent_tools_contract
python -m unittest services.worker.tests.test_agent_tools_adapters
python -m unittest services.worker.tests.test_agent_runtime
python -m unittest services.worker.tests.test_agent_orchestrator
python -m unittest services.worker.tests.test_agent_state_tracker
python -m unittest services.worker.tests.test_agent_write_control
python -m unittest services.worker.tests.test_agent_shadow_acceptance
python -m unittest services.worker.tests.test_agent_shadow_live_acceptance
```

Worker tests are split into two groups:

- Offline contract tests: fake model/RAG, schema, prompt/RAG metadata,
  observability, and route registration. These must not require Ollama, Chroma,
  PostgreSQL, or formal audio services.
- Live checks: optional service readiness and evaluation scripts. These may
  require PostgreSQL, Ollama, Chroma, and the configured model.

## Service Diagnostics

Run the local dependency check against already-running services:

```powershell
.\scripts\check-services.ps1
```

The script checks:

- PostgreSQL port
- Ollama port and expected model
- API `/health` and `/ready`
- Worker `/health` and `/ready`
- Prompt file
- RAG manifest
- Vector DB directory
- Alembic heads command

Redis and Expo Metro are reported as optional local development checks.

## Existing Evaluation Scripts

```powershell
python services/worker/scripts/run_eval_meeting_analyst.py
python services/worker/scripts/run_semantic_event_boundary_eval.py
python services/worker/scripts/test_semantic_event_extractor.py
python services/worker/scripts/test_topic_event_aggregator.py
python services/worker/scripts/test_six_dimension_mapper.py
python services/worker/scripts/test_six_dimension_validator.py
python services/worker/scripts/test_meeting_analysis_pipeline.py
python services/worker/scripts/run_meeting_pipeline_acceptance.py --limit 3 --ollama-timeout 60
python services/worker/scripts/run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
python services/worker/scripts/run_prompt_stability_eval.py --meeting-limit 4 --meeting-indices 1,2,3,4 --runs-per-meeting 2 --ollama-timeout 180
```

`test_topic_event_aggregator.py` uses hand-built `SemanticEvent` objects and
does not call Qwen3, Ollama, Chroma, PostgreSQL, API, or Expo.

`test_six_dimension_mapper.py` uses hand-built `TopicEventGroup` objects and
does not call Qwen3, Ollama, Chroma, PostgreSQL, API, or Expo.

`test_six_dimension_validator.py` uses hand-built `TopicEventGroup` and
`SixDimensionResult` objects and does not call Qwen3, Ollama, Chroma,
PostgreSQL, API, or Expo.

`test_meeting_analysis_pipeline.py` uses a fake semantic event extractor and
legacy fallback stub. It validates the integrated semantic pipeline, empty-result
fallback behavior, long-meeting rule-based fast path, schema compatibility,
shadow-mode behavior, seven-stage trace generation, and evidence traceability
without calling real Qwen3, Ollama, Chroma, PostgreSQL, API, or Expo.

`test_agent_contract.py` validates the Worker-internal Agent v1 contract
schemas. It covers serialization, enum validation, shared `EvidenceRef`
structure, confidence bounds, mutable default isolation, `AgentContext`
metadata merging, and isolation from the formal `MeetingAnalysisSchema` without
calling Qwen3, Ollama, Chroma, PostgreSQL, API, or Expo.

`test_meeting_scenarios.py` validates the Worker-internal Agent v1 Phase 2
meeting scenario policies. It covers all eight formal meeting types plus
`unknown`, registry behavior, duplicate registration rejection, enum validation,
policy serialization, immutable policies, classification result validation,
safe unknown defaults, mutable default isolation, and isolation from the formal
`MeetingAnalysisSchema` without calling Qwen3, Ollama, Chroma, PostgreSQL, API,
RAG, or Expo.

`test_agent_tools_contract.py` validates the Phase 3 Tool contract and unified
execution wrapper. It covers serialization, policy validation, status
validation, structured errors, duration recording, max calls per run, deadline
handling, timeout conversion, ordinary exception conversion, retryable error
reporting, mutable default isolation, and isolation from `MeetingAnalysisSchema`.

`test_agent_tools_adapters.py` validates the first six Phase 3 Tool Adapters
using fake DB, fake RAG retriever, fake analysis service, and fake validator
dependencies. These tests do not call real Qwen3, Ollama, Chroma, PostgreSQL,
external network, API, or Expo.

`test_agent_runtime.py` validates the Phase 4A Worker-internal Tool Registry
and controlled Runtime. It covers registration, lookup, duplicate registration,
unknown tools, read-only policy enforcement, default six-tool registry
construction without calling providers, ordered static execution, optional
skips, stop-or-continue failure handling, timeout/deadline/call-limit handling,
step duration/status recording, fallback preservation, previous-step payload
handoff, and import isolation from real Qwen3, Chroma, PostgreSQL, external
network, API, and Expo.

`test_agent_orchestrator.py` validates Phase 4B controlled Orchestrator and
Shadow Mode sidecar behavior. It covers Shadow disabled/enabled switches, Agent
Mode non-promotion, scenario-to-static-plan mapping, `unknown` minimal plan,
file audit writing, failure/timeout isolation from formal results, fallback and
`result_source` preservation, deterministic comparison summaries, no formal DB
write calls from Shadow wiring, and import isolation from real Qwen3, Chroma,
PostgreSQL, external network, API, and Expo.

`test_agent_state_tracker.py` validates the Phase 6 cross-meeting state
tracker without calling real Qwen3, Ollama, Chroma, PostgreSQL, external
network, API, or Expo. It covers bounded candidate reading, same object
matching, new object detection, complete/defer/cancel classification, duplicate
object detection, uncertain matches with `needs_review`, owner and deadline
confirmation, insufficient evidence confirmation, historical conflict handling,
high-risk closure confirmation, and the guarantee that the tracker does not
write database state.

`test_agent_write_control.py` validates the Phase 7 write-control contracts
without calling real Qwen3, Ollama, Chroma, PostgreSQL, external network, API,
or Expo. It covers authoritative state reads, approved/rejected/needs-changes
and expired confirmations, missing confirmation rejection, optimistic version
conflicts, permission denial, non-whitelisted fields, idempotency duplicate
commands, high-risk confirmation, audit records, rollback plans, missing target
and evidence rejection, and the guarantee that no database write is performed.

`test_agent_confirmation_api.py` validates the Phase 8 API confirmation loop
with an offline SQLite in-memory database and FastAPI dependency overrides. It
does not call real Qwen3, Ollama, Chroma, PostgreSQL, external network, Worker,
or Expo. It covers database authoritative-state reads for `Requirement`,
`AgentActionItem`, and `Risk`, proposal save/list/detail, approve/reject,
missing reviewer, insufficient permissions, duplicate approval idempotency,
version conflicts, expired proposals, missing target objects, non-whitelisted
fields, stable idempotency keys, terminal proposal states, duplicate
approve/reject no-op behavior, rollback on mid-transaction failures,
unique-constraint duplicate recovery, command/audit persistence, OpenAPI
compatibility, and the guarantee that the formal `ActionItem` row is not
changed by approval.

The same API test module now covers the Phase 9 command dry-run sandbox, Phase
10 pre-real-write safety layer, and Phase 11 production auth/authoritative-state
foundation. It validates dry-run success,
execution-switch rejection, non-ready command rejection, optimistic version
conflict rejection, repeated dry-run idempotency, audit and rollback preview
generation, OpenAPI command routes, and the guarantee that formal `ActionItem`
rows and summary JSON are unchanged by dry-run. Phase 10 coverage adds
unauthenticated request rejection, forged `X-Agent-Reviewer`/
`X-Agent-Permissions` header rejection, insufficient permission, project and
object isolation, high-risk approval denial for ordinary reviewers, dry-run and
audit permission checks, audit-failure rollback, service-restart idempotency,
rollback dry-run success, duplicate rollback dry-run, rollback conflict
rejection, and the real-write contract stub refusing writes. Phase 11 coverage
adds valid Bearer token authentication, expired/revoked token 401,
Requirement/Risk formal table reads, Provider no-summary-JSON behavior,
tenant/project/object isolation, and unchanged formal business data. Phase 12
coverage adds historical `action_items` tenant/project backfill from a unique
verifiable Requirement/Risk scope, unverifiable rows entering review,
idempotent repeat backfill, rollback, preservation of existing valid scope,
transaction rehearsal audit-only behavior, and rehearsal mid-transaction
rollback without changing formal business rows. Phase 13 coverage adds the
restricted internal ActionItem real-write pilot: default switch rejection,
non-whitelisted tenant/project denial, non-pilot field/risk denial, successful
ActionItem update, `version + 1`, same-transaction execution audit, injected
failure rollback, repeated execution idempotency, rollback success, rollback
version-conflict rejection, duplicate rollback idempotency, tenant/project
scope denial, and unchanged Requirement/Risk formal rows.

`npm run test:agent-review-ui` performs a lightweight static check of the Expo
Agent Review workbench. It verifies the presence of proposal list/detail,
approve/reject second-confirmation text, `conflict`/`expired`/`duplicate`
status handling, dry-run action, audit records, rollback preview, writes
performed display, and Agent API helpers. It also checks that mobile request
bodies do not submit `expected_object_version` or `idempotency_key`. It also
checks that mobile request bodies do not submit Agent command changes or
permissions. It also checks that Expo no longer sends `X-Agent-Reviewer` or
`X-Agent-Permissions` headers; Agent identity and permissions must come from
the API server-side auth adapter.

`services/api/scripts/run_agent_phase8_postgres_checks.py` validates the Phase
8 PostgreSQL path that SQLite cannot prove. It checks that Alembic has one
head, upgrades to head, seeds synthetic Agent-only test data, runs two
concurrent approval calls for one proposal, verifies that at most one ready
command and one confirmation are created, verifies one stable idempotency key,
and verifies the formal `action_items` row is not changed. Run it with:

```powershell
$env:PYTHONPATH="D:\codex_work\会议声纹识别;D:\codex_work\会议声纹识别\services\api;D:\codex_work\会议声纹识别\services\worker"
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase8_postgres_checks.py
```

`services/api/scripts/run_agent_phase10_security_acceptance.py` validates the
Phase 10 PostgreSQL safety path. It upgrades Alembic to head, uses synthetic
prefixed Agent data, verifies default auth fails closed, verifies forged client
Agent headers are ignored, checks project/object/risk denials, approves one
proposal idempotently, runs command dry-run idempotently, runs rollback dry-run
idempotently, rejects rollback version conflict, and verifies the formal
`ActionItem` owner remains unchanged. Run it with:

```powershell
$env:PYTHONPATH="D:\codex_work\浼氳澹扮汗璇嗗埆;D:\codex_work\浼氳澹扮汗璇嗗埆\services\api;D:\codex_work\浼氳澹扮汗璇嗗埆\services\worker"
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase10_security_acceptance.py
```

`services/api/scripts/run_agent_phase11_postgres_acceptance.py` validates the
Phase 11 PostgreSQL migration and isolation path. It uses synthetic prefixed
data, downgrades to Phase 10, seeds Phase-10-shape summary/action rows, upgrades
to head, verifies Requirement/Risk migration and `review` fallback, runs
upgrade idempotency, validates production Bearer token auth and expired/revoked
session denial, checks tenant/project/object Provider isolation, verifies the
original `meeting_summaries` JSON is unchanged, verifies the formal
`ActionItem` row is unchanged, downgrades to Phase 10 to prove rollback, and
restores Alembic head. Run it only against a database where Phase 11 downgrade
is acceptable:

```powershell
$env:PYTHONPATH="D:\codex_work\会议声纹识别;D:\codex_work\会议声纹识别\services\api;D:\codex_work\会议声纹识别\services\worker"
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase11_postgres_acceptance.py
```

`services/api/scripts/run_agent_phase12_postgres_acceptance.py` validates the
Phase 12 PostgreSQL safety path on synthetic `phase12_pg_` data. It upgrades to
head, seeds scoped/unscoped action items plus first-class Requirement/Risk
sources, verifies dry-run/apply/repeat/rollback backfill behavior, downgrades
to Phase 11 to prove migration rollback, upgrades again, verifies transaction
rehearsal failure rollback, concurrent idempotency, restart idempotency,
rollback conflict rejection, tenant/project isolation, and unchanged formal
business data. Run it only against a database where Phase 12
downgrade/upgrade rehearsal is acceptable:

```powershell
$env:PYTHONPATH="D:\codex_work\会议声纹识别;D:\codex_work\会议声纹识别\services\api;D:\codex_work\会议声纹识别\services\worker"
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase12_postgres_acceptance.py
```

`services/api/scripts/run_agent_phase13_postgres_acceptance.py` validates the
Phase 13 restricted PostgreSQL pilot on synthetic `phase13_pg_` data. It
upgrades to head, seeds a whitelisted internal ActionItem plus Requirement/Risk
control rows, verifies migration downgrade to Phase 12 and upgrade back to
head, verifies default execution rejection, injected transaction failure
rollback, concurrent execution idempotency, service-restart idempotency,
rollback success, duplicate rollback, rollback conflict rejection, tenant/
project whitelist enforcement, and unchanged Requirement/Risk/summary JSON.
Run it only against a disposable or explicitly safe test database where
downgrade/upgrade rehearsal is acceptable:

```powershell
$env:PYTHONPATH="D:\codex_work\浼氳澹扮汗璇嗗埆;D:\codex_work\浼氳澹扮汗璇嗗埆\services\api;D:\codex_work\浼氳澹扮汗璇嗗埆\services\worker"
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase13_postgres_acceptance.py
```

`test_agent_shadow_acceptance.py` validates the Phase 5 Shadow acceptance
infrastructure for `project_weekly`, `requirement_review`, and
`cross_department`. It covers the 9 synthetic fixtures, manual `meeting_type`
strategy selection, safe degradation when history/RAG fixture results are empty,
Tool failure/timeout/fallback statistics, report JSON serialization, and the
default guarantee that the acceptance script does not call the real model.

`test_agent_shadow_live_acceptance.py` validates the Phase 5B live Shadow
acceptance tooling without calling real Qwen3, Ollama, Chroma, PostgreSQL,
external network, API, or Expo. It covers default `--allow-live-model=false`,
smoke/full fixture selection, `--meeting-id` and `--scenario` filtering,
serial stop-on-failure behavior, `--ollama-timeout` propagation into the live
layer runner, `nvidia-smi` monitor start/stop and failure degradation, required
artifact structure, unavailable layer markers when live model execution is not
allowed, GPU CSV parsing for `nvidia-smi` headers with comma-space separators
and unit-suffixed values, and formal-result snapshot isolation.

Phase 5 Shadow acceptance can be run offline with:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_acceptance.py
```

It writes `acceptance_report.json`, `acceptance_report.md`, per-meeting
summaries, and Shadow audit files under
`data/debug/agent_shadow_acceptance/<timestamp>/`. The script uses offline
fixture analysis by default. Passing `--allow-live-model` is required before it
may call the existing `analyze_meeting` Tool and therefore Qwen3/RAG. Offline
fixture durations such as `0.15 ms` validate only the report and Runtime
structure; they must not be used as real Qwen3/RAG performance evidence.

Phase 5B live Shadow acceptance tooling can be exercised offline with:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_live_acceptance.py --mode smoke
```

This default command does not call Qwen3/RAG. It writes run configuration,
report files, per-meeting artifacts, unavailable markers for live-only layers,
formal-result snapshot hashes, and optional GPU summaries under:

```text
data/debug/agent_shadow_live_acceptance/<run_id>/
```

After explicit approval to run the real model, use smoke first:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_live_acceptance.py --mode smoke --allow-live-model --ollama-timeout 300 --gpu-monitor --stop-on-failure
```

For live acceptance, start Worker with stdout/stderr captured under the ignored
debug directory before running smoke/full:

```powershell
cd "D:\codex_work\会议声纹识别\services\worker"
.\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --host 0.0.0.0 `
  --port 8001 `
  *> "..\..\data\debug\agent_shadow_live_acceptance\worker-phase5b.log"
```

If real-time viewing is needed, use `Tee-Object` or another PowerShell logging
pattern that does not change Worker business logic. If Worker keeps the port
open but `/health` or `/ready` stop responding, first preserve this log and
collect a process/thread stack snapshot before changing Worker code.

Only after the 3-meeting smoke run passes should the full 9-meeting run be
executed:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_live_acceptance.py --mode full --allow-live-model --ollama-timeout 300 --gpu-monitor --stop-on-failure
```

The Phase 5B live gate is intentionally outside default unit tests because it
can be slow and depends on local `qwen3:14b`, Ollama, RAG/Chroma, local
embedding cache, and GPU runtime state.

Semantic shadow trace files are written under:

```text
data/debug/semantic_pipeline_trace/<meeting_id>/
```

These files are debug artifacts only. They should not be treated as formal API
or database output.

`run_meeting_pipeline_acceptance.py` is a live acceptance gate. It uses real
Qwen3/Ollama and existing RAG to compare the semantic pipeline with the legacy
Qwen3 + RAG path on 3-5 built-in meeting transcripts. It writes per-meeting
inputs, outputs, comparisons, logs, and `acceptance_report.json/.md` under
`data/debug/meeting_pipeline_acceptance/<timestamp>/`. The report distinguishes
direct new-pipeline success, fallback success, and new/legacy combined failure.

`run_real_production_analysis.py` is a single-meeting live diagnostic for the
formal production path. It defaults to the current V3.2 `meeting_001` transcript
and writes `input_transcript.txt`, `rag_context.json`, `prompt.txt`,
`model_raw_output.json`, `normalized_result.json`, and `pipeline.log` under
`data/debug/real_production_analysis/<meeting_id>/`.

Validator-only regression for `meeting_001` can be run against the existing
`model_raw_output.json` without calling Qwen3. The expected artifacts are
`validated_result.json` and `validator_audit.md` under
`data/debug/real_production_analysis/meeting_001/`. The unit test
`test_anti_hallucination_validator` covers agenda compression, flow-talk
removal, cross-dimension duplicate handling, complete evidence acceptance,
ellipsis evidence rejection, unsupported owner/deadline/priority cleanup,
proposal exclusion from core conclusions, and allowed decision/action pairs.

Prompt-only live regression after editing
`services/worker/app/prompts/meeting_analyst_qwen3.md` should use the existing
`meeting_001` transcript and write `model_raw_output_v2.json`,
`normalized_result_v2.json`, and `quality_audit_v2.md` in the same directory.
This live check calls Qwen3 and is intentionally outside default unit tests.

`run_prompt_stability_eval.py` is a live multi-meeting stability gate. It reads
the desktop meeting-script pack by default, selects 3-5 meetings, runs each
meeting twice with the same Qwen3 model, Prompt, and RAG configuration, and
writes per-meeting `run_1_result.json`, `run_2_result.json`, `comparison.json`,
plus aggregate `stability_report.json/.md` under
`data/debug/prompt_stability_eval/`. It records agenda counts, continuous
evidence validity, cross-dimension duplicates, unsupported action metadata,
proposal leakage into conclusions, resolved issues in open issues, Validator
changes, model latency, duplicate-run semantic differences, conclusion/action
set consistency, agenda topic consistency, output-order consistency, and
inference-parameter equality.

## Missing Test Coverage

- API to Worker integration tests with real background tasks.
- Expo screen tests.
- Runtime UI automation for the Agent Review workbench against a live API.
- End-to-end recording/upload/process/analyze/display smoke test.
- CI coverage for the Phase 8 PostgreSQL concurrency script against a disposable
  PostgreSQL service.
- CI coverage for the Phase 11 migration rollback script against a disposable
  PostgreSQL service.
- Live Qwen3 + RAG evaluation gate in CI.
- Human semantic-quality review for live semantic-pipeline acceptance reports.
- Automated regression script for API analyze background tasks using seeded transcript segments.

## Remaining Gaps

- Default tests intentionally do not call real Qwen3/Ollama.
- Default tests intentionally do not load the formal Chroma collection.
- Readiness checks require local services to already be running.
- Live acceptance is intentionally separate because it can be slow and depends
  on the local `qwen3:14b` runtime latency.
