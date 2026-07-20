# Agent v1.0 Phase 4B Orchestrator Shadow Mode

## Development Goal

Run the Agent Runtime beside the formal meeting analysis path after formal
summary persistence, record Shadow audit output, and keep formal API/database
results unchanged.

## Background

Phase 4A added Worker-internal Tool Registry and Runtime infrastructure. Phase
4B connects that infrastructure as a controlled sidecar only. The Agent result
is not promoted to product output and cannot execute actions.

## Implementation

- Added `services/worker/app/agent_orchestrator.py`.
- Added `AgentOrchestrator` to read meeting scenario policies, create static
  execution plans, call Runtime, preserve step status and `result_source`, and
  generate deterministic comparison summaries.
- Added `AgentShadowAuditStore` and `AgentShadowResult` for file audit output.
- Added `maybe_run_agent_shadow()` and wired it after `save_summary()` in
  `services/worker/app/summary_agent.py`.
- Added `services/worker/tests/test_agent_orchestrator.py`.
- Added the Orchestrator test to `scripts/test-all.ps1`.

## Shadow Audit

Audit files are written under:

```text
data/debug/agent_shadow_trace/<meeting_id>/<agent_run_id>.json
data/debug/agent_shadow_trace/<meeting_id>/latest.json
```

The audit contains run id, meeting id, meeting type, status, timestamps,
duration, step results, result source, shadow analysis, Validator audit,
comparison summary, error, fallback reason, and metadata.

## Static Plan Mapping

- `previous_meetings` or `previous_same_type_meeting` enables
  `search_meeting_history`.
- `project_knowledge` enables `search_project_knowledge`.
- `open_action_items` enables `get_open_action_items`.
- `unknown` uses the minimum plan and records `needs_review=true`.

The fixed order remains:

```text
get_meeting_context
-> search_meeting_history optional
-> search_project_knowledge optional
-> get_open_action_items optional
-> analyze_meeting
-> validate_meeting_analysis
```

## Impact

The formal Qwen3 + RAG result is saved before Agent Shadow starts. Shadow
failures and timeouts are caught and logged. The implementation does not modify
API contracts, database schema, migrations, Prompt, RAG rules, Validator rules,
Expo UI, formal `MeetingSummary`, formal `ActionItem`, project state, or Agent
business-object persistence.

`AGENT_MODE_ENABLED=true` is recorded but ignored in Phase 4B, so Agent output
is not promoted over the formal result. There is still no real meeting
classifier; when no meeting type is available from metadata, the Orchestrator
falls back to the safe `unknown` minimal plan.

## Tests

- `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_orchestrator`
- `.\scripts\test-all.ps1`

## Known Limits

- Phase 4B does not implement Agent result promotion.
- Phase 4B does not execute actions or add human confirmation UI.
- Phase 4B does not persist Agent business objects to PostgreSQL.
- Phase 4B does not perform semantic quality scoring between formal and Shadow
  outputs.
- With `AGENT_SHADOW_MODE=true`, the static plan includes `analyze_meeting`, so
  a real Shadow run may call the existing model analysis path again.

## Follow-Up

Phase 5 should use Shadow audit evidence to implement the first core meeting
scenarios. It must keep action execution disabled until the confirmation and
controlled write-service boundaries are implemented.
