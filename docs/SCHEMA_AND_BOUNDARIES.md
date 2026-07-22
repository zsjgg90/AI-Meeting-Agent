# Schema And Module Boundaries

Last updated: 2026-07-21

## Authoritative Meeting Analysis Schema

The authoritative business schema for six-dimension meeting analysis is:

- `services/worker/app/meeting_analysis_schema.py`

The Worker contract boundary is:

- `services/worker/app/analysis_contract.py`

Formal flow:

```text
LLM raw JSON
-> JSON parse
-> anti hallucination validator
-> normalize_meeting_analysis_result()
-> MeetingAnalysisSchema
-> analysis_to_persistence_payload()
-> MeetingSummary + ActionItem
-> API SummaryRead
-> Expo MeetingSummary type
```

Model raw output must not be written to the database directly.

## Agent Contract Schema

MeetMind Agent v1.0 Phase 1 adds a Worker-internal Agent contract:

- `services/worker/app/agent_contract.py`

Current Agent contract schema version:

```text
agent-contract-v1
```

The Agent contract defines the business objects that later Agent Runtime,
validators, and controlled service conversions may use:

- `Requirement`
- `Decision`
- `AgentActionItem`
- `Issue`
- `Risk`
- `Dependency`
- `Milestone`
- `CustomerRequest`
- `ProjectState`
- `AgentActionProposal`
- `AgentContext`

`AgentActionItem` intentionally uses an Agent-specific class name so it does
not collide with the existing six-dimension action item type or the API/DB
action item read models.

Phase 6 extends `AgentActionProposal` for cross-meeting state proposals while
keeping the original fields backward compatible. The proposal now supports:

- `proposal_id`
- `action_type`
- `target_object_type`
- `target_object_id`
- `proposed_changes`
- `evidence`
- `confidence`
- `risk_level`
- `requires_confirmation`
- `status`
- `reason`
- `metadata`

Supported Phase 6 `action_type` values are `new`, `update`, `complete`,
`defer`, `cancel`, `duplicate`, and `uncertain`.

All Agent business objects use `EvidenceRef` for source evidence. `EvidenceRef`
contains:

- `source_type`
- `source_meeting_id`
- `source_segment_id`
- `source_text`
- `start_time`
- `end_time`
- `speaker`
- `confidence`
- `metadata`

`source_type` is restricted to `transcript`, `meeting_history`,
`project_knowledge`, `manual`, or `unknown`. `confidence` may be `None`, and
when present it must be between `0.0` and `1.0`; the contract does not fabricate
a default confidence score.

`AgentContext` is a per-run context only. It keeps `transcript` and
`meeting_analysis` loosely coupled:

```text
transcript: list[dict[str, Any]]
meeting_analysis: dict[str, Any]
```

`AgentContext.runtime_metadata` always contains:

```json
{"schema_version": "agent-contract-v1"}
```

Callers may add extra metadata, but they cannot override the Agent contract
schema version.

`MeetingType` is defined in `agent_contract.py` and is shared by later Agent
contract layers. Current values are:

- `requirement_review`
- `project_weekly`
- `technical_review`
- `version_planning`
- `cross_department`
- `project_retrospective`
- `management_decision`
- `customer_requirement`
- `unknown`

## Meeting Scenario Policy Schema

MeetMind Agent v1.0 Phase 2 adds a Worker-internal scenario policy layer:

- `services/worker/app/meeting_scenarios/`

Current scenario policy schema version:

```text
meeting-scenario-policy-v1
```

`MeetingScenarioPolicy` is an immutable Pydantic model. It defines:

- `meeting_type`
- `display_name`
- `description`
- `required_context`
- `optional_context`
- `focus_entities`
- `validation_rules`
- `allowed_actions`
- `confirmation_required_actions`
- `classification_hints`
- `needs_review`
- `schema_version`

Allowed context, entity, action, and classification-source values are defined
centrally in `services/worker/app/meeting_scenarios/base.py`. Scenario modules
only declare configuration; they must not call models, databases, RAG, network,
files, or services.

The policy registry is pure in-memory and deterministic:

- `get_policy(meeting_type)`
- `list_policies()`
- `has_policy(meeting_type)`

`unknown` has a safe default policy. It requires no historical context, uses a
minimal allowed action set, requires review, does not allow high-risk actions
such as `update_project_health`, and must not be used by later Runtime code to
automatically modify project state.

`MeetingClassificationResult` defines the future classification result
contract only. It reuses `EvidenceRef`; it does not implement manual override,
rule classification, model classification, or fallback logic in Phase 2.

## Agent Tool Adapter Contracts

MeetMind Agent v1.0 Phase 3 adds Worker-internal thin adapters:

