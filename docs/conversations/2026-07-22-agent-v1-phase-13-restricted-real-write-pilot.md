# Agent v1 Phase 13 Restricted Real-Write Pilot

## Development Goal

Execute Agent v1 Phase 13: enable a restricted internal real-write pilot for
low-risk `AgentActionItem` updates with human confirmation, permission and
version checks, same-transaction audit, idempotency, concurrency protection,
and pilot rollback.

## Background

Phase 12 prepared the real-write path with historical action-item scope
backfill, transaction rehearsal, rollback design, and PostgreSQL safety
acceptance, while still rejecting formal business writes. Phase 13 opens only a
small internal pilot and keeps production-wide real writes disabled.

## Implementation

- Added Alembic revision `20260721_0015` with `action_items.version`.
- Switched `AgentActionItem` authoritative versions from `updated_at` to
  `action_items.version`.
- Added fail-closed pilot settings:
  `AGENT_COMMAND_PILOT_ENABLED`,
  `AGENT_COMMAND_PILOT_TENANTS`, and
  `AGENT_COMMAND_PILOT_PROJECTS`.
- Implemented restricted pilot execution in
  `services/api/app/agent_command_executor.py`.
- Added pilot rollback execution for successful Phase 13 commands.
- Added API endpoints:
  - `POST /agent/commands/{command_id}/execute`
  - `POST /agent/commands/{command_id}/rollback/execute`
- Updated the Agent Review workbench to show internal pilot execution,
  tenant/project scope, before/after values, and rollback status without
  letting the client submit changes, permissions, versions, or idempotency
  keys.
- Added unit coverage and PostgreSQL acceptance script
  `services/api/scripts/run_agent_phase13_postgres_acceptance.py`.

## Pilot Contract

Real execution is allowed only when all switches are intentionally opened:

```text
AGENT_COMMAND_EXECUTION_ENABLED=true
AGENT_COMMAND_DRY_RUN_ONLY=false
AGENT_COMMAND_PILOT_ENABLED=true
AGENT_COMMAND_PILOT_TENANTS=<explicit internal tenants>
AGENT_COMMAND_PILOT_PROJECTS=<explicit internal projects>
```

Rollback additionally requires:

```text
AGENT_ROLLBACK_EXECUTION_ENABLED=true
```

The pilot supports only:

- Object: `AgentActionItem`
- Operations: `update`, `complete`
- Fields: `owner`, `due_date`, `priority`, `status`
- Risk: low/medium
- Command state: manually approved and `ready`
- Scope: target action item tenant/project must be in the pilot whitelist

Existing elevated approval checks still apply to operations the security layer
classifies as high-risk, including `complete`.

## Transaction Flow

Execution locks the command and target action item, rereads authoritative state
from the locked row, validates principal permission, tenant/project/object
scope, pilot whitelist, risk, field whitelist, and `expected_version`, applies
the whitelisted changes, increments `action_items.version`, writes execution
audit, marks the command `succeeded`, and commits once.

Injected failures roll back business changes, audit records, and command
status. Repeated or concurrent execution returns the existing success audit and
does not repeat the mutation.

## Rollback Flow

Rollback is limited to Phase 13 succeeded commands. It requires
`rollback_execute`, an independent confirmation comment, the stored rollback
plan, and a current object version matching the execution audit's after-state.
Conflicts are rejected. Successful rollback restores the recorded before
values, increments `action_items.version`, writes rollback audit, marks the
command `rolled_back`, and commits once. Repeated rollback returns the existing
rollback audit.

## Impact

The change affects API Agent command execution, ActionItem authoritative
versioning, Alembic schema, Agent Review UI, tests, PostgreSQL acceptance
tooling, and documentation.

It does not modify Prompt, RAG, Validator, Worker Shadow promotion, formal
Qwen3 + RAG analysis, Requirement/Risk business writes, cancel operations,
automatic approval, batch execution, or production release behavior.

## Tests

Executed during implementation:

```powershell
services\api\.venv\Scripts\python.exe -m compileall -q services\api\app services\api\scripts services\api\alembic\versions
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
cd apps\mobile
npm run typecheck
npm run test:agent-review-ui
```

The PostgreSQL acceptance script was added for final Phase 13 validation:

```powershell
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase13_postgres_acceptance.py
```

## Known Limits

- The pilot is not production-wide real write enablement.
- The minimal `agent_users` / `agent_auth_sessions` auth layer still needs
  integration with the broader product identity or SSO system.
- Requirement and Risk write execution remains unsupported.
- `cancel`, high/critical commands, batch execution, and automatic approval
  remain unsupported.
- Rollback is limited to Phase 13 pilot commands and version-conflict-free
  restores.

## Follow-Up

Before Phase 14, review Phase 13 PostgreSQL acceptance evidence, pilot audit
records, UI clarity, command status semantics, rollback conflict behavior, and
operator controls. Phase 13 is suitable for grey acceptance planning only, not
for direct production-wide real writes.
