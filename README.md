# 会议声纹识别 AI Agent MVP 1.0

这是一个会议后处理 MVP，用来快速验证从手机录音到后端转写、说话人归并、六维会议纪要和行动项生成的完整链路。

MeetMind AI 面向产品经理、项目经理、研发负责人及中小团队管理者，目标是理解需求评审、项目周会、技术评审、版本规划等会议中的需求、决策、任务、依赖和风险，并跨会议持续追踪项目执行状态。

当前 Release Candidate 正式分析链路为：

```text
Expo -> API -> Worker -> Qwen3 + RAG -> MeetingAnalysisSchema
-> MeetingAnalysisPostProcessor -> AntiHallucinationValidator -> PostgreSQL -> Expo
```

企业会议知识库 MVP 在正式 Summary 与 ActionItem 入库后由 API 侧扩展：

```text
MeetingSummary + ActionItem + TranscriptSegment
-> API knowledge_sync_service
-> meeting_knowledge_items / meeting_knowledge_syncs
-> /knowledge 分类浏览与搜索 API
-> Expo 知识库页面
-> MeetingDetailScreen 来源会议与原文证据
```

知识同步不进入 Worker。Worker 继续负责 ASR、说话人分离、RAG、Qwen3、
Validator 和正式 Summary 持久化。知识同步失败只记录同步失败状态，不阻塞会议
`completed`、Summary、待办和会议详情。

语义事件链路当前处于 shadow mode，仅用于后台诊断和质量对比，不覆盖正式会议纪要：

```text
Transcript -> SemanticEventExtractor -> SemanticEventValidator
Validated Semantic Events -> Topic Event Aggregator -> TopicEventGroup
TopicEventGroup -> SixDimensionMapper -> SixDimensionResult
SixDimensionResult -> SixDimensionValidator -> SixDimensionResult
```

相关模块位于 `services/worker/app/meeting_analysis_pipeline.py`、
`services/worker/app/topic_event_aggregator.py`、
`services/worker/app/six_dimension_mapper.py`、
`services/worker/app/six_dimension_validator.py`。内部 Topic/Event/Validation
结构不会写入数据库或暴露 API。Worker 会在正式 Qwen3 + RAG 输出后尝试运行 shadow
语义链路，并把七级中间结果写入：

```text
data/debug/semantic_pipeline_trace/<meeting_id>/
```

该目录包含 `01_utterances.json` 到 `07_final_meeting_analysis.json` 以及
`comparison.md`，用于定位错误首次出现在哪一层。shadow 链路失败或产出为空不会影响
正式纪要结果。

链路审计报告可写入：

```text
data/debug/chain_audit/<meeting_id>/
```

如果会议 metadata 显示 `model_name=fixture-gold-standard`，说明该会议是人工测试
fixture，不代表正式 Qwen3 + RAG 或语义 shadow 链路输出质量。
Summary metadata also includes `result_source`: `fixture` means a manual gold
answer, `legacy_qwen_rag` means the formal production Qwen3 + RAG path, and
`semantic_pipeline` means semantic shadow/debug output.

Agent v1.0 upgrade work starts from the Phase 0 baseline freeze documented in
`docs/AGENT_V1_PHASE_0_BASELINE.md`. The RC formal path remains the default.
Agent rollout guardrails are available as:

```env
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=false
```

Agent v1.0 Phase 1 introduces Worker-internal contract schemas in
`services/worker/app/agent_contract.py` with schema version
`agent-contract-v1`. These schemas define evidence-backed objects such as
requirements, decisions, Agent action items, issues, risks, dependencies,
milestones, customer requests, project state, action proposals, and per-run
`AgentContext`. They are not exposed through the API and do not replace the
formal six-dimension `MeetingAnalysisSchema`.

Agent v1.0 Phase 2 introduces Worker-internal meeting scenario policies in
`services/worker/app/meeting_scenarios/` with schema version
`meeting-scenario-policy-v1`. The policy registry covers eight formal meeting
types plus `unknown`, and defines required context, focus entities, validation
rules, allowed action proposal names, and confirmation requirements. It is a
read-only contract layer only; it does not classify meetings, call Qwen3,
execute actions, update project state, or change the formal analysis path.

Agent v1.0 Phase 3 starts toolization with thin Worker-internal adapters in
`services/worker/app/agent_tools/`. The first batch contains
`get_meeting_context`, `search_meeting_history`, `search_project_knowledge`,
`get_open_action_items`, `analyze_meeting`, and
`validate_meeting_analysis`. These tools standardize inputs, results, timeouts,
call limits, and structured errors around existing services. They do not create
a Tool Registry, Agent Runtime, Orchestrator, write-path tool, project-state
update, action execution, ASR/diarization tool, or formal-chain integration.

Agent v1.0 Phase 4A adds Worker-internal controlled runtime infrastructure in
`services/worker/app/agent_runtime/`. It registers the six Phase 3 tools,
retrieves tools by name, validates read-only ToolPolicy boundaries, creates an
in-memory `AgentRunState`, and executes a caller-supplied static
`ExecutionPlan` step by step. It is not wired into the formal analysis entry,
does not implement Shadow Mode or Orchestrator integration, and does not execute
Agent actions or database writes.

