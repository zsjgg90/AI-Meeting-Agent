# Changelog

## 2026-07-20

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