- `services/worker/app/agent_tools/`

The first completed tools are:

- `get_meeting_context`
- `search_meeting_history`
- `search_project_knowledge`
- `get_open_action_items`
- `analyze_meeting`
- `validate_meeting_analysis`

Tool contracts are defined in `services/worker/app/agent_tools/base.py`:

- `AgentTool`
- `ToolExecutionContext`
- `ToolResult`
- `ToolError`
- `ToolPolicy`
- `ToolStatus`

`ToolStatus` is restricted to `success`, `failed`, `timeout`, `skipped`, or
`fallback`. `ToolResult` always records `tool_name`, `status`, `data`, `error`,
`duration_ms`, `result_source`, `retryable`, and `metadata`.

The first six tools are read-only from the Agent contract perspective:

```text
read_only = true
has_side_effects = false
requires_confirmation = false
```

`analyze_meeting` may call the existing model/RAG analysis service, but it must
not call `summarize_meeting()` or `save_summary()` and must not write database
state. `validate_meeting_analysis` wraps the existing validator with audit and
does not change validator rules.

`get_project_context` and `get_active_risks` are intentionally deferred because
there is no authoritative Project table, persisted `ProjectState`, or
independent risk state model. Later phases may add them only after a formal
state source and persistence boundary exist.

## Agent Runtime Contracts

MeetMind Agent v1.0 Phase 4A adds Worker-internal controlled runtime
infrastructure:

- `services/worker/app/agent_runtime/registry.py`
- `services/worker/app/agent_runtime/runtime.py`

`ToolRegistry` owns in-memory registration for the six Phase 3 tools:

- `get_meeting_context`
- `search_meeting_history`
- `search_project_knowledge`
- `get_open_action_items`
- `analyze_meeting`
- `validate_meeting_analysis`

The registry supports registration, lookup by name, listing, duplicate
registration rejection, unknown-tool rejection, and ToolPolicy boundary checks.
Phase 4A rejects side-effecting or confirmation-required tools. Creating or
importing the registry does not open database sessions, initialize RAG/Chroma,
load models, or call the network. The default registry factory receives
providers/factories and passes them through to the existing Tool Adapters.

`AgentRuntime` accepts an `AgentContext` plus a caller-supplied static
`ExecutionPlan`. It creates an in-memory `AgentRunState`, converts the context
to `ToolExecutionContext`, executes enabled steps in order, records
`AgentStepResult` entries, preserves `ToolResult.status` and `result_source`,
and stops or continues based on each step's `continue_on_failure` flag.
Optional steps are skipped only when the plan disables them; the model does not
choose tools or modify the plan.
`create_default_execution_plan()` provides the fixed Phase 4A sequence:
`get_meeting_context` -> optional `search_meeting_history` -> optional
`search_project_knowledge` -> optional `get_open_action_items` ->
`analyze_meeting` -> `validate_meeting_analysis`.

Runtime contract objects:

- `ExecutionStep`
- `ExecutionPlan`
- `AgentStepResult`
- `AgentRunState`
- `AgentRuntime`
- `create_default_execution_plan()`

Phase 4A does not implement Shadow Mode, Orchestrator integration, model free
planning, multi-Agent execution, write-path tools, action execution, project
state mutation, real meeting classification, or formal-chain integration.

## Agent Orchestrator Shadow Mode

MeetMind Agent v1.0 Phase 4B adds a controlled Worker-internal Orchestrator:

- `services/worker/app/agent_orchestrator.py`

`AgentOrchestrator` reads the meeting scenario policy, converts policy context
requirements into a static `ExecutionPlan`, calls the Phase 4A Runtime, creates
a deterministic comparison summary, and writes a file audit result. It does not
modify API responses, database schemas, migrations, Prompt, RAG rules,
Validator rules, Expo UI, or the formal six-dimension persistence payload.

Agent Shadow audit files are written to:

```text
data/debug/agent_shadow_trace/<meeting_id>/<agent_run_id>.json
data/debug/agent_shadow_trace/<meeting_id>/latest.json
```

Shadow audit fields include:

- `agent_run_id`
- `meeting_id`
- `meeting_type`
- `status`
- `started_at`
- `finished_at`
- `duration_ms`
- `steps`
- `result_source`
- `shadow_analysis`
- `validation_audit`
- `comparison_summary`
- `error`
- `fallback_reason`
- `metadata`

Static plan mapping:

- `previous_meetings` or `previous_same_type_meeting` enables
  `search_meeting_history`.
- `project_knowledge` enables `search_project_knowledge`.
- `open_action_items` enables `get_open_action_items`.
- `unknown` disables all optional context steps and records
  `needs_review=true`.