Agent v1.0 Phase 4B adds a controlled Worker-internal `AgentOrchestrator` in
`services/worker/app/agent_orchestrator.py`. When `AGENT_SHADOW_MODE=true`, it
runs after the formal summary has been persisted, builds a static plan from the
meeting scenario policy, executes Agent Runtime beside the formal result, and
writes file audit output under `data/debug/agent_shadow_trace/<meeting_id>/`.
The Shadow result is not exposed through the API, does not overwrite
`MeetingSummary` or `ActionItem`, and does not execute actions even if
`AGENT_ACTIONS_ENABLED` is changed.

Agent v1.0 Phase 5 adds a Shadow acceptance gate for the first three core
scenarios: `project_weekly`, `requirement_review`, and `cross_department`.
Sanitized synthetic fixtures live under
`data/eval/agent_v1_baseline/phase5_core_scenarios/`, and the acceptance script
is `services/worker/scripts/run_agent_shadow_acceptance.py`. By default it uses
offline fixture analysis and does not call the real model; `--allow-live-model`
is required before the script may call the existing `analyze_meeting` Tool.
Generated reports and per-meeting Shadow traces are written under
`data/debug/agent_shadow_acceptance/<timestamp>/` and remain debug-only. The
offline fixture runtime may report sub-millisecond average durations such as
`0.15 ms`; that number validates structure only and does not represent real
Qwen3/RAG performance.

Agent v1.0 Phase 5B adds a separate live Shadow acceptance tool:
`services/worker/scripts/run_agent_shadow_live_acceptance.py`. It reuses the
Phase 5 fixtures, controlled Agent Orchestrator, existing RAG, Qwen3,
PostProcessor, and Validator components, but does not call the real model
unless `--allow-live-model` is explicitly passed. It writes run-level reports
and per-meeting artifacts under the ignored directory
`data/debug/agent_shadow_live_acceptance/<run_id>/`, including transcript,
RAG context, prompt, raw model output, parsed result, normalized result before
postprocessing, postprocessed result, validated result, Validator audit, Shadow
audit, quality scoring template, GPU samples, GPU summary, and pipeline log.
If a layer is unavailable, the artifact is written with `available=false`
instead of being fabricated.

Agent v1.0 Phase 6 adds a Worker-internal cross-meeting state tracker in
`services/worker/app/agent_state_tracker.py`. It reads only caller-supplied
current objects and bounded historical candidates from `AgentContext` or
explicit in-memory inputs, normalizes `Requirement`, `AgentActionItem`, and
`Risk`, applies deterministic candidate matching, classifies state changes as
`new`, `update`, `complete`, `defer`, `cancel`, `duplicate`, or `uncertain`,
and emits evidence-backed `AgentActionProposal` objects. Phase 6 does not add
write-path Tools, execute Agent actions, scan or mutate PostgreSQL, expose a new
API contract, change Prompt/RAG/Validator, promote Shadow output, or modify
Expo UI. Uncertain matches and insufficient evidence set `needs_review=true`
and require human confirmation.

Agent v1.0 Phase 7 adds Worker-internal write-control contracts in
`services/worker/app/agent_write_control.py`. It defines a read-only
`AuthoritativeStateProvider`, `AuthoritativeStateSnapshot`,
`AgentProposalConfirmation`, `ControlledWriteCommand`, audit records, rollback
plans, and an offline `ControlledWritePlanner`. The planner re-reads the
bounded authoritative object, validates approval, permissions, optimistic
version, proposal expiry, field whitelist, evidence, audit context, high-risk
confirmation, and idempotency before producing a command. Phase 7 still does
not execute database writes, add write-path Tools, expose confirmation API,
modify Expo UI, change Prompt/RAG/Validator, promote Shadow output, or perform
automatic approval.

Agent v1.0 Phase 8 adds the minimum API-side confirmation loop. The production
read-only authoritative provider is `services/api/app/authoritative_state.py`.
It reads `AgentActionItem` from the existing `action_items` table and reads
`Requirement`/`Risk` snapshots from existing `meeting_summaries` JSON fields.
There is still no independent production Requirement or Risk business table.
Agent proposal, confirmation, command, and audit persistence is added through
Alembic revision `20260720_0012` and API-only models:
`agent_action_proposals`, `agent_proposal_confirmations`,
`controlled_write_commands`, and `agent_audit_records`. Approval re-reads the
authoritative object, checks the saved object version, proposal expiry,
reviewer permissions, field whitelist, evidence, audit context, and idempotency,
then saves an inert `ControlledWriteCommand` plus audit record. Phase 8 still
does not execute the command, write formal Requirement/ActionItem/Risk state,
connect Expo UI, change Prompt/RAG/Validator, or promote Shadow results.
Approval and rejection lock the proposal row in PostgreSQL, allow only
`pending -> approved/rejected/expired/conflict`, treat those destination states
as terminal, and use a stable command idempotency key based on proposal, target,
operation, and expected version rather than confirmation id.

