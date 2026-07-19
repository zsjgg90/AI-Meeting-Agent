# AI Meeting Agent Maintenance Guide

This repository is an AI meeting agent for recording, transcription, speaker diarization, Qwen3 + RAG meeting analysis, task extraction, and Expo mobile display.

## Current Source Of Truth

- Current mobile app: `apps/mobile`
- Current API service: `services/api`
- Current worker service: `services/worker`
- Current storage root: `storage`
- Current RAG source: `data/rag/meeting_analyst_rag_350_chunks.jsonl`
- Current Chroma database: `data/vector_db`
- Current independent semantic topic aggregation module: `services/worker/app/topic_event_aggregator.py`
- Current independent rule-based six-dimension mapper: `services/worker/app/six_dimension_mapper.py`
- Current independent six-dimension quality validator: `services/worker/app/six_dimension_validator.py`
- Current semantic analysis orchestration entry: `services/worker/app/meeting_analysis_pipeline.py`
- Current semantic/debug chain audit outputs: `data/debug/chain_audit/`
- Current legacy Qwen3 + RAG deterministic postprocessor: `services/worker/app/meeting_analysis_postprocessor.py`

Legacy prototype directories exist and should not be modified for normal work:

- `api`
- `mobile`

## Change Rules

1. Make surgical changes only. Do not reformat unrelated files.
2. Do not modify Qwen3 + RAG, prompt, validator, or analysis schema unless the task explicitly targets them.
3. Expo must call API service only. Expo must not call Worker, Ollama, or Chroma directly.
4. Worker owns ASR, diarization, RAG retrieval, Ollama calls, validation, and summary persistence.
5. API owns HTTP contracts, upload/storage coordination, background task orchestration, and read models.
   API must not enqueue duplicate `queued`/`running` processing tasks for the same meeting, and Worker calls must use a finite timeout so meetings do not stay in analysis states forever.
6. Database schema changes must use Alembic under `services/api/alembic/versions`.
7. Secrets must not be committed or added to startup scripts. Use `.env` or local environment variables.
8. Keep generated debug outputs out of production code paths.
9. Formal meeting summaries currently come from the legacy Qwen3 + RAG path and still pass through `MeetingAnalysisSchema` and existing persistence payload mapping before database writes.
10. Do not persist internal `SemanticEvent`, `TopicEventGroup`, `SixDimensionResult`, or validation flag structures without a separate contract and migration change.
11. The semantic pipeline is in shadow mode for quality diagnosis. It may run after the formal Qwen3 + RAG result, but it must not overwrite formal meeting summaries.
12. Shadow semantic analysis writes trace files under `data/debug/semantic_pipeline_trace/<meeting_id>/` and must log `semantic_pipeline.shadow_completed`, `semantic_pipeline.shadow_failed`, and `semantic_pipeline.trace_dir` as applicable.
13. Long meeting shadow analysis must not depend on per-utterance Qwen3 calls finishing inside the API timeout. The Worker semantic shadow path can use the rule-based fast path for trace generation.
14. Manual Expo fixture meetings must be identified by metadata such as `model_name=fixture-gold-standard`; do not use them to judge production Qwen3 + RAG or semantic pipeline quality.
15. Summary metadata must expose `result_source`: `fixture` for manual gold answers, `legacy_qwen_rag` for formal Qwen3 + RAG results, and `semantic_pipeline` for semantic shadow/debug results.
16. Real production analysis debug runs write artifacts under `data/debug/real_production_analysis/<meeting_id>/` and must not be confused with fixture or semantic shadow quality gates. Quality audits for those runs may be written as `quality_audit.md` in the same directory.
17. Legacy Qwen3 + RAG output must pass through `anti_hallucination_validator.py` before normalization/persistence. The validator blocks over-split agenda items, proposal/action leakage into core conclusions, cross-dimension duplicates, ellipsized or non-continuous `source_text`, and unsupported action owner/deadline/priority fields. Validator audit artifacts for real debug runs may be written as `validated_result.json` and `validator_audit.md`.
18. Expo summary dimensions should display list-style AI output as ordered lists for meeting agenda, key conclusions, action items, unresolved issues, and risks/focus. The mobile formatter must strip embedded numbering and split packed strings such as `1. A；2. B` before rendering with the shared `NumberedList` component.
19. The formal Meeting Analyst prompt must keep explicit rules for theme-level agendas, complete continuous `source_text` without ellipses, no inferred owner/deadline/priority, proposal-vs-decision boundaries, open-issue-vs-action boundaries, and cross-dimension de-duplication.
20. Prompt stability regression uses `services/worker/scripts/run_prompt_stability_eval.py` and writes artifacts under `data/debug/prompt_stability_eval/`. This is a live Qwen3 + RAG gate only; it must not modify Prompt, RAG data, Validator, database, API, or frontend code.
21. Formal Qwen3 + RAG inference parameters are deterministic by default: `temperature=0`, `top_p=0.2`, `seed=42`, and `format=json`. Production and live diagnostic scripts must read these values from Worker settings and log the resolved parameters.
22. Legacy Qwen3 + RAG formal output now flows through `MeetingAnalysisPostProcessor` after `MeetingAnalysisSchema` normalization and before `anti_hallucination_validator.py`. The postprocessor may only filter, deduplicate, sort, clear unsupported fields, and enforce dimension boundaries; it must not generate, rewrite, or supplement meeting facts.
23. Prompt stability regression must save per-run layer artifacts under each run directory: `normalized_before_postprocess.json`, `postprocessed_result.json`, and `validated_result.json`, plus PostProcessor and Validator audit files. Reports must show keep/remove/modify counts for both layers.
24. Worker RAG embedding model loading must use local cache by default (`RAG_EMBEDDING_LOCAL_FILES_ONLY=true`) so production analysis does not block on Hugging Face network metadata requests during manual or service starts.
25. Long summary/model analysis must not hold row locks on `transcript_segments`. Any speaker-name backfill or transcript metadata update must commit before entering RAG retrieval, Qwen inference, semantic shadow tracing, or persistence work.

