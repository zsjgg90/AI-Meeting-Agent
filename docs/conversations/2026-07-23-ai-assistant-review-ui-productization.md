# AI Assistant Review UI Productization

## Development Goal

Productize the Expo AI assistant review surface according to the supplied
mobile designs. The scope is UI, human review workflow, read-only aggregation
queries, all-records browsing, and detail display.

## Background

Agent v1.0-rc1 already has proposal, confirmation, controlled command, audit,
authorization, and restricted internal pilot infrastructure. The previous Expo
AI tab was an internal Agent Review workbench. This task turns that surface
into user-facing review pages without changing Prompt, RAG, Validator, Shadow,
or the existing real-write guardrails.

## Implementation

- Added read-only review aggregation APIs under `/agent/review`.
- Reused existing Agent proposal, confirmation, command, audit, authoritative
  object, and meeting records.
- Rebuilt the Expo AI assistant tab as a product review home page.
- Added all-records and record-detail screens inside the existing mobile app
  navigation.
- Kept approval and rejection on the existing confirmation endpoints.

## Modified Content

- `services/api/app/agent_review_service.py`
- `services/api/app/routers/agent_review.py`
- `services/api/app/main.py`
- `services/api/app/schemas.py`
- `services/api/tests/test_agent_confirmation_api.py`
- `apps/mobile/App.tsx`
- `apps/mobile/src/api.ts`
- `apps/mobile/src/components/BottomNav.tsx`
- `apps/mobile/src/components/LucideIcon.tsx`
- `apps/mobile/src/screens/AIAssistantScreen.tsx`
- `apps/mobile/scripts/test-agent-review-ui.js`
- `README.md`
- `docs/API_CONTRACT.md`
- `docs/CHANGELOG.md`
- `docs/CURRENT_TASKS.md`
- `docs/SCHEMA_AND_BOUNDARIES.md`
- `docs/TESTING.md`
- `SESSION_HANDOFF.md`

## Impact Scope

The change affects the mobile AI assistant UI and API read models for review
display. It does not add migrations, duplicate business tables, or formal
business data copies. Approval may still create a ready controlled command
through the existing confirmation flow, but it does not directly modify formal
business data.

## Testing Result

- `services\api\.venv\Scripts\python.exe -m unittest tests.test_agent_confirmation_api`: passed, 69 tests.
- `services\api\.venv\Scripts\python.exe -m unittest tests.test_api_contract tests.test_agent_config`: passed, 11 tests.
- `cd apps\mobile; npm run typecheck`: passed.
- `cd apps\mobile; npm run test:agent-review-ui`: passed.
- `services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_review_postgres_acceptance.py`: passed against PostgreSQL synthetic data.
- `.\scripts\test-all.ps1`: passed, including API tests, Worker tests, mobile typecheck, and AI assistant static checks.

## Known Limits

- The all-records screen is covered by TypeScript and static checks, not live
  device UI automation.
- The review aggregation count still evaluates object-scope visibility in the
  service layer after SQL tenant/project filtering because object scopes are
  stored in the authenticated principal.

## Follow-Up Suggestions

- Add real-device or React Native Testing Library coverage for the AI assistant
  review screens when the mobile test harness is expanded.
- Review production database indexes if `/agent/review/records` grows beyond
  the current RC/internal grey data volume.