`comparison_summary` is deterministic only. It compares six-dimension field
presence, item counts, schema field availability, Validator warning count, and
formal-vs-shadow `result_source`. It does not perform semantic quality scoring
and does not ask a model to compare results.

## Agent Cross-Meeting State Tracker

MeetMind Agent v1.0 Phase 6 adds a Worker-internal cross-meeting state module:

- `services/worker/app/agent_state_tracker.py`

Current tracker schema version:

```text
agent-state-tracker-v1
```

The tracker supports only the first three core Agent objects:

- `Requirement`
- `AgentActionItem`
- `Risk`

It performs bounded in-memory processing:

```text
current Agent objects + supplied historical candidates
-> historical candidate reader
-> object normalization
-> deterministic candidate matching
-> state-change classification
-> AgentActionProposal generation
-> proposal validation and confirmation flags
```

The deterministic matching rules use object type, `project_id`, normalized
title, keywords, owner, source meeting, and current status. String similarity is
used only as an auxiliary score for already bounded candidates. The tracker does
not freely scan databases, does not initialize RAG or Qwen, and does not execute
or persist proposals.

Human confirmation is required for owner changes, due-date changes,
requirement cancellation, closing high-risk items, formal status changes,
`uncertain` matches, insufficient evidence, and historical fact conflicts.

## Agent Write Control Contracts

MeetMind Agent v1.0 Phase 7 adds Worker-internal write-control contracts:

- `services/worker/app/agent_write_control.py`

Current write-control schema version:

```text
agent-write-control-v1
```

The Phase 7 flow is offline and non-executing:

```text
AgentActionProposal
-> AuthoritativeStateProvider.get_state(object_type, object_id)
-> AgentProposalConfirmation validation
-> ControlledWriteCommand generation
-> AuditRecord + RollbackPlan
```

`AuthoritativeStateProvider` is a read-only interface. It returns only the
specified bounded object as an `AuthoritativeStateSnapshot` with object type,
object id, current version, status, updated timestamp, source, data, and
metadata. The included `InMemoryAuthoritativeStateProvider` is for offline tests
and fixtures only; it does not scan databases.

`AgentProposalConfirmation` records:

- `confirmation_id`
- `proposal_id`
- `decision`
- `reviewer`
- `reviewed_at`
- `comment`
- `expected_object_version`
- `permissions`
- `metadata`

`ControlledWriteCommand` records:

- `command_id`
- `proposal_id`
- `target_object_type`
- `target_object_id`
- `operation`
- `expected_version`
- `changes`
- `idempotency_key`
- `confirmation_id`
- `audit_context`
- `status`

The planner refuses to generate a ready command when confirmation is missing,
rejected, expired, or needs changes; when the authoritative object is missing;
when the current version differs from the confirmed expected version; when
permissions are insufficient; when a field is outside the object whitelist; when
the idempotency key has already been seen; or when proposal evidence or audit
context is missing. High-risk operations require explicit approved
confirmation. Generated commands remain inert and carry `writes_performed=false`.

## Agent Phase 8 Confirmation API Boundary

MeetMind Agent v1.0 Phase 8 adds the minimum API-side confirmation loop:

- `services/api/app/authoritative_state.py`
- `services/api/app/agent_write_control.py`
- `services/api/app/agent_confirmation_service.py`
- `services/api/app/routers/agent_proposals.py`
- Alembic revision `20260720_0012`

The production `DatabaseAuthoritativeStateProvider` is read-only and returns
`AuthoritativeStateSnapshot` for one requested bounded object. It reads:

- `AgentActionItem` from the existing `action_items` table.
- `Requirement` from existing `meeting_summaries` JSON fields such as
  `meeting_agenda`.
- `Risk` from existing `meeting_summaries.risks_and_focus` or `risks` JSON.

There is still no independent production Requirement or Risk authoritative
business table. Requirement and Risk versions are therefore the owning
`meeting_summaries.updated_at` timestamp, while ActionItem versions are
`action_items.updated_at`.

Phase 8 persists only the confirmation loop:

- `agent_action_proposals`
- `agent_proposal_confirmations`
- `controlled_write_commands`
- `agent_audit_records`

`ControlledWriteCommand` is still an inert command record and does not
represent a formal state change. Approval must go through
`ControlledWritePlanner`; the API must not accept client-submitted commands or
client-submitted expected versions. Missing confirmation, insufficient
permissions, version conflicts, expired proposals, non-whitelisted fields,
missing evidence, missing audit context, duplicate idempotency keys, and missing
target objects are rejected. Version conflicts mark proposals as `conflict` and
write audit records without creating a ready command.

