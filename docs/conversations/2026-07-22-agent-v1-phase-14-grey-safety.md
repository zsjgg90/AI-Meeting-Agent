# Agent v1 Phase 14 Grey Safety

## Development Goal

Execute Agent v1 Phase 14: production safety hardening and grey acceptance
around the Phase 13 restricted real-write pilot without expanding the write
scope.

## Background

Phase 13 enabled a tightly restricted internal `AgentActionItem` pilot for
`update` and `complete`, low/medium risk, and fields `owner`, `due_date`,
`priority`, and `status`. Phase 14 adds operational controls needed before any
broader acceptance review.

## Implementation

- Added fail-closed grey settings for tenant/project/user whitelists, grey
  percentage, project/user daily limits, concurrency limit, UTC time window,
  manual pause, tenant/project pause, global kill switch, circuit thresholds,
  and manual recovery timestamp.
- Added `services/api/app/agent_phase14_guardrails.py`.
- Wired Phase 14 guardrails before the Phase 13 business mutation step in
  `services/api/app/agent_command_executor.py`.
- Added `/agent/ops` endpoints for metrics, scoped redacted audit search,
  circuit status, circuit reset, and release preflight.
- Added Phase 14 unit coverage to API Agent tests.
- Added PostgreSQL grey acceptance script
  `services/api/scripts/run_agent_phase14_postgres_acceptance.py`.
- Added grey runbook `docs/AGENT_PHASE14_GREY_RUNBOOK.md`.

## Modified Content

Phase 14 uses existing Agent tables and does not add a migration. Guardrail
rejections are written to `agent_audit_records` with
`writes_performed=false`. Circuit reset writes an operations audit anchor and
does not modify business rows.

## Impact

The impact is limited to API Agent guardrails, operational read APIs, tests,
PostgreSQL acceptance tooling, and documentation. It does not modify Worker
Prompt, RAG, Validator, Shadow promotion, formal Qwen3 + RAG analysis,
Requirement/Risk business writes, summary JSON writes, cancel operations,
high/critical commands, automatic approval, batch execution, or production
release behavior.

## Tests

Executed and passed:

```powershell
services\api\.venv\Scripts\python.exe -m compileall -q services\api\app services\api\scripts services\api\alembic\versions
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase14_postgres_acceptance.py
.\scripts\test-all.ps1
```

`test-all.ps1` covered API compile, Worker compile, API contract and Agent
tests, Worker unit tests, Mobile TypeScript typecheck, and
`npm run test:agent-review-ui`.

## Known Limits

- No external monitoring platform integration is included; metrics are exposed
  through an internal provider endpoint.
- Preflight reports the gate state but does not itself enable grey execution.
- Circuit recovery is audit-backed and operational; persistent configuration
  switches such as kill switch and manual pause still require operator config
  changes.

## Follow-Up

Review Phase 14 acceptance evidence and `/agent/ops/preflight` output before
deciding whether the project is ready for Phase 15 final acceptance.