Agent v1.0 Phase 9 adds the minimum human confirmation UI and dry-run command
sandbox. Expo uses the existing Agent proposal approval/rejection API from the
AI tab, shows proposal evidence, changes, status, confidence, risk, version
state, ready commands, dry-run results, audit records, and rollback previews.
The API adds command read/dry-run endpoints under `/agent/commands`. The
executor re-reads authoritative state, checks command `ready` status, version,
permissions, idempotency key, expected changes, and rollback preview, then
writes dry-run audit records only. It does not update `action_items`, summary
JSON, Requirement, or Risk state. Runtime guardrails are:

```env
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
```

When execution is not explicitly enabled, command dry-run is rejected. Even
when enabled in tests or local diagnostics, this phase supports only dry-run;
real business writes remain unsupported.

Agent v1.0 Phase 10 adds the pre-real-write safety layer. Agent APIs no longer
trust client-reported `X-Agent-Reviewer` or `X-Agent-Permissions` headers. The
API now uses a server-side `AgentPrincipal` adapter in
`services/api/app/agent_security.py`; because the project still has no
production auth/session/JWT module, the default adapter fails closed with 401
until a real provider is wired in. Tests and local acceptance scripts inject a
server-side principal only through dependency overrides. Permissions are
operation scoped as `proposal_view`, `proposal_review`, `command_dry_run`,
`command_execute`, `audit_view`, and `rollback_execute`, with project scope,
object scope, operation, and risk-level checks. High-risk commands require an
elevated role or permission.

Phase 10 also adds a dry-run-only rollback executor and a formal real-write
transaction contract stub. Rollback dry-run accepts only a persisted command id,
requires the original dry-run audit, re-reads authoritative state, checks object
version and idempotency, generates a rollback command preview, and writes audit
records with `writes_performed=false`. The real-write contract is documented in
code but deliberately rejects execution. Phase 10 still does not write
`action_items`, summary JSON, Requirement, Risk, Prompt, RAG, Validator, Shadow
output, or any production business state.

Agent v1.0 Phase 11 wires the API Agent auth adapter to a minimal production
server-side token/session model. `Authorization: Bearer <token>` is hashed and
matched against `agent_auth_sessions`; active sessions join `agent_users` to
build `AgentPrincipal` with `user_id`, `tenant_id`, `roles`, `permissions`,
`project_scope`, `object_scope`, and `authentication_source`. Missing,
unknown, expired, revoked, or inactive sessions return 401. Scope or permission
denials return 403. Tests may still inject principals through FastAPI
dependency overrides, but the production path fails closed and never trusts
client-reported identity or permissions.

Phase 11 also adds first-class authoritative state tables for `Requirement` and
`Risk` through Alembic revision `20260721_0013`. The migration copies
confirmable candidates from existing `meeting_summaries` JSON into
`requirements` and `risks`, puts incomplete candidates into `review`, records
source meeting/summary/JSON references, preserves the original summary JSON,
and uses source-reference uniqueness to avoid duplicate migration. The
production `DatabaseAuthoritativeStateProvider` now reads `Requirement` from
`requirements`, `AgentActionItem` from `action_items`, and `Risk` from `risks`;
it no longer scans summary JSON as the formal authoritative source. Real
ControlledWriteCommand execution, real rollback execution, automatic approval,
Prompt/RAG/Validator changes, and Shadow promotion remain disabled.

Agent v1.0 Phase 12 adds the pre-real-write preparation layer without enabling
real writes. Alembic revision `20260721_0014` adds
`action_item_scope_backfill_audits` for historical `action_items`
tenant/project backfill evidence. The backfill service only applies a scope
when `summary_id` or `meeting_id` links to exactly one non-default
Requirement/Risk tenant/project pair; existing valid scopes are preserved, and
unverifiable or conflicting rows are recorded for `review`. Backfill supports
dry-run, persisted audit, idempotent repeat execution, and rollback of applied
scope updates. It is an explicit operator-run utility and does not
automatically act on production data.

Phase 12 also adds an offline transaction rehearsal for future real command
execution. The rehearsal locks the command row, checks readiness, re-reads the
authoritative state, validates permission and version, and writes an Agent
audit record in one transaction. It deliberately skips the business mutation
step and records `business_writes_performed=false`; `Requirement`, `Risk`, and
`ActionItem` business fields remain unchanged. The real write executor and real
rollback executor still reject execution and the default safety switches remain
closed. Phase 12 provides the basis for Phase 13 pilot preparation only; it is
not sufficient to directly enable production real writes.

Agent v1.0 Phase 13 adds a restricted real-write pilot for internal test
tenants/projects only. Alembic revision `20260721_0015` adds
`action_items.version`, and `DatabaseAuthoritativeStateProvider` now uses that
integer as the `AgentActionItem` optimistic version. Real execution remains
closed unless all pilot switches are intentionally opened:

```text
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
AGENT_COMMAND_PILOT_ENABLED=false
AGENT_COMMAND_PILOT_TENANTS=
AGENT_COMMAND_PILOT_PROJECTS=
AGENT_ROLLBACK_EXECUTION_ENABLED=false
```

When enabled for a whitelisted internal scope, the pilot executor supports only
`AgentActionItem` `update` and `complete` commands with low/medium risk and the
fields `owner`, `due_date`, `priority`, and `status`. It locks the command and
target action item, revalidates server-side principal permissions, tenant,
project, object scope, risk, field whitelist, and `expected_version`, updates
the action item with `version + 1`, writes an execution audit, and marks the
command `succeeded` in the same PostgreSQL transaction. Repeated or concurrent
execution returns the existing success result without duplicate audit or
business mutation.

