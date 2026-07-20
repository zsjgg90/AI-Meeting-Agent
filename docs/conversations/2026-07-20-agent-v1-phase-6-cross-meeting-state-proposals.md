# Agent v1 Phase 6 Cross-Meeting State Proposals

## 开发目标

新增 Worker 内部跨会议状态模型，使 Agent 能基于当前会议对象和受控历史候选识别
`new`、`update`、`complete`、`defer`、`cancel`、`duplicate` 和 `uncertain`，并生成带证据的
`AgentActionProposal`。本阶段不写正式业务表、不执行动作。

## 背景

Phase 1 到 Phase 5B 已建立 Agent 合同、会议场景策略、Tool Adapter、Runtime、
Orchestrator Shadow Mode 以及离线/实时 Shadow 验收工具。Phase 6 在这些内部合同之上补充跨会议对象状态判断，但仍保持正式 Qwen3 + RAG 链路、API、数据库和 Expo UI 不变。

## 实现方案

- 扩展 `AgentActionProposal` 内部合同，补齐 `action_type`、`confidence`、`risk_level`、
  `requires_confirmation`、`reason` 和 `metadata`。
- 新增 `services/worker/app/agent_state_tracker.py`。
- 仅支持 `Requirement`、`AgentActionItem` 和 `Risk`。
- 历史候选仅来自调用方传入对象、`AgentContext` 中的内存对象或 `meeting_history` 中的结构化对象。
- 匹配规则使用 object type、project_id、标准化标题、关键词、owner、source meeting 和当前状态；相似度只作为受控候选内排序辅助。
- 输出只包含 `AgentActionProposal` 和匹配审计结构，不持久化、不执行。

## 修改内容

- 新增 `HistoricalObjectReader`、`NormalizedAgentObject`、`ObjectMatch`、
  `CrossMeetingStateTracker` 和 `CrossMeetingStateResult`。
- 新增状态变化判断、提案生成、提案校验和人工确认标记。
- 新增 `services/worker/tests/test_agent_state_tracker.py` 并纳入 `scripts/test-all.ps1`。
- 更新 README、Schema 边界、当前任务、变更日志、测试文档和 Session Handoff。

## 影响范围

影响范围限于 Worker 内部 Agent 合同、跨会议状态跟踪模块、测试和文档。未修改 API Contract、数据库表、Alembic migration、Prompt、RAG、Validator、Expo UI、正式分析链路、Shadow 提升逻辑或 Agent Action 执行逻辑。

## 测试结果

已执行：

```powershell
services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_state_tracker
services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_contract
```

结果：

- `test_agent_state_tracker` 通过 10 项测试。
- `test_agent_contract` 通过 9 项测试。

默认全量门禁 `.\scripts\test-all.ps1` 待最终执行。

## 已知限制

- Phase 6 没有独立正式历史状态源，暂以调用方提供的候选对象为边界。
- 不扫描数据库，也不从模型自由发现历史对象。
- 不生成 API 响应，不写 PostgreSQL，不启动前端确认流。
- 相似度只用于候选排序，不能替代确定性候选边界。

## 后续建议

Phase 7 前需要先定义权威历史状态源、人工确认 API/UI 合同、受控写服务、幂等策略、审计模型、权限边界和回滚策略，再考虑执行任何 Agent Action。
