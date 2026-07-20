# Agent v1 Phase 8 Confirmation API

## Development Goal

Build the minimum controlled backend loop for Agent action proposals:

```text
read authoritative state
-> persist AgentActionProposal
-> approve or reject manually
-> generate ControlledWriteCommand
-> persist audit result
```

This phase still does not execute formal business writes.

## Background

Phase 6 produced evidence-backed `AgentActionProposal` objects. Phase 7 defined
offline write-control contracts and `ControlledWritePlanner`. Phase 8 connects
those contracts to API-side persistence and a small approval API while keeping
formal Qwen3 + RAG, Shadow output, and Expo unchanged.

## Implementation

- Added API-side write-control contracts in `services/api/app/agent_write_control.py`.
- Added `DatabaseAuthoritativeStateProvider` in
  `services/api/app/authoritative_state.py`.
- Added confirmation service orchestration in
  `services/api/app/agent_confirmation_service.py`.
- Added `/agent/action-proposals` routes for save, list, detail, approve, and
  reject.
- Added Alembic revision `20260720_0012_agent_confirmation_loop.py`.
- Added offline API tests in `services/api/tests/test_agent_confirmation_api.py`.

## Modified Content

Phase 8 adds four Agent-only persistence tables:

- `agent_action_proposals`
- `agent_proposal_confirmations`
- `controlled_write_commands`
- `agent_audit_records`

`controlled_write_commands.idempotency_key` is unique. Proposals store the
expected object version captured from the authoritative state provider.
Approvals never accept a client-submitted expected version.

The hardened approval path uses a stable idempotency key built from
`proposal_id`, target object type, target object id, operation, and expected
version. It does not include `confirmation_id`. Approval and rejection lock the
proposal row in PostgreSQL and enforce only `pending -> approved`,
`pending -> rejected`, `pending -> expired`, and `pending -> conflict`.
Those destination states are terminal. Approved confirmations are persisted
only after planner success. Planner rejections for conflict, expiry, missing
target, permission, whitelist, evidence, or audit failures do not leave
`decision=approved` confirmations behind.

## Impact

The new API can persist proposals and reviewer decisions and can generate inert
commands. It does not update `action_items`, does not mutate summary JSON,
does not add Requirement or Risk business tables, and does not execute Agent
actions.

## Tests

Executed:

```powershell
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_confirmation_api
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_api_contract services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
```

Both commands passed. Full `.\scripts\test-all.ps1` is the final gate for this
phase and passed after the implementation.

The Phase 8 hardening added tests for stable idempotency keys, terminal state
immutability, duplicate approve/reject no-op behavior, rejected planner results
without approved confirmations, rollback on mid-transaction failure, and
database unique-conflict recovery. PostgreSQL-specific migration and concurrent
approval checks are provided by
`services/api/scripts/run_agent_phase8_postgres_checks.py`.

## Known Limits

- There is no independent production Requirement or Risk table yet.
- Requirement and Risk authoritative snapshots come from existing
  `meeting_summaries` JSON fields and use the owning summary update timestamp
  as the version.
- The API currently uses minimal Agent reviewer headers for this internal route
  because the project has no broader authentication module.
- No command execution service, formal audit UI, rollback executor, or Expo
  confirmation page exists.
- Proposal list/detail evidence and metadata exposure needs a production
  response-shaping pass.
- Requirement and Risk snapshots still scan summary JSON rather than first-class
  state tables.
- API and Worker Agent contracts are duplicated and can drift.
- Foreign-key `ondelete` policy is not finalized for production retention.
- Header reviewer permissions are development-only and are not production
  authentication.

## Follow-Up

Before the next phase, decide the production authorization integration and
whether Requirement and Risk need first-class state tables. Command execution
must remain blocked until rollback transactions, execution auditing, and
operator controls are defined.