## Required Checks

Default local verification:

```powershell
.\scripts\test-all.ps1
```

Runtime service diagnostics, when local services are running:

```powershell
.\scripts\check-services.ps1
```

## Documentation Index

- `docs/PROJECT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/AI_PIPELINE.md`
- `docs/API_CONTRACT.md`
- `docs/CONFIGURATION.md`
- `docs/PROMPT_AND_RAG_VERSIONING.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/TESTING.md`
- `docs/CURRENT_TASKS.md`
- `docs/KNOWN_ISSUES.md`
- `PROJECT_FINAL_REPORT.md`
- `DEPLOYMENT.md`
- `RUNBOOK.md`
- `KNOWN_LIMITATIONS.md`
- `ROADMAP.md`
- `SESSION_HANDOFF.md`
- `docs/ADR/0001-qwen3-rag-meeting-analyst.md`
- `docs/ADR/0002-api-worker-boundary.md`

*************分割线****************************
# Default Development Workflow

## Working Principles

每一个新开发任务默认遵循以下流程：

1. 阅读与当前任务相关的项目文档（优先 AGENTS.md、README.md 和 docs/）。
2. 理解现有实现，不猜测、不重复开发。
3. 在开始修改代码前，先输出：

   * 当前理解
   * 修改计划
   * 影响范围
   * 潜在风险
4. 优先采用最小改动方案，保持向后兼容。
5. 如涉及以下核心内容，必须先给出修改方案并等待确认后再实施：

   * 系统架构
   * Prompt
   * RAG
   * Schema
   * API Contract
   * Database
   * 核心业务流程

---

# Documentation Rules

完成开发后，自动同步更新所有受影响的文档。

至少检查以下文档是否需要更新：

* README.md
* AGENTS.md（仅当开发规范发生变化时）
* docs/current-tasks.md
* docs/changelog.md
* docs/session-handoff.md
* docs/ROADMAP.md（如开发计划发生变化）

每完成一个独立开发任务，在：

docs/conversations/

下新增一份 Markdown 文档。

命名格式：

YYYY-MM-DD-<task-name>.md

文档至少包含：

* 开发目标
* 背景
* 实现方案
* 修改内容
* 影响范围
* 测试结果
* 已知限制
* 后续建议

文档内容必须基于实际开发结果，不记录聊天过程，不虚构内容。

---

# Testing Rules

完成开发后，根据本次修改范围执行相关测试。

例如：

* Compile
* Unit Test
* API Contract Test
* Integration Test
* Mobile Typecheck
* Smoke Test

不要报告未执行的测试。

测试结果必须真实说明：

* 已执行
* 未执行
* 执行失败及原因

---

# Task Completion Checklist

每完成一个开发任务，默认执行以下检查：

* 代码修改完成
* 相关测试完成
* 文档已同步
* Conversation 文档已生成
* Session Handoff 已更新（如适用）
* 输出最终实施报告

最终实施报告至少包含：

* 修改内容
* 修改文件
* 测试结果
* 文档更新情况
* 已知风险
* 后续建议

---

# Development Principles

长期遵循以下原则：

* 保持代码可维护性。
* 保持模块边界清晰。
* 保持 Schema 一致性。
* 保持 API 向后兼容。
* 保持 Prompt、RAG、Validator 的版本一致。
* 避免无必要的大规模重构。
* 优先解决实际问题，而不是过度优化。

所有修改应优先保证系统稳定性和长期可维护性。