Approval and rejection lock the proposal row with `SELECT ... FOR UPDATE` on
PostgreSQL so confirmations for the same proposal are serialized. The only
allowed terminal transitions are `pending -> approved`, `pending -> rejected`,
`pending -> expired`, and `pending -> conflict`; terminal proposals cannot be
approved or rejected again. Repeated approval returns the existing ready command
and does not create another confirmation or audit record. Approved
confirmations are persisted only after `ControlledWritePlanner` returns a ready
command. The command idempotency key is generated from stable business fields:
proposal id, target object type, target object id, operation, and expected
version.

## Agent Phase 9 Dry-Run Command Sandbox

MeetMind Agent v1.0 Phase 9 adds the minimum execution sandbox while keeping
formal business writes disabled:

- `services/api/app/agent_command_executor.py`
- `services/api/app/routers/agent_commands.py`
- `apps/mobile/src/screens/AIAssistantScreen.tsx`

The API command routes are limited to reading persisted commands, running
dry-run validation, and reading command audit records:

- `GET /agent/commands`
- `GET /agent/commands/{command_id}`
- `POST /agent/commands/{command_id}/dry-run`
- `GET /agent/commands/{command_id}/audits`

The dry-run executor accepts only a persisted command id. It does not accept
client-submitted `ControlledWriteCommand`, `expected_version`, changes,
permissions in the request body, or idempotency keys. The executor re-reads the
current authoritative state through `DatabaseAuthoritativeStateProvider`,
validates command `ready` status, server-side reviewer authorization,
optimistic version, command idempotency key, target existence, and non-empty
changes, then writes an `agent_audit_records` dry-run audit with:

```json
{
  "dry_run": true,
  "writes_performed": false,
  "expected_changes": {},
  "rollback_preview": {},
  "authoritative_state": {}
}
```

Repeated successful dry-runs return the existing dry-run audit as a duplicate
result and do not create duplicate dry-run audit records. Rejected dry-runs
write rejected audit records only. Phase 9 does not update `action_items`,
`meeting_summaries`, Requirement, Risk, Shadow output, Prompt, RAG, or
Validator behavior.

Runtime guardrails are:

```text
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
```

`AGENT_COMMAND_EXECUTION_ENABLED=false` rejects command dry-run by default.
`AGENT_COMMAND_DRY_RUN_ONLY=true` keeps real writes unsupported even when dry
run is explicitly enabled for tests or local diagnostics.

## Agent Phase 10 Auth, Permission, And Rollback Safety

MeetMind Agent v1.0 Phase 10 adds the pre-real-write safety layer while keeping
all formal business writes disabled:

- `services/api/app/agent_security.py`
- `services/api/app/agent_command_executor.py`
- `services/api/app/routers/agent_proposals.py`
- `services/api/app/routers/agent_commands.py`
- `services/api/scripts/run_agent_phase10_security_acceptance.py`

Agent APIs must not trust client-submitted `X-Agent-Reviewer` or
`X-Agent-Permissions`. Expo no longer sends those headers. The API obtains an
`AgentPrincipal` from the server-side authentication adapter. Because the
project has no complete production auth/session/JWT implementation yet, the
default adapter fails closed with HTTP 401. Unit tests and PostgreSQL safety
checks inject test principals with FastAPI dependency overrides; this is not a
production authentication implementation.

Phase 10 permission scopes are:

- `proposal_view`
- `proposal_review`
- `command_dry_run`
- `command_execute`
- `audit_view`
- `rollback_execute`

Every Agent authorization check must validate user identity, project scope,
object scope, operation type, and risk level. High-risk actions, including
`high`/`critical` risk levels and high-risk operations such as cancel/complete,
require an elevated role (`agent_admin` or `agent_high_risk_approver`) or the
`high_risk_approve` permission. A regular reviewer must not approve high-risk
commands alone.

Rollback execution is still dry-run only. The rollback dry-run endpoint is:

```text
POST /agent/commands/{command_id}/rollback/dry-run
```

It accepts only a persisted command id. It checks the original command and
audit, requires an existing original dry-run audit, re-reads authoritative
state, validates the current object version, generates a rollback command
preview, writes an audit record, and preserves `writes_performed=false`.
Repeated rollback dry-run returns the existing rollback audit as a duplicate
result. Rollback conflicts are rejected and audited; no formal
Requirement/ActionItem/Risk state is modified.

The future real-write executor contract is present only as a rejecting stub.
Before any later phase can enable it, implementation must prove:

- authoritative state is re-read immediately before write;
- `expected_version` optimistic lock is checked;
- command status is `ready`;
- idempotency key recovery is deterministic after process restart;
- all formal writes and audit writes happen in one database transaction;
- mid-transaction failures and audit failures roll back completely;
- successful execution transitions command state only after the audit is
  durable;
