# Agent v1 Phase 15 Final Acceptance

## Development Goal

Complete Agent v1 final acceptance and release decision without adding product
functionality, expanding write scope, enabling production grey by default, or
starting the next phase.

## Background

Phase 13 introduced the restricted internal `AgentActionItem` real-write pilot.
Phase 14 added grey guardrails, metrics, audit search, circuit breakers, and
preflight. Phase 15 validates whether that constrained system can enter
internal controlled grey.

## Implementation

- Added `services/api/scripts/run_agent_phase15_final_acceptance.py` to run a
  synthetic PostgreSQL API acceptance with real Bearer token auth, internal
  grey scope, manual approval, controlled execute, idempotent duplicate
  execute, audit query, metrics, controlled rollback, preflight, and business
  isolation checks.
- Updated the Phase 12 PostgreSQL acceptance script to use the current
  authoritative `AgentActionItem` version source after Phase 13 introduced
  `action_items.version`.
- Added Phase 15 final acceptance, release decision, risk, grey checklist, and
  rollback/emergency runbook documentation.

## Modified Content

No runtime product feature was added. The Phase 15 script uses `phase15_pg_`
synthetic rows, process-local test settings, and cleans up after execution.

## Impact

Impact is limited to acceptance tooling and documentation. Prompt, RAG,
Validator, Shadow behavior, API product contracts, Expo UI, production config,
Requirement/Risk writes, high/critical execution, cancel, batch execution, and
automatic approval were not changed.

## Tests

Executed and passed:

```powershell
.\scripts\test-all.ps1
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase11_postgres_acceptance.py
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase12_postgres_acceptance.py
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase13_postgres_acceptance.py
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase14_postgres_acceptance.py
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_live_acceptance.py --mode full --allow-live-model --ollama-timeout 600
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase15_final_acceptance.py
```

## Known Limits

- The decision is only for internal controlled grey.
- Metrics are still internal only.
- Broader product identity integration remains a non-blocking internal-grey
  risk and a blocker for wider exposure.

## Follow-Up

Create an archive tag after review, for example:

```text
agent-v1-phase15-final-acceptance
```
