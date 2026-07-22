# Agent Phase 15 Release Decision

## Decision

`GO`

Agent v1 may proceed to internal controlled grey with the Phase 13/14 scope and
safety controls. This is not approval for production-wide write enablement.

## Allowed Scope

- Internal test tenant/project/user whitelist.
- `AgentActionItem` only.
- `update` and `complete` only.
- `owner`, `due_date`, `priority`, and `status` only.
- `low` and `medium` risk only.
- Manual approval only.
- Quota, concurrency, preflight, metrics, audit search, circuit breakers,
  tenant/project pause, manual pause, and global kill switch active.

## Decision Evidence

- Full local regression passed.
- Phase 11-14 PostgreSQL acceptance passed.
- Phase 5B full live Qwen3 + RAG Shadow acceptance passed 9/9.
- Real `meeting_001` production analysis diagnostic passed with deterministic
  model settings.
- Phase 15 final API/DB acceptance passed with real Bearer token auth,
  proposal approval, controlled write, audit, rollback, metrics, and preflight.
- Requirement, Risk, and summary JSON stayed unchanged in Phase 13-15 write
  acceptance.
- Defaults keep grey and real execution closed.

## Explicit Non-Approval

This decision does not approve:

- Production-wide grey.
- Requirement writes.
- Risk writes.
- Summary JSON writes.
- `cancel`.
- High or critical command execution.
- Batch execution.
- Automatic approval.
- Prompt, RAG, Validator, or Shadow promotion changes.

## Review Condition Before Actual Grey

Before any real internal grey window, operators must run `/agent/ops/preflight`
with the exact target tenant/project/user scope, inspect metrics and audit
search, confirm kill switch access, and keep rollback execution limited to
eligible successful pilot commands.