Phase 13 also adds pilot rollback execution for successful Phase 13 commands
only. Rollback requires `rollback_execute`, the same internal tenant/project
pilot scope, a separate confirmation action, and a current-version match
against the execution audit. Conflicts are rejected; successful rollback
restores the recorded before values, increments `action_items.version`, writes
rollback audit, and marks the command `rolled_back` in one transaction.
Requirement/Risk writes, cancel, high/critical commands, non-whitelisted
projects, automatic approval, batch execution, Prompt/RAG/Validator changes,
Shadow promotion, and production release remain out of scope. Phase 13 is fit
for Phase 14 grey acceptance planning only, not direct production-wide real
writes.

Agent v1.0 Phase 14 adds production safety guardrails around the Phase 13 pilot
without expanding the write contract. Real execution now also requires explicit
server-side grey configuration: tenant/project/user whitelists, non-zero grey
percentage, non-zero project/user daily limits, non-zero concurrency limit, and
an optional UTC time window. Defaults remain closed. Phase 14 also adds a
global kill switch, tenant/project pause lists, audit-backed circuit breakers,
scoped metrics, scoped and redacted audit search, circuit status/reset
endpoints, and a preflight release gate. Emergency close rejects new command
execution but still allows audit queries and controlled rollback of already
successful Phase 13 commands.

Agent v1.0 Phase 15 completes final acceptance and release decision without
adding product functionality or expanding the write contract. The final
decision is `GO` for internal controlled grey only, under the same Phase 13/14
scope and guardrails. Phase 15 adds final acceptance tooling and archive
documents:

- `services/api/scripts/run_agent_phase15_final_acceptance.py`
- `docs/AGENT_PHASE15_FINAL_ACCEPTANCE_REPORT.md`
- `docs/AGENT_PHASE15_RELEASE_DECISION.md`
- `docs/AGENT_PHASE15_RISKS_AND_OPEN_ITEMS.md`
- `docs/AGENT_PHASE15_GREY_CHECKLIST.md`
- `docs/AGENT_PHASE15_ROLLBACK_EMERGENCY_RUNBOOK.md`

This does not approve production-wide write enablement, Requirement/Risk
writes, summary JSON writes, `cancel`, high/critical commands, batch execution,
automatic approval, Prompt/RAG/Validator changes, or Shadow promotion.

最终交付文档：

- `PROJECT_FINAL_REPORT.md`
- `DEPLOYMENT.md`
- `RUNBOOK.md`
- `KNOWN_LIMITATIONS.md`
- `ROADMAP.md`
- `SESSION_HANDOFF.md`

## 技术栈

- Mobile: Expo React Native
- API: FastAPI，代码位于 `services/api`
- Worker: 音频转写、说话人聚类、Qwen3 + RAG 会议分析服务，代码位于 `services/worker`
- DB: PostgreSQL + SQLAlchemy
- Migration: Alembic
- Storage: 本地 `storage/` 目录
- AI: 火山引擎/本地 Whisper 转写 + Ollama Qwen3 14B + RAG 六维会议分析

## 目录结构

```text
.
├── docker-compose.yml
├── .env.example
├── storage/
├── services/
│   └── api/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── alembic.ini
│       ├── alembic/
│       └── app/
│   └── worker/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
├── apps/
│   └── mobile/
└── mobile/
```

移动端新实现位于 `apps/mobile`，旧 `mobile` 目录为早期原型。

## 启动后端

复制环境变量文件：

```bash
cp .env.example .env
```

如需正式会议分析，需要本地 Ollama 已安装并拉取：

```bash
ollama pull qwen3:14b
```

Docker 启动 PostgreSQL、FastAPI 和 Worker：

```bash
docker compose up --build
```

API 容器启动时会先执行：

```bash
alembic upgrade head
```

Docker 访问地址：

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Worker: http://localhost:8001
- Worker health: http://localhost:8001/health

Windows 本地开发默认端口：

- API: http://127.0.0.1:8002
- Worker: http://127.0.0.1:8001
- Expo: http://127.0.0.1:8081

本地启动：

```powershell
.\services\worker\start-worker-local.ps1
.\services\api\start-api-local.ps1
cd apps\mobile
npx expo start --host lan --port 8081
```

本地验证：

```powershell
.\scripts\test-all.ps1
.\scripts\check-services.ps1
python -m unittest tests.test_evaluate_meeting_analysis
python scripts\evaluate_meeting_analysis.py expected.json actual.json --transcript transcript.txt --output data\eval\reports\baseline_v1.0_RC1.md
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_pipeline_acceptance.py --limit 3 --ollama-timeout 60
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_acceptance.py
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_live_acceptance.py --mode smoke
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase10_security_acceptance.py
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase11_postgres_acceptance.py
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase15_final_acceptance.py
```

