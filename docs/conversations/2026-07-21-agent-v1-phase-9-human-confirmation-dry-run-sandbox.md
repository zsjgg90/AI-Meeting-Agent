# Agent v1 Phase 9 Human Confirmation UI And Dry-Run Sandbox

## 开发目标

建立 Agent v1 最小人工确认闭环：

```text
查看待确认提案
-> 查看证据和变更
-> 人工批准或拒绝
-> dry-run 执行
-> 查看审计与回滚结果
```

本阶段默认禁止正式业务写入，仅允许 dry-run 沙箱。

## 背景

Phase 8 已经提供提案保存、列表、详情、人工批准、人工拒绝、惰性
`ControlledWriteCommand` 持久化和审计记录。Phase 9 在该基础上补齐最小 Expo
人工确认界面和 API dry-run 执行器，但不引入真实写入服务。

## 实现方案

- 复用 Phase 8 proposal、confirmation、command、audit 表和审批 API。
- 新增 API command routes，只支持读取已持久化命令、执行 dry-run、读取命令审计。
- 新增 dry-run executor，按 command id 重新读取权威状态并校验安全边界。
- 新增运行时开关：
  - `AGENT_COMMAND_EXECUTION_ENABLED=false`
  - `AGENT_COMMAND_DRY_RUN_ONLY=true`
- 在 Expo 现有 AI tab 中实现 Agent Review 工作台，不新增 Worker/Ollama/Chroma 直连。

## 修改内容

- 新增 `services/api/app/agent_command_executor.py`。
- 新增 `services/api/app/routers/agent_commands.py`。
- 扩展 `services/api/app/schemas.py` 的 dry-run 响应模型。
- 扩展 `services/api/app/config.py` 与 `.env.example` 的 Phase 9 开关。
- 将 command router 注册到 `services/api/app/main.py`。
- 扩展 `services/api/tests/test_agent_confirmation_api.py` 与
  `services/api/tests/test_agent_config.py`。
- 扩展 `apps/mobile/src/api.ts` 的 Agent proposal/command/audit API helper。
- 替换 `apps/mobile/src/screens/AIAssistantScreen.tsx` 为 Agent Review 工作台。
- 新增 `apps/mobile/scripts/test-agent-review-ui.js` 并纳入 `scripts/test-all.ps1`。
- 更新 README、Schema 边界、Current Tasks、Changelog、Testing 和 Session Handoff。

## 影响范围

影响范围限定为 API Agent command dry-run 边界、Expo AI tab 内部页面、测试和文档。

未修改：

- Prompt
- RAG
- Validator
- Worker Shadow promotion
- 正式 Qwen3 + RAG 分析链路
- `action_items` 正式写入逻辑
- `meeting_summaries` summary JSON 写入逻辑
- Requirement 或 Risk 独立业务表
- 自动批准或真实 rollback executor

## 安全边界

- 客户端不提交 `expected_object_version`。
- 客户端不提交 `idempotency_key`。
- 客户端不构造或提交 `ControlledWriteCommand`。
- dry-run 只接受已持久化 command id。
- command 必须为 `ready`。
- dry-run 前重新读取权威状态并校验版本。
- dry-run 校验权限、幂等键、目标存在和预计变更。
- 重复 dry-run 返回已有 dry-run 审计作为 duplicate，不重复生成成功审计。
- dry-run 审计始终记录 `writes_performed=false`。

## 测试结果

已执行：

```powershell
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
cd apps\mobile
npm run typecheck
npm run test:agent-review-ui
```

结果：

- API Agent config 和 confirmation/dry-run tests 通过，共 27 项。
- Mobile TypeScript typecheck 通过。
- Agent Review UI static checks 通过。

最终全量门禁 `.\scripts\test-all.ps1` 待本阶段收尾时执行。

## 已知限制

- Phase 9 仍使用开发期 Agent reviewer header，不是生产权限系统。
- Requirement 和 Risk 仍来自现有 `meeting_summaries` JSON 快照，没有独立生产业务表。
- dry-run 审计只生成回滚预览，不执行真实 rollback。
- Expo Agent Review 是最小内部工作台，没有端到端 UI 自动化。
- 默认配置会拒绝 command dry-run；本地或测试必须显式打开
  `AGENT_COMMAND_EXECUTION_ENABLED=true` 才能验证 dry-run 成功。

## 后续建议

- 在进入真实写入前，先评审 Phase 9 dry-run 审计、回滚预览和版本冲突体验。
- 明确生产权限系统和审计保留策略。
- 决定 Requirement 和 Risk 是否需要一等生产业务表。
- 设计真实写入事务、rollback executor、冲突恢复和运维开关后，再进入下一阶段。
