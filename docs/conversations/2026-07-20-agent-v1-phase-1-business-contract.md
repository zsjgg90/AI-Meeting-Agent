# Agent v1.0 Phase 1 Business Contract

## 开发目标

建立 MeetMind Agent v1 后续运行所需的统一业务对象与本次运行上下文契约，同时不改变当前正式 Qwen3 + RAG 六维分析结果。

## 背景

阶段 0 已完成基线冻结和 Agent 开关。阶段 1 需要先定义后续场景策略、受控转换、Validator、Agent Runtime 和人工确认流程可复用的数据结构，避免后续直接把 Raw LLM 输出写入正式业务状态。

## 实现方案

新增 Worker 内部模块 `services/worker/app/agent_contract.py`，定义 `agent-contract-v1` 版本的 Pydantic schema。所有业务对象统一使用 `EvidenceRef` 表示证据来源；`AgentContext` 只表示单次运行上下文，并保持 `transcript` 与 `meeting_analysis` 为松耦合 dict/list 结构。

## 修改内容

- 新增 `EvidenceRef`、`Requirement`、`Decision`、`AgentActionItem`、`Issue`、`Risk`、`Dependency`、`Milestone`、`CustomerRequest`、`ProjectState`、`AgentActionProposal`、`AgentContext`。
- 新增受限枚举类型，覆盖证据来源、需求状态、决策状态、行动项状态、风险等级、依赖关系、里程碑状态、客户需求状态、项目健康度和操作建议状态。
- `AgentContext.runtime_metadata` 自动写入并强制保持 `schema_version=agent-contract-v1`。
- 新增 `services/worker/tests/test_agent_contract.py`，覆盖序列化、反序列化、枚举、证据置信度、metadata 合并、可变默认值隔离，以及与正式 `MeetingAnalysisSchema` 的隔离。
- 将 Agent contract 测试加入 `scripts/test-all.ps1` 默认 Worker 测试集合。

## 影响范围

影响范围限定在 Worker 内部 Agent contract、测试脚本和文档。未修改 API Contract、数据库表、Alembic migration、Prompt、RAG、Validator、正式分析链路或 Expo UI。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_contract`，通过，9 个测试。
- 已执行 `services\worker\.venv\Scripts\python.exe -m compileall -q services\worker\app`，通过。
- 已执行 `.\scripts\test-all.ps1`，通过。
- `test-all.ps1` 覆盖 API/Worker Python compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck；Worker 单元测试共 31 个。

## 已知限制

- 新增 schema 暂不持久化到 PostgreSQL。
- 新增 schema 暂不暴露 API。
- Raw LLM 输出不能直接成为这些业务对象，后续阶段仍需受控转换和 Validator。
- 还未实现 Agent Runtime、Tool Registry、跨会议匹配或八类会议场景策略。

## 后续建议

阶段 2 应设计八类会议场景策略系统，先定义场景枚举、策略配置结构、匹配输入输出和默认策略，不修改正式 Qwen3 + RAG 输出。
