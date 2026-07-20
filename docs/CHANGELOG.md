# Changelog

## 2026-07-20

- Added Agent v1.0 Phase 6 Worker-internal cross-meeting state tracker in
  `services/worker/app/agent_state_tracker.py`.
- Phase 6 supports bounded candidate reading, object normalization,
  deterministic matching, state-change classification, evidence-backed
  `AgentActionProposal` generation, proposal validation, and human-confirmation
  flags for `Requirement`, `AgentActionItem`, and `Risk`.
- Extended the internal `AgentActionProposal` contract with Phase 6 fields:
  `action_type`, `confidence`, `risk_level`, `requires_confirmation`, `reason`,
  and `metadata`, while preserving existing `proposal_type` and
  `needs_confirmation` compatibility.
- Added Phase 6 unit tests to the default Worker test gate. The tests cover same
  object matching, new object detection, complete/defer/cancel classification,
  duplicate detection, uncertain review flags, owner/deadline confirmation,
  insufficient evidence confirmation, historical conflicts, high-risk closure
  confirmation, and no database/model/RAG/network side effects.
- Added Agent v1.0 Phase 5B live Shadow acceptance tooling in
  `services/worker/scripts/run_agent_shadow_live_acceptance.py`.
- The Phase 5B tool supports offline-by-default runs, explicit
  `--allow-live-model`, smoke/full selection, `--meeting-id`, `--scenario`,
  per-run `--ollama-timeout`, optional `nvidia-smi` GPU monitoring,
  stop-on-failure gates, quality scoring templates, formal-result snapshot
  hashes, and per-meeting debug artifacts under
  `data/debug/agent_shadow_live_acceptance/<run_id>/`.
- Added Phase 5B unit tests to the default Worker test gate. The tests cover
  default no-real-model behavior, smoke/full and filtered fixture selection,
  serial stop-on-failure behavior, timeout propagation, GPU monitor failure
  degradation, artifact structure, unavailable layer markers, and formal-result
  isolation checks without calling real Qwen3, Chroma, PostgreSQL, or external
  network services.
- Added Agent v1.0 Phase 5 Shadow acceptance fixtures for three core
  scenarios: `project_weekly`, `requirement_review`, and `cross_department`.
- Added `run_agent_shadow_acceptance.py`, an offline-by-default acceptance
  script that writes `acceptance_report.json/.md`, per-meeting summaries, and
  Shadow audit files under `data/debug/agent_shadow_acceptance/<timestamp>/`.
- Calibrated Phase 2 scenario context policy for `requirement_review` and
  `cross_department` so Phase 4B static plans include meeting history for the
  Phase 5 core scenario acceptance gate.
- Added Phase 5 acceptance tests to the default Worker test gate, covering
  scenario plan selection, manual meeting type control, safe degradation for
  missing history/RAG results, failure/timeout/fallback statistics, report
  serialization, and default no-real-model behavior.
- Added Agent v1.0 Phase 4B controlled Worker-internal Orchestrator and Shadow
  Mode sidecar execution after formal summary persistence.
- Added file audit output under `data/debug/agent_shadow_trace/<meeting_id>/`
  with Agent run status, steps, result source, shadow analysis, validator audit,
  fallback reason, and deterministic comparison summary.
- Added Agent Orchestrator tests for Shadow switches, static plan generation,
  unknown minimal plans, audit writing, timeout/failure isolation, fallback
  preservation, deterministic comparisons, and import-side-effect boundaries.
- Added Agent v1.0 Phase 4A Worker-internal Tool Registry and controlled
  Runtime infrastructure.
- Added `ExecutionPlan`, `ExecutionStep`, `AgentRunState`, and
  `AgentStepResult` contracts for static, in-memory Tool execution.
- Added Agent Runtime unit tests for registry behavior, ordered execution,
  optional skips, stop/continue failure handling, timeout/deadline/call limits,
  fallback preservation, and import-side-effect boundaries.
- Added Agent v1.0 Phase 3 first-batch Worker-internal Tool Adapters:
  `get_meeting_context`, `search_meeting_history`,
  `search_project_knowledge`, `get_open_action_items`, `analyze_meeting`, and
  `validate_meeting_analysis`.
- Added Tool contracts for `AgentTool`, `ToolExecutionContext`, `ToolResult`,
  `ToolError`, `ToolPolicy`, and `ToolStatus`, with unified duration, timeout,
  call-limit, structured-error, and result-source handling.
- Added Agent Tool tests to the default Worker test gate.
- Added Agent v1.0 Phase 2 Worker-internal meeting scenario policies with
  schema version `meeting-scenario-policy-v1`.
- Added eight formal meeting scenario policies plus safe `unknown` defaults,
  an immutable policy contract, a deterministic in-memory registry, and a
  `MeetingClassificationResult` contract that reuses `EvidenceRef`.
- Added Phase 2 meeting scenario tests to the default Worker test gate.
- Added Agent v1.0 Phase 1 Worker-internal contract schemas:
  `EvidenceRef`, `Requirement`, `Decision`, `AgentActionItem`, `Issue`, `Risk`,
  `Dependency`, `Milestone`, `CustomerRequest`, `ProjectState`,
  `AgentActionProposal`, and `AgentContext`.
- Added `agent-contract-v1` schema version metadata and tests for Agent contract
  serialization, enum validation, evidence validation, mutable defaults, and
  isolation from the formal `MeetingAnalysisSchema`.
- Added Agent v1.0 Phase 0 baseline freeze documentation and baseline dataset
  directory specification.
- Added API and Worker Agent rollout guardrail settings:
  `AGENT_MODE_ENABLED=false`, `AGENT_SHADOW_MODE=true`, and
  `AGENT_ACTIONS_ENABLED=false`.
- Fixed a production analysis stall where stale `transcript_segments`
  `speaker_name` update locks blocked subsequent summary analysis runs.
- Changed Worker summary orchestration to commit speaker-name backfill before
  RAG/Qwen inference so long model calls do not hold transcript row locks.
- Added `RAG_EMBEDDING_LOCAL_FILES_ONLY=true` Worker setting and made
  `RagRetriever` load the embedding model from local cache by default to avoid
  blocking on Hugging Face metadata requests during manual Worker starts.
- Repaired meeting `73c47be6-0ea0-41eb-ac73-81e458574abd` by rerunning Worker
  analysis successfully; generated summary
  `33db99a1-634d-4d57-b28b-f720c4d9bcde`.

## 2026-07-15

- Added Phase 4 unified meeting analysis schema boundary.
- Added Worker analysis contract normalization before persistence.
- Added summary response `metadata.schema_version`.
- Added schema boundary documentation and ADR 0003.
- Added Phase 5 prompt and RAG version management.
- Moved the formal Qwen3 Meeting Analyst prompt into a versioned prompt template and registry.
- Added RAG dataset manifest, configurable RAG settings, retrieved chunk id tracking, and summary metadata persistence.
- Added Alembic migration `20260715_0011` for prompt/RAG metadata fields.
- Added Phase 6 testing and observability improvements.
- Added Worker/API `/ready` checks, structured Worker analysis logs with redaction, and local service diagnostics.
- Added fake Qwen/RAG Meeting Analyst service tests and regression fixture shape checks.
- Added observability documentation and ADR 0005.