- rollback execution is separately permissioned and audited.

Runtime guardrails are:

```text
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
AGENT_ROLLBACK_EXECUTION_ENABLED=false
```

Unset or default configuration must reject real command execution and real
rollback execution. Test environments must not enable formal business writes.
Changing environment variables must not bypass the unimplemented real write
executor or real rollback executor; both executors remain unsupported until a
later phase implements and verifies them.

## Agent Phase 11 Production Auth And Authoritative State

MeetMind Agent v1.0 Phase 11 adds the minimum production identity and
first-class authoritative-state foundation while keeping all formal business
writes disabled:

- `services/api/app/agent_security.py`
- `services/api/app/authoritative_state.py`
- `services/api/app/models.py`
- Alembic revision `20260721_0013`
- `services/api/scripts/run_agent_phase11_postgres_acceptance.py`

The production Agent authentication path accepts only
`Authorization: Bearer <token>`. The API hashes the token, reads
`agent_auth_sessions`, rejects missing/unknown/expired/revoked sessions with
401, joins `agent_users`, rejects inactive users with 401, and builds
`AgentPrincipal` from server-side fields only:

- `user_id`
- `tenant_id`
- `roles`
- `permissions`
- `project_scope`
- `object_scope`
- `authentication_source`

Tests may still use FastAPI dependency overrides, but production code no longer
uses client-submitted reviewer or permission headers.

Phase 11 formalizes first-class state sources:

- `requirements`
- existing `action_items`
- `risks`

`requirements` and `risks` contain `id`, `tenant_id`, `project_id`, `title`,
`description`, `status`, `owner`, `due_date`, `priority`, `version`,
`source_meeting_id`, source JSON reference fields, `source_ref`, and timestamps.
`risks` also keeps risk-specific fields such as `level`, `category`, `impact`,
`probability`, and `mitigation`. Existing `action_items` gain `tenant_id` and
`project_id` columns for scoped reads.

Migration copies Requirement/Risk candidates from existing summary JSON into
the formal tables, defaults incomplete candidates to `review`, records source
meeting/summary/field/index and raw source reference, does not delete or mutate
the original summary JSON, and uses source-reference uniqueness to avoid
duplicate migration. Downgrade removes the Phase 11 tables and action scope
columns.

`DatabaseAuthoritativeStateProvider` now returns:

- `Requirement` from `postgresql.requirements`
- `AgentActionItem` from `postgresql.action_items`
- `Risk` from `postgresql.risks`

It no longer scans `meeting_summaries` JSON as the formal authoritative source.
Every Agent API state read passes a server-side principal into the provider and
validates tenant, project, object type, object id, and operation permission.
Provider reads remain read-only and return `writes_performed=false`.

## Agent Phase 12 Real-Write Preparation

MeetMind Agent v1.0 Phase 12 prepares for future real writes while keeping real
business mutation disabled:

- `services/api/app/action_item_scope_backfill.py`
- `services/api/app/agent_command_executor.py`
- Alembic revision `20260721_0014`
- `services/api/scripts/run_agent_phase12_postgres_acceptance.py`

Phase 12 adds `action_item_scope_backfill_audits` to support historical
`action_items` tenant/project backfill. Backfill rules are fail-closed:

- Existing non-default `tenant_id` and `project_id` are treated as valid and
  are not overwritten.
- Default `default-tenant` / `default-project` values are placeholders, not
  verifiable production scope.
- A row is backfilled only when related first-class `Requirement` or `Risk`
  records for the same `summary_id` or `meeting_id` produce exactly one
  non-default `(tenant_id, project_id)` pair.
- No unique verifiable pair, or multiple conflicting pairs, records `review`
  and leaves `action_items.tenant_id/project_id` unchanged.
- Every dry-run, applied row, skipped valid row, review row, and rollback is
  recorded with source references and reasons.

The future real-write contract is explicit but not enabled. Supported object
types are `Requirement`, `AgentActionItem`, and `Risk`; allowed operations are
`update`, `complete`, `defer`, and `cancel`. Commands must carry a field
whitelist-valid change set, required permission, risk level,
`expected_version`, `idempotency_key`, `confirmation_id`, `audit_context`, and
`rollback_plan`.

The designed transaction order is:

```text
lock command
-> validate ready
-> re-read authoritative state
-> validate permission and expected_version
-> execute business change in a future phase
-> write audit
-> update command state
-> single transaction commit
```

