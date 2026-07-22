# Agent Phase 15 Final Acceptance Report

## Scope

Agent v1.0 Phase 15 is a final acceptance and release decision phase. It does
not add product functionality, expand write scope, enable production grey by
default, or start Phase 15+ work.

The only allowed grey release scope remains:

- Internal tenant/project/user whitelist only.
- Object: `AgentActionItem`.
- Operations: `update`, `complete`.
- Fields: `owner`, `due_date`, `priority`, `status`.
- Risk levels: `low`, `medium`.
- Manual confirmation required.
- Quota, concurrency, circuit breaker, pause, and kill switch protection.

## Baseline

- Branch: `feature/agent-v1`.
- Baseline tag: `agent-v1-phase14`.
- Baseline commit before Phase 15 validation: `9cf6a314c39e1cd151a8f10e21465004df966e46`.
- Alembic current/head after validation: `20260721_0015`.

## Regression Results

Executed on 2026-07-22:

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

Results:

- `test-all.ps1`: passed. API tests: 76 OK. Worker tests: 138 OK. Mobile
  TypeScript and Agent Review UI static checks passed.
- Phase 11 PostgreSQL: passed production token auth, expired/revoked denial,
  Requirement/Risk migration, rollback, tenant/project/object isolation,
  summary JSON retention, and no Agent business writes.
- Phase 12 PostgreSQL: passed backfill, migration rollback, transaction
  rehearsal, concurrent idempotency, audit-failure rollback, restart
  idempotency, rollback conflict rejection, isolation, and unchanged formal
  business data.
- Phase 13 PostgreSQL: passed restricted ActionItem write, version increment,
  same-transaction audit, injected failure rollback, concurrent/restart
  idempotency, rollback success/duplicate/conflict, whitelist enforcement, and
  unchanged Requirement/Risk/summary JSON.
- Phase 14 PostgreSQL: passed default reject, non-whitelisted user reject,
  quota/concurrency, circuit breakers, kill switch, tenant/project pause,
  restart-persistent circuit state, audit tenant isolation, emergency rollback,
  and unchanged Requirement/Risk/summary JSON.
- Phase 5B full live Shadow acceptance: passed 9/9 meetings with
  `overall_passed=true`, `qwen3:14b`, `temperature=0`, `top_p=0.2`, `seed=42`,
  `format=json`, no timeout/fallback/error, and formal result isolation.
- `meeting_001` real production analysis: passed with `legacy_qwen_rag`,
  transcript chars 1381, RAG chunks 8, prompt chars 7571, Ollama duration
  42512.78 ms, total duration 42740.51 ms.
- Phase 15 final API/DB acceptance: passed proposal, manual approval,
  controlled execute, duplicate execute idempotency, audit query, metrics,
  controlled rollback, preflight, and business isolation.

## Phase 15 E2E Evidence

`services/api/scripts/run_agent_phase15_final_acceptance.py` uses synthetic
`phase15_pg_` rows and the real API Bearer token provider backed by
`agent_users` and `agent_auth_sessions`.

Observed result:

- Proposal: `phase15_pg_proposal`.
- Command: `command-d75e48f0-418d-5e86-8dbd-30dfab7056cd`.
- Execute status: `succeeded`.
- Duplicate execute status: `duplicate`.
- Rollback status: `rolled_back`.
- Action version: `1 -> 3` after execute and rollback.
- Command audit count: 3.
- Metrics totals: execute requests 1, success 1, rollback success 1, failure 0,
  rejected 0, version conflict 0, permission denied 0, whitelist denied 0,
  audit write failure 0, circuit triggers 0.
- Preflight status: `passed`.
- Preflight hard failures: none.
- Business isolation: Requirement unchanged, Risk unchanged, summary unchanged.

The script cleans up synthetic `phase15_pg_` rows and restores Alembic head.

## Security Acceptance

Validated by unit tests, PostgreSQL scripts, and Phase 15 acceptance:

- Bearer token authentication is server-side and backed by hashed
  `agent_auth_sessions` entries.
- Tenant, project, object, operation, and risk scope are enforced server-side.
- High-risk approval remains gated and high/critical execution is outside the
  allowed pilot scope.
- Command execution uses optimistic version checks, row locks, idempotency, and
  same-transaction business update plus audit.
- Rollback checks current version and rejects conflicts.
- Client requests cannot provide trusted permissions, command changes,
  authoritative versions, or idempotency keys.
- Kill switch, pause, and audit-backed circuit breakers reject new execution.
- Defaults keep real execution and grey disabled.

## Stability And Fault Drills

Covered by Phase 12-15 acceptance:

- Concurrent execute succeeds once and duplicate calls return idempotent
  results.
- Service restart idempotency is audit-backed.
- Audit failure and injected DB failure roll back without partial business
  writes.
- Version conflicts and rollback conflicts are rejected.
- Circuit state is recovered from audit after restart.
- Emergency close rejects new execute while still allowing audit queries and
  controlled rollback for already successful Phase 13 pilot commands.

## Preflight

Phase 15 preflight was run with a real Bearer token session and explicit
internal scope:

- Tenant: `tenant-phase15`.
- Project: `project-phase15`.
- User: `phase15_pg_user`.
- Result: `passed`.
- Hard failures: none.

Preflight only reports gate state. It does not enable grey, modify config, or
approve production release.

## Decision

Final decision: `GO`.

This means Agent v1 is allowed to enter internal controlled grey only. It does
not mean production-wide enablement or unrestricted writes.

Default execution, pilot, rollback, and grey switches remain closed:

```text
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
AGENT_COMMAND_PILOT_ENABLED=false
AGENT_ROLLBACK_EXECUTION_ENABLED=false
AGENT_GREY_ENABLED=false
AGENT_GREY_PERCENTAGE=0
AGENT_GREY_PROJECT_DAILY_LIMIT=0
AGENT_GREY_USER_DAILY_LIMIT=0
AGENT_GREY_CONCURRENCY_LIMIT=0
AGENT_GREY_TENANTS=
AGENT_GREY_PROJECTS=
AGENT_GREY_USERS=
```

## Rollback Baseline

Use tag `agent-v1-phase14` as the rollback baseline for Phase 15 documentation
and acceptance script changes. For runtime grey rollback, close the gate with
the kill switch or pause settings first, then run controlled rollback only for
already successful eligible Phase 13 pilot commands.

## Suggested Archive Version

Suggested release candidate version:

```text
Agent v1.0-rc1
```

Suggested archive tag after review and commit:

```text
agent-v1-phase15-final-acceptance
```
