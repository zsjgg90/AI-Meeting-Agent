# Seven-Phase Maintainability Plan

This document is the source of truth for the current long-term maintainability work.

## Phase 1: Project Audit

Goal:

- Understand the real current state of the project.
- Identify active modules, legacy modules, risk areas, and maintenance gaps.

Primary outputs:

- `docs/PROJECT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/KNOWN_ISSUES.md`

Status:

- Done.

## Phase 2: Project Memory And Documentation Entry

Goal:

- Create stable entry documents for future development sessions.
- Make module ownership, current state, and next tasks discoverable.

Primary outputs:

- `AGENTS.md`
- `docs/CURRENT_TASKS.md`
- Documentation index through `docs/`

Status:

- Done.

## Phase 3: Unified Configuration Management

Goal:

- Centralize local, Docker, API, Worker, Ollama, ASR, and Expo configuration rules.
- Remove hardcoded local values from startup scripts where practical.
- Keep secrets out of startup scripts.

Primary outputs:

- `scripts/local-env.ps1`
- Updated local startup scripts.
- `docs/CONFIGURATION.md`

Status:

- Done.

## Phase 4: Unified Schema And Module Boundaries

Goal:

- Clarify and stabilize API schemas, Worker schemas, AI output schemas, and frontend data contracts.
- Confirm module boundaries between Expo, API, Worker, database, ASR, RAG, and Meeting Analyst.

Expected outputs:

- Schema boundary documentation.
- Identification of duplicate or overlapping schemas.
- Optional contract tests only where they protect schema boundaries.

Status:

- Done.

Primary outputs:

- `services/worker/app/analysis_contract.py`
- `docs/SCHEMA_AND_BOUNDARIES.md`
- `docs/ADR/0003-unified-analysis-schema-boundary.md`
- Worker and API schema contract tests.

## Phase 5: Prompt And RAG Version Management

Goal:

- Make prompts, RAG rules, model config, and evaluation assets traceable by version.
- Avoid changing the Meeting Analyst prompt or RAG content casually.

Expected outputs:

- Prompt inventory.
- RAG source and Chroma version notes.
- Model and prompt version metadata rules.
- Evaluation/report retention rules.

Status:

- Done.

Primary outputs:

- `services/worker/app/prompt_registry.py`
- `services/worker/app/prompts/meeting_analyst_qwen3.md`
- `data/rag/meeting_analyst_rag_manifest.json`
- `docs/PROMPT_AND_RAG_VERSIONING.md`
- `docs/ADR/0004-prompt-rag-version-management.md`
- Prompt/RAG metadata migration and contract tests.

## Phase 6: Testing, Logging And Observability

Goal:

- Provide a repeatable local test and verification path.
- Make API, Worker, ASR, RAG, Ollama, and frontend failures easier to diagnose.

Primary outputs:

- `scripts/test-all.ps1`
- API contract tests
- Updated `docs/TESTING.md`
- `scripts/check-services.ps1`
- `docs/OBSERVABILITY.md`
- `docs/ADR/0005-testing-observability.md`

Status:

- Done with known gaps.

Remaining work:

- API to Worker integration tests.
- Migration verification.
- E2E smoke test.
- Live Qwen3 + RAG evaluation gate in CI.

## Phase 7: Final Verification And Session Handoff

Goal:

- Run final checks.
- Summarize current state, remaining risks, and next safe development steps.
- Leave enough context for the next session to continue without rediscovery.

Expected outputs:

- Final verification report.
- Updated `docs/CURRENT_TASKS.md`.
- Handoff notes.

Status:

- Pending.