Phase 12 rehearsal follows that order through the validation and audit steps
but skips business mutation. It writes only `agent_audit_records` with
`transaction_rehearsal=true`, `writes_performed=false`, and
`business_writes_performed=false`. PostgreSQL row locks and stable audit ids
make repeated or concurrent rehearsal idempotent. A failed audit or injected
mid-transaction exception rolls back the rehearsal record.

Rollback remains dry-run/offline only. The design requires rollback to target a
previously successful command, use the pre-execution authoritative snapshot,
validate the current object version, reject conflicts instead of automatic
rollback, require independent confirmation and permission, and be auditable and
idempotent. Real rollback execution is still unsupported.

## Agent Phase 13 Restricted Real-Write Pilot

MeetMind Agent v1.0 Phase 13 opens a restricted real-write pilot for internal
test tenant/project scopes only:

- Alembic revision `20260721_0015` adds `action_items.version`.
- `AgentActionItem` authoritative snapshots now use `action_items.version` as
  `object_version`; `updated_at` remains a timestamp only.
- Runtime switches remain fail-closed by default:

```text
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
AGENT_COMMAND_PILOT_ENABLED=false
AGENT_COMMAND_PILOT_TENANTS=
AGENT_COMMAND_PILOT_PROJECTS=
AGENT_ROLLBACK_EXECUTION_ENABLED=false
```

The executor permits real writes only when execution is enabled, dry-run-only
is disabled, pilot mode is enabled, the locked `ActionItem` tenant/project is
whitelisted, and the command is inside the Phase 13 pilot contract. The pilot
contract is intentionally small:

- Object type: `AgentActionItem`.
- Operations: `update`, `complete`.
- Fields: `owner`, `due_date`, `priority`, `status`.
- Risk: low/medium only. Existing elevated approval checks still apply where
  the security layer treats an operation, such as `complete`, as high-risk.
- Command state: persisted, manually approved, and `ready`.

Execution transaction order:

```text
lock command
-> lock target action item
-> re-read authoritative state from the locked row
-> validate tenant/project/object scope, permission, pilot whitelist, risk, fields, expected_version
-> update whitelisted business fields
-> increment action_items.version
-> write execution audit
-> mark command succeeded
-> single PostgreSQL transaction commit
```

Any exception rolls back the business update, audit, and command status change.
Repeated execution or service restart after success returns the existing
execution audit as a duplicate result. PostgreSQL row locks ensure concurrent
execution can produce at most one successful business mutation.

Pilot rollback execution is limited to successful Phase 13 pilot commands. It
requires a separate confirmation action, `rollback_execute`, the same
tenant/project pilot whitelist, the execution audit's after-version, and the
stored rollback plan. On success it restores recorded before values, increments
`action_items.version`, writes rollback audit, and marks the command
`rolled_back` in one transaction. If the current object version has changed,
rollback is rejected and no automatic rollback is attempted.

Phase 13 still does not allow Requirement/Risk writes, `cancel`, high/critical
commands, non-whitelisted tenant/project writes, automatic approval, batch
execution, Prompt/RAG/Validator changes, Shadow promotion, or production-wide
release.

## Agent Phase 14 Grey Safety And Operations

MeetMind Agent v1.0 Phase 14 adds production safety guardrails and operational
read APIs around the Phase 13 restricted pilot:

- `services/api/app/agent_phase14_guardrails.py`
- `services/api/app/routers/agent_ops.py`
- `services/api/scripts/run_agent_phase14_postgres_acceptance.py`

Phase 14 does not add a database migration. It uses existing command,
proposal, action item, and Agent audit tables. Real execution must pass both
the Phase 13 pilot contract and the Phase 14 grey guardrails. Defaults remain
closed:

```text
AGENT_GLOBAL_KILL_SWITCH=false
AGENT_GREY_ENABLED=false
AGENT_GREY_TENANTS=
AGENT_GREY_PROJECTS=
AGENT_GREY_USERS=
AGENT_GREY_PERCENTAGE=0
AGENT_GREY_PROJECT_DAILY_LIMIT=0
AGENT_GREY_USER_DAILY_LIMIT=0
AGENT_GREY_CONCURRENCY_LIMIT=0
```

The grey gate requires explicit tenant/project/user whitelists, a non-zero
percentage, non-zero per-project and per-user daily limits, a non-zero
concurrency limit, and an open UTC time window when configured. It also
supports global kill switch, manual pause, tenant/project pause lists,
consecutive-failure circuit breaking, version-conflict-rate circuit breaking,
rollback-failure circuit breaking, and audit-backed manual circuit reset.

New API operations are operational only:

- `GET /agent/ops/metrics`
- `GET /agent/ops/audits`
- `GET /agent/ops/circuit-breakers`
- `POST /agent/ops/circuit-breakers/reset`
- `GET /agent/ops/preflight`