`run_meeting_pipeline_acceptance.py` 会使用真实 Qwen3/Ollama 和现有 RAG
对比语义候选链路与旧 Qwen3 + RAG 链路，报告输出到
`data/debug/meeting_pipeline_acceptance/`。该脚本属于 live gate，不纳入默认
`test-all.ps1`。当前正式 Worker 输出仍以旧 Qwen3 + RAG 为准。
`run_agent_shadow_live_acceptance.py` is the Phase 5B live Shadow acceptance
tool. Without `--allow-live-model`, it only validates selection, reporting,
artifact structure, and non-promotion safeguards. With `--allow-live-model`, it
runs selected fixtures serially through the current Qwen3 + RAG analysis
components, records cold/warm durations, optional `nvidia-smi` GPU samples,
quality scoring templates, timeout/fallback/error gates, and formal-result
snapshot hashes. Smoke mode selects
`phase5-project_weekly-1`, `phase5-requirement_review-1`, and
`phase5-cross_department-1`; full mode selects all 9 Phase 5 fixtures. Run
smoke successfully before running full.
`run_real_production_analysis.py` uses the current V3.2 `meeting_001`
transcript by default and writes transcript, RAG context, prompt, raw model
output, normalized result, and pipeline log under
`data/debug/real_production_analysis/<meeting_id>/`.
The current `meeting_001` quality audit is saved as
`data/debug/real_production_analysis/meeting_001/quality_audit.md`.
The same directory may also contain Validator-only regression artifacts:
`validated_result.json` and `validator_audit.md`. These are produced from the
existing raw model output without re-calling Qwen3 and record agenda compression,
continuous evidence repair/rejection, duplicate removal, and action metadata
cleanup before persistence.
Prompt regression artifacts for the optimized legacy Qwen3 + RAG prompt are
written as `model_raw_output_v2.json`, `normalized_result_v2.json`, and
`quality_audit_v2.md` in the same directory.
Multi-meeting prompt stability regression is available via
`services/worker/scripts/run_prompt_stability_eval.py`. It repeats each selected
meeting twice with the same Qwen3 model, Prompt, and RAG settings, then writes
`run_1_result.json`, `run_2_result.json`, `comparison.json`, and aggregate
`stability_report.json/.md` under `data/debug/prompt_stability_eval/`.
Each run also saves `normalized_before_postprocess.json`,
`postprocessed_result.json`, and `validated_result.json` under a per-run
subdirectory so schema normalization, deterministic postprocessing, and
Validator effects can be audited separately. The current 2026-07-18 stability
report did not pass the production gate; see
`docs/KNOWN_ISSUES.md` before treating the prompt as production-ready.

本地端到端流程至少需要：

- `OLLAMA_MODEL=qwen3:14b`：正式 Meeting Analyst 模型
- `RAG_COLLECTION_NAME=meeting_analyst_rules`：正式规则检索集合
- `OLLAMA_TIMEOUT_SECONDS=600`：Worker 单次 Ollama 请求超时，真实分析日志会记录该值和实际耗时
- `WORKER_REQUEST_TIMEOUT_SECONDS=600`：API 等待 Worker 处理/分析的最长时间，超时后任务会落入失败态，避免 APP 长时间停留在“分析中”
- `VOLCENGINE_ASR_API_KEY`：可选，用于火山引擎 ASR；未配置时回退到其他转写 provider
- `HUGGINGFACE_TOKEN`：可选，用于 pyannote 说话人分离；不配置时仍会转写和总结，但 `speaker_label` 可能为空

Worker 模型配置：

```env
TRANSCRIPT_PROVIDER=auto
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
VOLCENGINE_ASR_API_KEY=
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.auc
VOLCENGINE_REALTIME_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_ENABLE_SPEAKER_INFO=true
VOLCENGINE_ENABLE_GENDER_DETECTION=true
WHISPER_MODEL_SIZE=small
REALTIME_WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=zh
WHISPER_INITIAL_PROMPT=以下是普通话会议录音，请准确转写为简体中文，保留人名、项目名、数字和专业术语。
HUGGINGFACE_TOKEN=
OLLAMA_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_SECONDS=600
OLLAMA_TEMPERATURE=0
OLLAMA_TOP_P=0.2
OLLAMA_SEED=42
OLLAMA_FORMAT=json
RAG_ENABLED=true
RAG_COLLECTION_NAME=meeting_analyst_rules
RAG_EMBEDDING_LOCAL_FILES_ONLY=true
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=false
AGENT_COMMAND_EXECUTION_ENABLED=false
AGENT_COMMAND_DRY_RUN_ONLY=true
AGENT_COMMAND_PILOT_ENABLED=false
AGENT_COMMAND_PILOT_TENANTS=
AGENT_COMMAND_PILOT_PROJECTS=
AGENT_ROLLBACK_EXECUTION_ENABLED=false
AGENT_GLOBAL_KILL_SWITCH=false
AGENT_GREY_ENABLED=false
AGENT_GREY_TENANTS=
AGENT_GREY_PROJECTS=
AGENT_GREY_USERS=
AGENT_GREY_PERCENTAGE=0
AGENT_GREY_PROJECT_DAILY_LIMIT=0
AGENT_GREY_USER_DAILY_LIMIT=0
AGENT_GREY_CONCURRENCY_LIMIT=0
AGENT_GREY_WINDOW_START=
AGENT_GREY_WINDOW_END=
AGENT_GREY_MANUAL_PAUSED=false
AGENT_PAUSED_TENANTS=
AGENT_PAUSED_PROJECTS=
AGENT_CIRCUIT_CONSECUTIVE_FAILURES=0
AGENT_CIRCUIT_VERSION_CONFLICT_RATE=0
AGENT_CIRCUIT_ROLLBACK_FAILURES=0
AGENT_CIRCUIT_RECOVERED_AFTER=
AGENT_LOCAL_AUTH_ENABLED=false
```

