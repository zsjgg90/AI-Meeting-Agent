# Agent Review Auth And Real Proposal Generation

## Goal

Fix the RC1 break where real completed meetings could not surface AI assistant
suggestions because the mobile app had no Agent Bearer session and completed
meeting summaries did not generate persisted review proposals.

## Background

Diagnostics showed `/agent/review/*` and `/agent/action-proposals/*` returned
401 without a Bearer token. The database had no `agent_users` or
`agent_auth_sessions`. Two real completed meetings had summaries and three
ActionItems each, but no AgentActionProposal rows. Phase 15 acceptance used
synthetic `phase15_pg_` data and did not prove real-meeting proposal creation.

## Implementation

- Added fail-closed local Agent login/session support. It creates real
  `agent_users` and `agent_auth_sessions` rows only when local auth is enabled.
- Added Expo Agent session persistence with AsyncStorage. `/agent/*` requests
  receive `Authorization: Bearer <token>` automatically when a valid session is
  cached.
- Added AI assistant page states for loading, unauthenticated, forbidden,
  empty, data, and error. 401 clears the local session and shows a relogin
  action; 403 shows a permission state.
- Added API-side real-meeting ActionItem proposal generation after successful
  summary analysis and a scoped manual diagnostic endpoint for acceptance.
- The generator reads current meeting ActionItems, same tenant/project
  historical ActionItems, and transcript evidence. It generates pending
  proposals only for evidence-backed `owner`, `due_date`, `priority`, or
  `status` changes.

## Boundaries

- Did not modify Prompt, RAG data, Validator, or Shadow.
- Did not expand Requirement, Risk, or Summary controlled-write scope.
- Did not enable real execution or grey controls by default.
- Did not let Expo submit reviewer, tenant, project, role, or permissions.
- Did not create proposals for new objects, ambiguous matches, no-change
  candidates, insufficient evidence, unsupported fields, or duplicates.

## Real Diagnostics

- `6387afc1-1287-4a45-b1e0-a2d33b8ca777`: 3 ActionItems, generated 0.
  Skip reasons: `insufficient_evidence`, `no_historical_match`,
  `ambiguous_match`.
- `5683fa7d-268d-4f2a-ac27-aadcc0df8a42`: 3 ActionItems, generated 0.
  Skip reasons: `no_field_change`, `ambiguous_match`, `no_field_change`.

## Acceptance

Created a deterministic `agent-real-change-` acceptance dataset with a
historical ActionItem owner `前端` and a new completed meeting transcript that
states the owner changed to `后端`. The final proposal was generated through
the API, not directly inserted.

- Proposal: `agent-proposal-5893608a-5b0b-5fc8-931b-6cc73fd59ae3`
- Command: `command-11f0e269-a44c-576c-80ed-13685012cbe2`
- Execute: `succeeded`, `writes_performed=true`
- Duplicate execute: `duplicate`
- Rollback: `rolled_back`, `writes_performed=true`
- Audit count after rollback: 4
- Requirement/Risk counts unchanged during controlled write and rollback.

## Tests

- `npm run typecheck` in `apps/mobile`: passed.
- `node apps/mobile/scripts/test-agent-review-ui.js`: passed.
- `services/api/.venv/Scripts/python.exe -m unittest tests.test_agent_confirmation_api tests.test_api_contract`: passed.
- `.\scripts\test-all.ps1`: passed.
- `services/api/.venv/Scripts/python.exe scripts/run_agent_review_postgres_acceptance.py`: passed.
- `services/api/.venv/Scripts/python.exe scripts/run_agent_phase15_final_acceptance.py`: passed after transient pending proposal state cleared by the first failed run.

## Known Limitations

The local Agent login endpoint is intended for local/manual RC acceptance only
and remains disabled unless explicitly enabled by local environment settings.
Real-meeting proposal generation is deliberately conservative and may return
zero proposals when the transcript does not contain explicit before-to-after
evidence.
