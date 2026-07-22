# Agent Phase 15 Risks And Open Items

## Non-Blocking Risks

- The minimal Agent Bearer token provider is suitable for internal grey
  acceptance, but still needs integration review with the broader product
  identity/session system before wider exposure.
- Metrics are internal API aggregates only and are not connected to an external
  monitoring or alerting platform.
- Phase 5B quality scoring is rule-assisted and still marks manual review as
  required.
- RAG retrieval in the Phase 5B fixture set repeatedly selects the same eight
  chunks; this is acceptable for the current gate but should be reviewed before
  broader scenario expansion.
- API and Worker still maintain duplicated Agent contract shapes, creating a
  drift risk.
- Production-scale historical `action_items` tenant/project backfill still
  requires operator review before broad use.

## Blocking Items For Production-Wide Enablement

- No approval for Requirement/Risk writes.
- No approval for high/critical risk execution.
- No approval for batch execution or automatic approval.
- No external monitoring integration.
- No production-wide grey scope.
- No final broader identity integration review.

These are not blockers for internal controlled grey under the Phase 13/14
scope.

## Operational Watch Items

- Watch execute rejection counts, version conflicts, rollback failures, audit
  write failures, and circuit trigger counts during grey.
- Keep `AGENT_GLOBAL_KILL_SWITCH` and pause controls immediately available.
- Treat any audit write failure or DB exception as a stop condition.
- Preserve ignored debug and acceptance artifacts for post-run review, but do
  not commit them.
