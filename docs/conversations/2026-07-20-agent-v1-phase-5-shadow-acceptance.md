# Agent v1 Phase 5 Shadow Acceptance

## 开发目标

执行前三个核心会议场景的 Agent Shadow 验收：

- 项目周会：`project_weekly`
- 需求评审会：`requirement_review`
- 跨部门协调会：`cross_department`

本阶段只验证 Shadow 稳定性、静态计划命中、Tool 结果来源、耗时、fallback/timeout
统计和确定性差异对比，不提升 Agent 结果，不执行动作，不写正式业务表。

## 背景

阶段 4B 已经将受控 `AgentOrchestrator` 接入正式分析后的 Shadow Mode。
阶段 5 需要使用至少 9 场脱敏会议数据验证前三个核心场景的策略与执行计划。

## 实现方案

1. 将用户提供的 9 场合成脱敏会议脚本整理为可复跑 fixture。
2. 新增离线优先验收脚本，默认不调用 Qwen3、Chroma、数据库或外部网络。
3. 复用 Phase 4B Orchestrator 和静态计划生成逻辑，使用 fixture runtime 生成
   Shadow 审计和验收报告。
4. 仅在显式传入 `--allow-live-model` 时允许调用现有 `analyze_meeting` Tool。
5. 对需求评审会和跨部门协调会进行最小策略校准，使静态计划按验收要求启用历史会议检索。

## 修改内容

- 新增 `services/worker/scripts/run_agent_shadow_acceptance.py`
- 新增 `data/eval/agent_v1_baseline/phase5_core_scenarios/fixtures.json`
- 新增 `data/eval/agent_v1_baseline/phase5_core_scenarios/README.md`
- 新增 `services/worker/tests/test_agent_shadow_acceptance.py`
- 更新 `scripts/test-all.ps1`，将 Phase 5 验收测试纳入默认 Worker 门禁
- 更新 `requirement_review` 和 `cross_department` 场景策略的历史会议上下文
- 更新 README、测试文档、当前任务、变更日志和会话交接文档

## 影响范围

影响范围仅限 Agent v1 Shadow 验收、会议场景策略上下文配置、测试门禁和文档。

未修改：

- API Contract
- 数据库表和 Alembic Migration
- Prompt
- RAG 数据和检索规则
- Validator 规则
- 正式六维 Schema
- Expo UI
- 正式 Qwen3 + RAG 分析链路
- Tool 核心业务逻辑
- Agent 动作执行或项目状态写入

## 测试结果

已执行：

```powershell
services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_shadow_acceptance services.worker.tests.test_agent_orchestrator services.worker.tests.test_meeting_scenarios
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_agent_shadow_acceptance.py --timestamp phase5-local-acceptance
.\scripts\test-all.ps1
```

阶段 5 本地离线验收结果：

- 会议数：9
- 场景计划命中率：1.0
- Shadow 完成率：1.0
- Tool 失败率：0.0
- fallback 率：0.0
- 六维字段完整率：1.0
- 真实模型调用次数：0
- 输出目录：`data/debug/agent_shadow_acceptance/phase5-local-acceptance/`

最终全量门禁通过，覆盖 API/Worker Python compile、API contract tests、
Worker unit tests 和 Mobile TypeScript typecheck。

## 已知限制

- 默认验收使用 fixture Shadow 分析，因此不评估真实模型输出质量。
- Runtime 对包含 disabled optional steps 的计划仍记录为 `partial`，报告将安全
  `partial` 计入 Shadow 完成率，并保留每步状态。
- 本地离线平均耗时约 `0.15 ms`，只代表 fixture 结构验收开销，不代表真实
  Qwen3/RAG 性能。
- `search_meeting_history`、`search_project_knowledge` 和 `get_open_action_items`
  在离线 fixture 模式下返回空结果和降级原因，用于验证安全降级。
- 真实模型验收必须显式传入 `--allow-live-model`，并依赖本地 Qwen3/RAG 环境。

## 后续建议

- 阶段 5 验收通过后，再进入阶段 6 的跨会议状态追踪设计。
- 阶段 6 前应明确正式项目状态、任务、风险、需求等状态源和写入边界。
- 如需评估真实模型差异，应用 `--allow-live-model` 单独生成 live report，并避免纳入默认单元测试。
