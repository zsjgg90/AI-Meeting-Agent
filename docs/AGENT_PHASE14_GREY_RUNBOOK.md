# Agent Phase 14 Grey Runbook

## Scope

Phase 14 hardens the Phase 13 restricted real-write pilot. It does not expand
objects, operations, fields, risk levels, approval behavior, or production
release scope.

Allowed real-write scope remains:

- Object: `AgentActionItem`
- Operations: `update`, `complete`
- Fields: `owner`, `due_date`, `priority`, `status`
- Risk: `low`, `medium`
- State: manually approved persisted command in `ready`

## Default State

Defaults reject real execution:

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
```

Unset tenant/project/user grey lists also reject execution.

## Grey Configuration

To run a controlled internal grey check, all Phase 13 pilot switches and Phase
14 grey switches must be explicitly configured:

```text
AGENT_COMMAND_EXECUTION_ENABLED=true
AGENT_COMMAND_DRY_RUN_ONLY=false
AGENT_COMMAND_PILOT_ENABLED=true
AGENT_COMMAND_PILOT_TENANTS=<tenant ids>
AGENT_COMMAND_PILOT_PROJECTS=<project ids>
AGENT_GREY_ENABLED=true
AGENT_GREY_TENANTS=<tenant ids>
AGENT_GREY_PROJECTS=<project ids>
AGENT_GREY_USERS=<user ids>
AGENT_GREY_PERCENTAGE=<1-100>
AGENT_GREY_PROJECT_DAILY_LIMIT=<positive integer>
AGENT_GREY_USER_DAILY_LIMIT=<positive integer>
AGENT_GREY_CONCURRENCY_LIMIT=<positive integer>
```

Optional UTC window:

```text
AGENT_GREY_WINDOW_START=09:00
AGENT_GREY_WINDOW_END=18:00
```

## Emergency Close

Use these controls to stop new execution:

```text
AGENT_GLOBAL_KILL_SWITCH=true
AGENT_GREY_MANUAL_PAUSED=true
AGENT_PAUSED_TENANTS=<tenant ids>
AGENT_PAUSED_PROJECTS=<project ids>
```

Emergency close rejects new command execution. It still allows audit queries
and controlled rollback of already successful Phase 13 pilot commands when
rollback execution is explicitly enabled.

## Circuit Breakers

Optional audit-backed thresholds:

```text
AGENT_CIRCUIT_CONSECUTIVE_FAILURES=<positive integer>
AGENT_CIRCUIT_VERSION_CONFLICT_RATE=<0.0-1.0>
AGENT_CIRCUIT_ROLLBACK_FAILURES=<positive integer>
AGENT_CIRCUIT_RECOVERED_AFTER=<ISO timestamp>
```

Operators can inspect and reset audit-backed circuit state:

```text
GET /agent/ops/circuit-breakers?tenant_id=<tenant>&project_id=<project>
POST /agent/ops/circuit-breakers/reset
```

Reset writes an Agent audit record and does not change business rows.

## Monitoring And Audit

Internal endpoints:

```text
GET /agent/ops/metrics
GET /agent/ops/audits
GET /agent/ops/preflight
```

Audit search supports command, proposal, object, tenant, project, reviewer,
executor, time, result, operation, limit, and offset filters. Responses are
scoped by the server-side `AgentPrincipal` and redact sensitive keys.

## Preflight

Before any grey run, check:

```text
GET /agent/ops/preflight
```

Any hard failure means do not enter grey. The checker covers safety switches,
whitelists, auth provider source, Alembic current/head, DB connectivity, audit
read/write viability, rollback switch, circuit state, unresolved review data,
and Phase 14 acceptance script availability.

## Verification

Run:

```powershell
.\scripts\test-all.ps1
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase14_postgres_acceptance.py
```

The PostgreSQL script uses synthetic `phase14_pg_` data and cleans it up after
the run.
