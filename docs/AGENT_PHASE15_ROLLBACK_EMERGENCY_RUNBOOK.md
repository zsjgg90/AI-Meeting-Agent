# Agent Phase 15 Rollback And Emergency Runbook

## Emergency Close

To stop new command execution:

```text
AGENT_GLOBAL_KILL_SWITCH=true
```

For scoped stops:

```text
AGENT_GREY_MANUAL_PAUSED=true
AGENT_PAUSED_TENANTS=<tenant ids>
AGENT_PAUSED_PROJECTS=<project ids>
```

After changing runtime configuration, restart or reload the affected API
process according to the deployment environment.

## What Remains Allowed

Emergency close blocks new execute requests. It does not block:

- `/agent/ops/audits`
- `/agent/ops/metrics`
- `/agent/ops/circuit-breakers`
- Controlled rollback for already successful eligible Phase 13 pilot commands,
  when rollback execution is explicitly enabled and all original permission,
  version, tenant/project, and pilot boundaries still pass.

## Controlled Rollback Steps

1. Query the command and its audits.
2. Confirm the command has a successful Phase 13/14 execution audit.
3. Confirm the target action item version still matches the execution audit.
4. Confirm the reviewer has `rollback_execute`.
5. Run rollback dry-run if needed.
6. Run rollback execute with an explicit confirmation comment.
7. Verify rollback audit and action item version increment.
8. Re-run audit query for the command.

## Hard Stop Conditions

- Audit write failure.
- DB exception.
- Rollback version conflict.
- Tenant/project/user outside whitelist.
- Requirement/Risk/summary write attempt.
- High/critical, cancel, batch, or automatic approval path.

## Rollback Baseline

For code rollback of Phase 15 documentation and acceptance tooling, use:

```text
agent-v1-phase14
```

Do not use force push as part of rollback coordination.
