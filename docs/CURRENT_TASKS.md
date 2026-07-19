# Current Tasks

## Active Priority

1. Review and accept Agent v1.0 Phase 3 first-batch Tool Adapter behavior.
2. Keep formal Qwen3 + RAG meeting analysis stable.
3. Keep Expo Go flow stable: create meeting -> record -> upload -> process -> analyze -> display.
4. Follow the seven-phase maintainability plan in `docs/PHASE_PLAN.md` for RC
   maintenance issues that remain relevant.
5. Use `data/debug/semantic_pipeline_trace/<meeting_id>/comparison.md` to locate
   semantic quality errors before considering formal semantic output again.
6. Use `data/debug/chain_audit/<meeting_id>/chain_audit.md` before debugging an
   Expo-visible summary, especially when the meeting metadata indicates a
   manual fixture such as `fixture-gold-standard`.

## Pending Engineering Tasks

- Keep Agent v1.0 work on `feature/agent-v1`; do not continue Agent work on
  `main`.
- Import the 19 required Agent v1.0 baseline meeting artifact folders under
  `data/eval/agent_v1_baseline/`.
- Keep Phase 2 meeting scenario policies as read-only contracts until a later
  Agent Runtime phase explicitly wires them in.
- Keep Phase 3 Tool Adapters as thin wrappers only. Do not add Tool Registry,
  Agent Runtime, Orchestrator integration, write-path tools, or action
  execution before a later phase explicitly requires them.
- Defer `get_project_context` and `get_active_risks` until a formal Project
  state source and independent risk state model exist.
- Decide whether to archive or remove legacy `api` and `mobile` directories.
- Move backup Worker files out of active source paths.
- Keep API, Worker, AI, and Expo schemas aligned through the Phase 4 schema boundary.
- Align API contract docs with actual OpenAPI contracts.
- Run Alembic migration `20260715_0011` in local and Docker databases.
- Add end-to-end recording/upload/process/analyze/display smoke test.
- Add migration verification script.
- Fix the sentence-level SemanticEvent intent classifier before changing mapper
  or validator rules. Current gold trace shows the first errors at
  `02_semantic_events_raw`.
- Reproduce Expo summary issues through the real production path before tuning
  analysis logic. The latest Expo fixture result was manually inserted from a
  gold answer and is not valid evidence for Qwen3 + RAG or semantic output
  quality.
- Use `metadata.result_source` in Expo/API responses to distinguish
  `fixture`, `legacy_qwen_rag`, and `semantic_pipeline` before judging quality.
- Use `services/worker/scripts/run_real_production_analysis.py` for single
  V3.2 production-chain diagnostics under
  `data/debug/real_production_analysis/<meeting_id>/`.
- The current `meeting_001` legacy Qwen3 + RAG quality audit is under
  `data/debug/real_production_analysis/meeting_001/quality_audit.md`.
  It found first semantic errors in `model_raw_output.json`; normalized output
  preserved those errors rather than creating new ones.
- Add live Qwen3 + RAG evaluation gate outside default unit tests.
- Review the 2026-07-18 `prompt_stability_eval` artifacts before production
  rollout. The deterministic PostProcessor fixed proposal leakage and metadata
  cleanup, but duplicate-run semantic stability still fails for agenda/action
  consistency and the risk-review meeting.
- Continue monitoring local `qwen3:14b` latency; long meetings now use the
  rule-based semantic fast path, while small meetings and legacy comparison can
  still expose local model latency issues.
- Keep Worker RAG embedding startup in local-cache mode
  (`RAG_EMBEDDING_LOCAL_FILES_ONLY=true`) and avoid holding
  `transcript_segments` row locks during long RAG/Qwen analysis. The
  2026-07-20 Expo failure for meeting `73c47be6-0ea0-41eb-ac73-81e458574abd`
  was repaired after terminating stale transcript update locks and rerunning
  Worker `/analyze` successfully.

## Explicit Non-Goals For Current Phase

- No business logic rewrite.
- No database migration unless a future phase explicitly requires one.
- No Qwen3/RAG prompt or validator changes.
- No UI redesign.
- No queue system migration.
- No Agent Runtime, Tool Registry, or cross-meeting matching until later Agent
  phases.
- No real meeting classifier or Agent action execution in Phase 2.
- No Tool Registry, Agent Runtime, write-path Tool, ASR Tool, diarization Tool,
  project-state update Tool, or cross-meeting object matching in Phase 3.