Formal legacy Qwen3 + RAG summaries are normalized, then passed through
`services/worker/app/meeting_analysis_postprocessor.py`, then through
`anti_hallucination_validator.py` before persistence. The deterministic
postprocessor only filters, deduplicates, sorts, clears unsupported metadata,
and enforces dimension boundaries; it does not create or rewrite meeting facts.
Worker loads the RAG embedding model from the local Hugging Face cache by
default. Keep `RAG_EMBEDDING_LOCAL_FILES_ONLY=true` for local production
analysis so a manually started Worker does not block on network model metadata
requests. Summary analysis also commits speaker-name backfill before entering
RAG/Qwen inference, so long model calls do not hold transcript row locks.

## Evaluation System

Phase 0 evaluation infrastructure lives under `data/eval/`:

- `meeting_cases/`: sanitized offline case folders.
- `schema/`: evaluation case schema compatible with `meeting-analysis-v1`.
- `metrics/`: metric definitions for deterministic offline scoring.
- `reports/`: generated Markdown reports, including `baseline_v1.0_RC1.md`.

The offline evaluator is `scripts/evaluate_meeting_analysis.py`. It compares
existing `expected.json` and `actual.json` files and can generate a baseline
Markdown report:

```powershell
python scripts\evaluate_meeting_analysis.py expected.json actual.json --transcript transcript.txt --output data\eval\reports\baseline_v1.0_RC1.md
```

Supported Phase 0 metrics are Decision Precision, Task Recall, Risk Recall,
Hallucination Rate, and Evidence Coverage. The evaluator is not wired into the
production meeting-analysis flow and does not call Qwen3, Ollama, RAG, API,
database, Worker, ASR, semantic pipeline, or Mobile.

`WHISPER_MODEL_SIZE` 可改为 `medium` 以进一步提升准确率，但 CPU 转写会明显变慢。
`TRANSCRIPT_PROVIDER=auto` 会优先使用豆包/火山引擎 ASR 新版控制台鉴权 `VOLCENGINE_ASR_API_KEY`；会后完整音频默认使用 `volc.seedasr.auc`，实时字幕分片默认尝试 `volc.seedasr.sauc.duration`，并通过 `VOLCENGINE_ENABLE_SPEAKER_INFO=true` 开启说话人聚类，通过 `VOLCENGINE_ENABLE_GENDER_DETECTION=true` 开启男女音色识别。未配置豆包凭证时使用 OpenAI 高准确率转写；云端调用失败时自动回退到本地 faster-whisper。也可以设置为 `volcengine`、`openai` 或 `faster_whisper` 强制指定。

## 启动移动端

```bash
cd apps/mobile
cp .env.example .env
npm install
npm run start:dev
```

移动端 API 地址从 `.env` 读取：

```env
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000
EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=false
EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI=true
```

如果使用真机 Dev Client，请把 `localhost` 改为电脑的局域网 IP，例如：

```env
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000
EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=false
EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI=true
```

移动端首页当前按 MeetMind AI RC1 原型展示品牌区、搜索入口、实时录音、导入音频、全部会议列表和固定底部导航。底部导航固定为 `首页 | 知识库 | 麦克风 | 待办 | 我的`，中心蓝色麦克风按钮复用同一个实时录音入口。实时录音会用用户本地时间自动创建 `YYYY-MM-DD HH:mm 实时录音` 默认标题的会议，并在首页内展开实时录音覆盖层启动同一个真实 `expo-av` 录音实例；向下拖动顶部短横线可收起为 BottomNav 上方迷你录音条，点击迷你条可重新展开。点击结束录音会直接停止并释放录音，显示 `已进入AI结构化分析` 强提示 500ms 后回到首页，随后在移动端后台复用现有上传、转写和 AI 结构化分析链路。导入音频会选择本地音频文件，创建会议后继续进入 AI 处理页复用同一上传、处理和分析流程。

个人中心的 `声纹管理` 已提供 React Native 页面入口。该页面显示声纹识别未开放状态、真实空列表和录入样本入口；`添加声纹样本` 页面复用 `expo-av` 的 `Audio.Recording` 基础能力采集本地声音样本，但使用独立页面状态，不创建会议、不上传会议音频、不触发转写、AI 纪要或 Agent 分析。当前没有正式声纹注册 API，保存时只提示 `待接入接口`，不会伪造注册成功、身份匹配或示例用户列表。

个人中心的 `推送配置` 已提供 React Native 页面入口。该页面定位为 AI 会议成果自动分发中心，展示飞书推送、邮箱推送和短信提醒三个渠道的配置入口；当前没有正式飞书、邮箱、短信、推送配置或推送历史 API，因此开关保持关闭且不可操作，只显示 `未配置`、`暂未开放` 和 `待接入`，不会伪造连接成功、发送成功或历史记录。

