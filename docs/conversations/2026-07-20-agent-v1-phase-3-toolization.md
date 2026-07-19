# Agent v1.0 Phase 3 Toolization

## 开发目标

将现有稳定能力封装为 Agent 后续可调用的薄 Tool Adapter，同时保持正式 Qwen3 + RAG 分析链路完全不变。

## 背景

阶段 1 已定义 Agent 业务对象和 `AgentContext`，阶段 2 已定义八类会议场景策略。阶段 3 第一批只封装现有可控能力，不实现 Tool Registry、Agent Runtime、Orchestrator 或任何写入动作。

## 实现方案

- 新增 `services/worker/app/agent_tools/base.py`，统一定义 `AgentTool`、`ToolExecutionContext`、`ToolResult`、`ToolError`、`ToolPolicy` 和 `ToolStatus`。
- 在 `AgentTool.execute()` 中统一处理调用次数、deadline、Tool timeout、异常转换、耗时统计和 `ToolResult` 返回。
- 新增 6 个薄 Adapter，均支持依赖注入，测试可使用 fake DB、fake RAG retriever、fake analysis service 和 fake validator。
- 所有 Adapter 都不在模块导入时创建 DB Session、RAG Retriever、模型 Client、Chroma client 或网络连接。

## 修改内容

正式完成的 Tool：

- `get_meeting_context`
- `search_meeting_history`
- `search_project_knowledge`
- `get_open_action_items`
- `analyze_meeting`
- `validate_meeting_analysis`

暂缓：

- `get_project_context`：当前没有正式 Project 表或持久化 `ProjectState`。
- `get_active_risks`：当前风险主要存在于 `MeetingSummary.risks_and_focus` JSON，没有独立风险状态模型。

## 影响范围

影响范围限定在 Worker 内部 Tool Adapter、测试门禁和文档。未修改 API Contract、数据库表、Migration、Prompt、RAG 数据或检索规则、Validator 规则、Expo UI 或正式分析链路。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_tools_contract services.worker.tests.test_agent_tools_adapters`，通过 22 项测试。
- 已执行 `.\scripts\test-all.ps1`，通过。该门禁覆盖 API/Worker Python compile、API contract tests、Worker unit tests 和 Mobile TypeScript typecheck；Worker 单元测试共 68 项。

## 已知限制

- 本阶段不实现 Tool Registry。
- 本阶段不实现 Agent Runtime。
- 本阶段不实现 Orchestrator。
- 本阶段不实现保存/写库 Tool、Action 执行 Tool、项目状态更新 Tool、ASR Tool、diarization Tool、跨会议对象匹配或真实会议分类器。
- `analyze_meeting` Tool 只调用现有 `MeetingAnalystService.analyze()`，不会调用 `summarize_meeting()` 或 `save_summary()`。
- 外层同步 Tool timeout 只能返回结构化 `timeout` 结果，不能强制中止底层已经阻塞的同步调用。
- `analyze_meeting` 的真实模型请求超时仍依赖现有 `OLLAMA_TIMEOUT_SECONDS`。
- `search_meeting_history` 目前只是确定性数据库检索，不做向量语义匹配、项目归属推断或跨会议对象匹配。
- `get_project_context` 和 `get_active_risks` 仍未实现。

## 后续建议

阶段 4 可以在这些 Tool Adapter 通过验收后设计 Agent Runtime，但必须继续保持模型不直接写数据库、关键动作人工确认、关闭 Agent 开关时正式链路行为不变。
