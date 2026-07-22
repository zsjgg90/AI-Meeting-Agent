# Agent Phase 15 Grey Checklist

Use this checklist before each internal controlled grey window.

## Preconditions

- Branch and artifact under review correspond to the approved Phase 15 commit.
- Alembic current equals head: `20260721_0015`.
- Target tenant, project, and users are explicitly identified.
- Real Bearer token auth provider is active.
- `/agent/ops/preflight` is run for the target scope.
- Preflight returns `passed` with no hard failures.
- Metrics and audit query endpoints are available.
- Kill switch and pause controls are verified.
- Rollback execution is understood and limited to eligible successful pilot
  commands.

## Required Config For A Grey Window

All Phase 13 and Phase 14 gates must be explicit:

```text
AGENT_COMMAND_EXECUTION_ENABLED=true
AGENT_COMMAND_DRY_RUN_ONLY=false
AGENT_COMMAND_PILOT_ENABLED=true
AGENT_COMMAND_PILOT_TENANTS=<internal tenant>
AGENT_COMMAND_PILOT_PROJECTS=<internal project>
AGENT_ROLLBACK_EXECUTION_ENABLED=<operator decision>
AGENT_GREY_ENABLED=true
AGENT_GREY_TENANTS=<internal tenant>
AGENT_GREY_PROJECTS=<internal project>
AGENT_GREY_USERS=<internal users>
AGENT_GREY_PERCENTAGE=<1-100>
AGENT_GREY_PROJECT_DAILY_LIMIT=<positive integer>
AGENT_GREY_USER_DAILY_LIMIT=<positive integer>
AGENT_GREY_CONCURRENCY_LIMIT=<positive integer>
AGENT_GLOBAL_KILL_SWITCH=false
AGENT_GREY_MANUAL_PAUSED=false
```

## During Grey

- Monitor `/agent/ops/metrics`.
- Search `/agent/ops/audits` by tenant/project/user/command.
- Stop on unexpected Requirement/Risk/summary changes.
- Stop on audit write failure, DB exception, elevated version conflict rate, or
  rollback failure.
- Keep new execute traffic within daily and concurrency quotas.

## Exit Criteria

- All command audits have been reviewed.
- No unauthorized scope access is observed.
- No Requirement/Risk/summary JSON writes occurred.
- Rollback evidence is reviewed for any command that required rollback.
- Metrics and non-blocking risks are added to the release review notes.
