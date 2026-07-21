# Agent v1 Phase 12 Real-Write Preparation

## Development Goal

Execute Agent v1 Phase 12: prepare for real writes by adding historical
`action_items` tenant/project backfill support, formal write-contract design,
transaction rehearsal, rollback strategy, and PostgreSQL safety acceptance.
This phase still does not enable real business writes.

## Background

Phase 11 added server-side Bearer token auth, `AgentPrincipal`, first-class
Requirement/Risk tables, and scoped `DatabaseAuthoritativeStateProvider` reads.
Historical `action_items` still had default tenant/project placeholders, and
the real write executor remained a rejecting stub. Phase 12 prepares the data
and transaction design needed before a later limited real-write pilot.

## Implementation

- Added Alembic revision `20260721_0014` with
  `action_item_scope_backfill_audits`.
- Added `services/api/app/action_item_scope_backfill.py`.
- Added transaction rehearsal support in
  `services/api/app/agent_command_executor.py`.
- Added API tests for backfill success, review fallback, idempotency, rollback,
  existing-scope preservation, audit-only transaction rehearsal, and rehearsal
  failure rollback.
- Added PostgreSQL acceptance script
  `services/api/scripts/run_agent_phase12_postgres_acceptance.py`.

## Backfill Strategy

Historical `action_items` are backfilled only when their `summary_id` or
`meeting_id` links to exactly one non-default `(tenant_id, project_id)` pair
from first-class `Requirement` or `Risk` rows. Existing non-default scopes are
preserved and not overwritten. Default `default-tenant` / `default-project`
values are treated as placeholders, not proof. Unverifiable or conflicting rows
enter `review` and keep their existing scope values.

Backfill supports dry-run, persisted audit records, repeat execution
idempotency, source references, reason fields, and rollback of applied scope
updates. It is explicit operator-run tooling and does not automatically act on
production data.

## Write Contract

The designed future write contract supports `Requirement`, `AgentActionItem`,
and `Risk` with `update`, `complete`, `defer`, and `cancel`. Each command must
carry whitelisted field changes, required permission, risk level,
`expected_version`, `idempotency_key`, `confirmation_id`, `audit_context`, and
`rollback_plan`.

The current real executor still rejects execution. Phase 12 only rehearses the
transaction around command locking, authoritative state reread, permission and
version validation, and Agent audit writing.

## Transaction And Rollback

The target transaction order is:

```text
lock command
-> validate ready
-> re-read authoritative state
-> validate permission and expected_version
-> execute business change in a future phase
-> write audit
-> update command status
-> single transaction commit
```

Phase 12 rehearsal skips business mutation and records
`business_writes_performed=false`. Repeated or concurrent rehearsal returns the
existing result through PostgreSQL row locking and stable audit ids. Injected
mid-transaction failures roll back the rehearsal audit.

Rollback remains dry-run/offline only. The design requires rollback to target a
successful command, use the pre-execution authoritative snapshot, validate the
current object version, reject conflicts, require separate confirmation and
permission, and remain auditable and idempotent.

## Impact

The impact is limited to API Agent safety code, Alembic migration, tests,
PostgreSQL acceptance tooling, and documentation. The phase does not modify
Prompt, RAG, Validator, Worker Shadow promotion, Expo UI, or formal Qwen3 + RAG
analysis behavior.

## Tests

Executed and passed:

```powershell
services\api\.venv\Scripts\python.exe -m compileall -q services\api\app services\api\scripts services\api\alembic\versions
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase12_postgres_acceptance.py
```

The Phase 12 PostgreSQL script passed on synthetic `phase12_pg_` data and
covered backfill success/review/idempotency/rollback/existing preservation,
migration rollback, transaction rehearsal rollback, concurrent idempotency,
audit-failure rollback, restart idempotency, rollback conflict rejection,
tenant/project isolation, and unchanged formal business data.

## Known Limits

- Backfill relies on unique first-class Requirement/Risk scope already being
  present. Rows without such evidence require manual review.
- The broader product user/session/SSO system is still not integrated.
- Real write execution and real rollback execution are still unsupported.
- Phase 12 does not implement command status transitions for successful real
  execution because real execution is not enabled.

## Follow-Up

Before Phase 13, review the backfill audit results, finalize lifecycle rules
for Requirement/Risk/ActionItem operations, and decide whether the transaction
rehearsal evidence is sufficient for a limited real-write pilot behind closed
runtime flags. Phase 12 is not sufficient to directly enable production real
writes.