### 实时字幕真机调试

后端保留豆包流式会议字幕资源 `volc.seedasr.sauc.duration` 和实时字幕 WebSocket。当前 Expo 移动端录音页只使用 `expo-av` 录制完整音频，未接入 `@siteed/audio-studio` PCM 推流，因此录音过程中不展示实时 ASR 或实时说话人分离结果；结束后会统一上传音频并生成转写和 AI 纪要。若后续重新启用移动端实时字幕，需要 Development Build，普通 Expo Go 无法加载原生 PCM 录音流模块。

后端实时字幕 WebSocket：

```text
ws://{API_HOST}/meetings/{meeting_id}/realtime-stream
```

后端实时字幕流程：

1. 客户端打开 WebSocket。
2. 每 200ms 推送一包 PCM 音频。
3. API 桥接豆包流式 ASR，并开启 `enable_speaker_info=true`、`enable_gender_detection=true`。
4. API 实时写入 `transcript_segments`，包含 `speaker_label` 和 `speaker_gender`。
5. 录音结束后，APP 仍会上传完整 WAV 音频，走会后高准确率处理和会议纪要生成。

iOS 真机需要使用 EAS 生成开发构建：

```bash
cd apps/mobile
npx expo install expo-dev-client
npx eas build --profile development --platform ios
```

Android 本地可用：

```bash
cd apps/mobile
npx expo prebuild
npx expo run:android
```

## 后端接口

- `POST /meetings` 创建会议
- `GET /meetings` 获取会议列表，支持 `limit` / `offset` 分页参数
- `GET /meetings/{id}` 获取会议详情
- `POST /meetings/{id}/audio` 上传音频文件
- `WS /meetings/{id}/realtime-stream` 实时字幕流式转写
- `POST /meetings/{id}/process` 触发会议处理
- `POST /meetings/{id}/analyze` 触发 Meeting Analyst Agent Pipeline
- `GET /meetings/{id}/transcript` 获取转写结果
- `GET /meetings/{id}/summary` 获取六大维度结构化会议分析
- `PUT /meetings/{id}/speakers/{speaker_label}` 保存 `speaker_label -> display_name` 映射
- `POST /agent/action-proposals` 保存待确认 Agent 提案
- `GET /agent/action-proposals` 查询待确认提案
- `GET /agent/action-proposals/{proposal_id}` 查询提案详情
- `POST /agent/action-proposals/{proposal_id}/approve` 人工批准并生成受控写入命令
- `POST /agent/action-proposals/{proposal_id}/reject` 人工拒绝提案
- `GET /agent/review/overview` 查询 AI 助手首页待确认建议和最近处理聚合视图
- `GET /agent/review/records` 分页查询 AI 助手全部处理记录，支持状态筛选和时间排序
- `GET /agent/review/records/{record_id}` 查询单条处理记录详情、证据、确认、命令和审计时间线
- `GET /agent/commands` 查询已生成的受控命令
- `GET /agent/commands/{command_id}` 查询受控命令详情
- `POST /agent/commands/{command_id}/dry-run` 对 ready 命令执行 dry-run 沙箱校验
- `POST /agent/commands/{command_id}/rollback/dry-run` 生成受控 rollback dry-run 预览
- `POST /agent/commands/{command_id}/execute` 执行 Phase 13/14 受限真实写入
- `POST /agent/commands/{command_id}/rollback/execute` 执行受控 pilot rollback
- `GET /agent/commands/{command_id}/audits` 查询命令审计记录
- `GET /agent/ops/metrics` 查询 Agent 内部指标
- `GET /agent/ops/audits` 受控检索 Agent 审计
- `GET /agent/ops/circuit-breakers` 查询熔断状态
- `POST /agent/ops/circuit-breakers/reset` 人工恢复审计型熔断
- `GET /agent/ops/preflight` 查询灰度发布门禁
- `GET /knowledge/overview` 查询知识库首页计数和同步状态概览
- `GET /knowledge/meetings` 分页查询已完成会议记录
- `GET /knowledge/decisions` 分页查询关键决策
- `GET /knowledge/issues` 分页查询遗留问题
- `GET /knowledge/risks` 分页查询风险记录
- `GET /knowledge/search` 基于 PostgreSQL 关键词搜索会议知识
- `POST /meetings/{id}/knowledge/reindex` 手动重试指定会议知识同步

`GET /meetings/{id}/summary` 返回结构：

```json
{
  "meeting_agenda": [],
  "meeting_summary": "",
  "key_conclusions": [],
  "action_items": [],
  "unresolved_issues": [],
  "risks_and_focus": [],
  "topics": [],
  "metadata": {}
}
```

Meeting Analyst Agent Pipeline 包含 Transcript Cleaner、Semantic Label Agent、Topic Chunk Agent、六大维度 Agent、边界校验 Rule Engine 和 JSON Schema 校验。

## 快速验证

创建会议：

```bash
curl -X POST http://localhost:8000/meetings \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"MVP Demo Meeting\"}"
```

获取会议列表：