Audit search is scoped by the server-side `AgentPrincipal` and redacts
sensitive keys such as tokens, passwords, secrets, and API keys. Emergency
close rejects new command execution but does not block audit queries or
controlled rollback of already successful Phase 13 pilot commands.

Phase 14 still does not allow Requirement/Risk writes, summary JSON writes,
`cancel`, high/critical commands, batch execution, automatic approval,
Prompt/RAG/Validator changes, Shadow promotion, grey enablement by default, or
production-wide release.

## Schema Version

Current schema version:

```text
meeting-analysis-v1
```

The version is exposed to API consumers through:

```text
GET /meetings/{meeting_id}/summary
metadata.schema_version
```

## Six-Dimension Mapping

| Dimension | Canonical field | DB compatibility | API field | Frontend field |
| --- | --- | --- | --- | --- |
| Meeting agenda | `meeting_agenda` | `meeting_agenda`, legacy `agenda` | `meeting_agenda`, `agenda` | `meeting_agenda`, `agenda` |
| Meeting summary | `meeting_summary` | `meeting_summary`, legacy `overview` | `meeting_summary`, `overview`, `summary` | `meeting_summary`, `overview`, `summary` |
| Key conclusions | `key_conclusions` | `key_conclusions`, legacy `decisions` | `key_conclusions`, `decisions` | `key_conclusions`, `decisions` |
| Action items | `action_items` | `action_items` table | `action_items` | `action_items` |
| Unresolved issues | `unresolved_issues` | `unresolved_issues`, legacy `open_questions` | `unresolved_issues`, `open_questions` | `unresolved_issues`, `open_questions` |
| Risks and focus | `risks_and_focus` | `risks_and_focus`, legacy `risks` | `risks_and_focus`, `risks` | `risks_and_focus`, `risks` |

Legacy fields remain for backward compatibility. New code should prefer canonical fields.

## Module Boundaries

| Layer | Owns | Must not own |
| --- | --- | --- |
| Expo | UI, user interaction, API calls, view model fallback | Worker/Ollama/Chroma access, raw LLM parsing |
| API | HTTP contracts, validation, upload coordination, task submission, read models | ASR, RAG, model calls, business analysis |
| Worker | ASR, diarization, transcript building, AI analysis orchestration, validation, persistence mapping | Mobile UI, public HTTP contracts |
| RAG Retriever | Retrieval only | Prompt business definitions, persistence |
| Ollama Client | Model transport only | Schema normalization, validation, persistence |
| Validator | Evidence and boundary validation | Database writes, API response shaping |
| Semantic Analysis Pipeline | Worker-side orchestration from transcript rows to existing six-dimension result dict | Database writes, API response shaping, direct persistence of internal event/topic schemas |
| Topic Event Aggregator | Grouping of validated `SemanticEvent` rows into `TopicEventGroup` | LLM calls, database writes, API response shaping |
| Six Dimension Mapper | Rule mapping from `TopicEventGroup` into `SixDimensionResult` | LLM calls, database writes, API response shaping |
| Six Dimension Validator | Quality control for `SixDimensionResult` evidence, status, and duplicates | LLM calls, database writes, API response shaping |
| Agent Contract | Worker-internal Agent v1 business objects and per-run `AgentContext` validation | API contracts, database writes, raw LLM persistence, Agent runtime orchestration, tool execution |
| Meeting Scenario Policy | Worker-internal read-only meeting type policies and classification result contract | Real classification, model calls, database/RAG/network access, Agent runtime orchestration, tool execution |
| Agent Tool Adapter | Thin wrappers around existing read services, RAG retrieval, model analysis, and validation with structured results | Tool Registry, Agent Runtime, database writes, action execution, project state mutation, duplicated business logic |
| Agent Runtime | Worker-internal Tool Registry, static execution plans, in-memory Agent run state, step/result recording | Formal analysis entry wiring, Shadow Mode, Orchestrator, model free planning, multi-Agent execution, database writes, action execution |
| Agent Orchestrator | Worker-internal Shadow Mode orchestration, scenario-to-plan mapping, file audit output, deterministic formal-vs-shadow comparison | API response changes, formal result overwrite, database writes, action execution, model free planning, semantic scoring |
| Agent State Tracker | Worker-internal cross-meeting candidate normalization, deterministic matching, state-change classification, and proposal generation | Database writes, write-path Tools, API contracts, Prompt/RAG/Validator changes, action execution, free database scanning |
| Agent Write Control | Worker-internal authoritative-state read contract, confirmation validation, inert command generation, audit records, rollback plans, idempotency and permission checks | Database writes, write-path Tools, API contracts, Expo confirmation UI, automatic approval, action execution |
| Agent Confirmation API | API-side proposal persistence, read-only authoritative snapshots, manual approve/reject decisions, inert command persistence, server-side principal authorization, and audit records | Client-submitted permissions, client-submitted commands, formal Requirement/ActionItem/Risk writes, Prompt/RAG/Validator changes, Shadow promotion, automatic approval |
| Agent Command Sandbox | API-side dry-run validation for persisted ready commands, expected-change preview, rollback dry-run preview, server-side principal authorization, and dry-run audit records | Formal Requirement/ActionItem/Risk writes, client-submitted commands or versions, automatic approval, real rollback execution, Prompt/RAG/Validator changes |
| Repository/persistence mapping | DB-compatible payload and rows | Prompt building, model calls |

