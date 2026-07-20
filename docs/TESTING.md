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
- End-to-end recording/upload/process/analyze/display smoke test.
- Migration upgrade/current verification against a clean PostgreSQL instance.
- Live Qwen3 + RAG evaluation gate in CI.
- Human semantic-quality review for live semantic-pipeline acceptance reports.
- Automated regression script for API analyze background tasks using seeded transcript segments.

## Remaining Gaps

- Default tests intentionally do not call real Qwen3/Ollama.
- Default tests intentionally do not load the formal Chroma collection.
- Readiness checks require local services to already be running.
- Live acceptance is intentionally separate because it can be slow and depends
  on the local `qwen3:14b` runtime latency.