```bash
curl http://localhost:8000/meetings
```

上传音频：

```bash
curl -X POST http://localhost:8000/meetings/{meeting_id}/audio \
  -F "file=@sample.m4a"
```

音频上传支持 `m4a`、`mp3`、`wav`，文件会保存到：

```text
storage/meetings/{meeting_id}/audio/
```

数据库会记录文件路径、文件大小和上传时间，接口返回 `audio_file_id`。

触发处理：

```bash
curl -X POST http://localhost:8000/meetings/{meeting_id}/process
```

查询转写：

```bash
curl http://localhost:8000/meetings/{meeting_id}/transcript
```

查询纪要：

```bash
curl http://localhost:8000/meetings/{meeting_id}/summary
```

## 端到端流程检查

1. 在 APP 首页点击 `实时录音`。
2. APP 自动创建默认标题为 `YYYY-MM-DD HH:mm 实时录音` 的会议，不打开 `NewMeetingScreen`，也不跳转独立录音页。
3. 首页内录音覆盖层自动开始真实录音；展开层和迷你录音条共享同一个录音实例、计时、暂停状态、meetingId 和 audioUri。
4. 首页实时录音按钮和 BottomNav 中心麦克风按钮都复用同一个录音入口；已有录音会话时点击麦克风只展开当前 Overlay，不创建第二套录音状态。
5. 向下拖动覆盖层顶部短横线可收起为 BottomNav 上方迷你录音条；点击迷你条非按钮区域可重新展开。
6. 点击结束录音后，APP 停止并释放录音，显示 `已进入AI结构化分析` 500ms 后回到首页。
7. APP 在移动端后台上传音频并调用 `POST /meetings/{id}/process`，会议列表 `处理中` 状态左侧显示 loading。
8. API 创建处理任务，并在后台调用 worker。
   如果同一会议已有 `queued` 或 `running` 任务，API 会返回现有任务，避免重复排队。
7. Worker 读取 `storage/meetings/{meeting_id}/audio/` 中最新上传的音频。
8. Worker 使用 `faster-whisper` 写入 `transcript_segments`。
9. 如果豆包返回 `spk_0/spk_1`，worker 会保存为 `Speaker 1/Speaker 2`；如果没有 provider 说话人信息且配置了 `HUGGINGFACE_TOKEN`，worker 使用 `pyannote.audio` 兜底分离说话人。
10. Worker 调用 LLM summary agent，写入 `meeting_summaries` 和 `action_items`。
11. APP 会议详情页会自动刷新处理中状态，默认进入“会议原文”页，使用真实 `transcript_segments` 展示时间轴、说话人、时间戳和原文，并提供基于现有录音文件的播放/暂停、拖动进度、前后 15 秒、时间戳跳转、单段发言播放、会议速览和原文导出入口。AI 纪要保留在同一详情页标签中，复用现有顶部导航、播放器和标签栏，优先展示 canonical 六维字段 `meeting_agenda`、`meeting_summary`、`key_conclusions`、`action_items`、`unresolved_issues`、`risks_and_focus`，继续兼容 legacy 字段，显示只读待办状态和已有证据/时间定位，并通过现有 `/exports/summary.{format}` 能力导出 MD/PDF/DOCX/TXT。
12. 在会议详情页的发言人名称区域，可以把 `Speaker 1/Speaker 2` 保存为真实姓名；后端会保存 `speaker_label -> display_name` 映射，APP 会用真实姓名显示转写和纪要。

导入音频流程同样从首页进入：点击 `导入音频`，选择音频文件后，APP 创建会议并进入现有 AI 处理页。上传格式和解析能力仍以后端 `/meetings/{id}/audio` 接口为准。

## MVP 限制

- 不做实时入会或真实声纹注册。
- 声纹管理移动端页面已可进入和录制本地样本，但正式声纹注册、声纹列表、身份匹配和自动说话人身份辅助仍待后端/API 合同接入。
- 当前移动端录音页不展示实时字幕或示例转写；实时 ASR/说话人分离在会后完整音频处理链路中生成。
- `Speaker 1 / Speaker 2 / Speaker 3` 来自豆包说话人聚类或后端兜底分离，不等于真实身份识别。
- 未配置 `OPENAI_API_KEY` 时，后端仍可启动，但 `/process` 后任务会失败并记录错误。
- RAG 目前只保存文本块，暂不做 embedding 和向量检索。

## Worker 转写

先确保数据库已执行 Alembic migration，然后运行：

```bash
docker compose run --rm worker python -m app.transcribe_meeting {meeting_id}
```

Worker 会读取该会议最新上传的音频文件，使用 `faster-whisper` 转写，再用 `pyannote.audio` 做说话人分离，并写入 `transcript_segments` 表。每个 segment 包含 `start_time`、`end_time`、`text`、`speaker_label`，当前 speaker 只显示 `Speaker A/B/C` 这类 MVP 标签。

生成结构化会议总结：

```bash
docker compose run --rm worker python -m app.summarize_meeting {meeting_id}
```

Summary agent 会读取 transcript segments，调用 LLM 输出结构化 JSON，并保存到 `meeting_summaries` 和 `action_items` 表。若 JSON 解析失败，会自动重试一次。