## Compatibility Strategy

- No database migration is required for Phase 4.
- Existing DB fields are kept.
- API keeps legacy response aliases to avoid breaking existing Expo screens.
- `metadata.schema_version` is added as a non-breaking field.
- Formal Qwen3 + RAG results now pass through `MeetingAnalysisSchema` before persistence.
- Semantic pipeline results pass through `MeetingAnalysisSchema` before persistence.
- `SemanticEvent`, `TopicEventGroup`, `SixDimensionResult`, and validation flags remain internal Worker-side structures; introducing API or persistence output for them requires a separate contract change.
- `Requirement`, `Decision`, `AgentActionItem`, `Issue`, `Risk`, `Dependency`,
  `Milestone`, `CustomerRequest`, `ProjectState`, `AgentActionProposal`, and
  `AgentContext` are internal Agent contract objects in Phase 1. They are not
  persisted to PostgreSQL, exposed through the API, or used to replace
  `MeetingAnalysisSchema`.
- Raw LLM output must not directly become formal Agent business objects. Later
  phases must use controlled conversion and validation before any state update.
- Meeting scenario policies and `MeetingClassificationResult` are internal
  Agent v1 Phase 2 contracts. They are not persisted, exposed through the API,
  or connected to the formal analysis chain.
- Agent Tool adapters are internal Phase 3 wrappers. Importing them must not
  open DB sessions, instantiate RAG/embedding/model clients, access Chroma, or
  call the network. They are not exposed through the API and are not wired into
  the formal analysis chain.
- Agent Runtime infrastructure is internal Phase 4A scaffolding. Importing it
  must not access databases, RAG, models, files, or networks. It is not exposed
  through the API, not connected to the formal analysis chain, and not enabled
  by Agent rollout switches until a later phase explicitly wires it in.
- Agent Orchestrator Shadow Mode is internal Phase 4B sidecar execution. It runs
  only after formal summary persistence when `AGENT_SHADOW_MODE=true`; when the
  switch is false it does not run. Its audit files must not be treated as
  formal API or database output. Agent failures, timeouts, and fallback statuses
  must not trigger formal-chain retries or overwrite formal results.
- Agent State Tracker is internal Phase 6 scaffolding. It returns
  `AgentActionProposal` objects only and records `writes_performed=false`; it is
  not exposed through the API, not persisted to PostgreSQL, and not wired into a
  confirmation or execution flow.
- Agent Write Control is internal Phase 7 scaffolding. It can generate
  `ControlledWriteCommand` objects only after approved confirmation,
  authoritative state re-read, version check, permission check, whitelist check,
  idempotency check, evidence check, and audit check. It does not execute those
  commands, does not write PostgreSQL, and is not exposed through API or Expo.
- Agent Phase 8 exposes a minimum confirmation API and persists proposals,
  confirmations, inert commands, and audit records. It does not execute
  commands, does not write formal business state, does not add Expo UI, does
  not modify the formal Qwen3 + RAG or Shadow result-promotion behavior, and
  does not implement automatic approval.
- Agent Phase 9 exposes a minimum Expo confirmation workbench and API dry-run
  sandbox for persisted ready commands. It writes dry-run audit records only,
  does not execute real business writes, does not accept client-submitted
  commands or versions, and does not implement automatic approval or rollback
  execution.
- Qwen3 + RAG analysis remains the fallback path and must log `fallback_reason` when used after semantic pipeline failure.

## Known Remaining Risks

- API and Worker still define duplicate SQLAlchemy models and must remain manually synchronized.
- Legacy OpenAI/rule-based code remains in `summary_agent.py`; current formal path is isolated but the file is still large.
- Prompt/RAG version management is documented in `docs/PROMPT_AND_RAG_VERSIONING.md`; persisted metadata is available after migration `20260715_0011`.
