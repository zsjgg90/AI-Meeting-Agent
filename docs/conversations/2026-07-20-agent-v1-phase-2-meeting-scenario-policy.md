# Agent v1.0 Phase 2 Meeting Scenario Policy

## 开发目标

建立可版本化、可注册、可测试的会议场景策略层，为后续 Agent Runtime 判断上下文读取、重点对象、边界规则、允许建议动作和人工确认要求提供只读契约。

## 背景

阶段 1 已新增 `agent-contract-v1` 业务对象和 `EvidenceRef`。阶段 2 在不修改正式分析链路的前提下，为八类目标会议和 `unknown` 场景补充策略契约。

## 实现方案

- 在 `services/worker/app/agent_contract.py` 中新增共享 `MeetingType`。
- 新增 `services/worker/app/meeting_scenarios/`，将策略契约、场景配置和 Registry 分离。
- 使用不可变 `MeetingScenarioPolicy`，策略字段使用统一 Literal 类型。
- 使用纯内存 Registry 提供 `get_policy()`、`list_policies()`、`has_policy()`。
- 新增 `MeetingClassificationResult`，复用阶段 1 的 `EvidenceRef`。

## 修改内容

- 新增八类会议策略：需求评审会、项目周会、技术方案评审、版本规划会、跨部门协调会、项目复盘会、管理决策会、客户需求沟通会。
- 新增 `unknown` 安全默认策略，要求人工复核，不加载历史上下文，不允许高风险动作。
- 新增阶段 2 单元测试并纳入 `scripts/test-all.ps1`。
- 更新 README、Schema 边界、当前任务、Changelog、Testing 和 Session Handoff。

## 影响范围

影响范围限定在 Worker 内部 Agent 场景策略契约、测试和文档。未修改 API Contract、数据库、Migration、Prompt、RAG、Validator、Expo UI 或正式六维输出。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_meeting_scenarios`，通过 15 项测试。
- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_contract services.worker.tests.test_meeting_scenarios`，通过 24 项测试。
- 已执行 `.\scripts\test-all.ps1`，通过。该门禁覆盖 API/Worker Python compile、API contract tests、Worker unit tests 和 Mobile TypeScript typecheck。

## 已知限制

- 本阶段不实现真实会议分类器。
- 本阶段不实现 Agent Runtime、Tool Registry、Orchestrator 或 Agent Action 执行。
- 策略只声明允许的建议动作，不执行数据库或项目状态修改。

## 后续建议

阶段 3 应将现有 ASR、转写读取、RAG 检索、正式分析、语义 shadow 和 Validator 能力封装为受控工具，并保持正式链路行为不变。
