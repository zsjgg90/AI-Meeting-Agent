# Agent v1 Phase 7 Write Control Contracts

## 开发目标

为 Phase 6 生成的 `AgentActionProposal` 建立离线安全闭环：

```text
读取权威状态
-> 校验提案
-> 等待人工确认
-> 生成受控写入命令
-> 审计与回滚
```

本阶段只完成合同、边界和离线实现，不接正式 API/UI，不写正式业务数据。

## 背景

Phase 6 已能基于当前会议对象和受控历史候选生成 `AgentActionProposal`，但这些提案不代表正式状态变更。Phase 7 为后续确认与写入阶段定义更严格的权威状态、人工确认、命令、审计、回滚和拒绝规则。

## 实现方案

- 新增 Worker 内部模块 `services/worker/app/agent_write_control.py`。
- 定义只读 `AuthoritativeStateProvider` 和离线 `InMemoryAuthoritativeStateProvider`。
- 定义 `AgentProposalConfirmation`、`ControlledWriteCommand`、`AuditRecord`、`RollbackPlan` 和 `WriteControlResult`。
- 使用 `ControlledWritePlanner` 从提案和确认生成 inert command。
- 命令生成前强制执行权威状态二次读取、乐观锁版本校验、权限校验、字段白名单、幂等键、证据校验、审计上下文校验、高风险确认和冲突拒绝。

## 修改内容

- 新增 `services/worker/app/agent_write_control.py`。
- 新增 `services/worker/tests/test_agent_write_control.py`。
- 更新 `scripts/test-all.ps1`，将 Phase 7 测试纳入默认 Worker 门禁。
- 更新 README、Schema 边界、当前任务、变更日志、测试文档和 Session Handoff。

## 影响范围

影响范围限于 Worker 内部 Agent 写入控制合同、离线测试和文档。未修改 API Contract、数据库表、Alembic migration、Prompt、RAG、Validator、Expo UI、正式分析链路、Shadow 提升逻辑或 Agent Action 执行逻辑。

## 测试结果

已执行：

```powershell
services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_write_control
```

结果：

- `test_agent_write_control` 通过 14 项测试。

默认全量门禁 `.\scripts\test-all.ps1` 待最终执行。

## 已知限制

- Phase 7 仍没有生产权威状态源，当前只提供接口和离线内存实现。
- `ControlledWriteCommand` 只是未来写服务的输入合同，不执行数据库写入。
- 没有确认 API、前端确认页面、自动审批、写库 Tool 或动作执行。
- 回滚计划只基于当前权威快照生成，不代表生产回滚事务已经实现。

## 后续建议

下一阶段前需要先明确生产权威状态源、确认 API/UI 合同、正式审计表、命令持久化表、写服务幂等策略、权限来源、回滚事务策略和运行时开关，再考虑任何真实写入。
