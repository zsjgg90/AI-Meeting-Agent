# Agent v1 Phase 11 Production Auth And Authoritative State

## 开发目标

执行 Agent v1 Phase 11：接入最小生产身份认证路径，并建立
Requirement、AgentActionItem、Risk 的一等权威状态读取基础。本阶段继续禁止真实
业务写入。

## 背景

Phase 10 已经移除客户端自报 reviewer/permission headers，但默认
`AgentPrincipal` 适配器仍 fail-closed，Requirement/Risk 仍从
`meeting_summaries` JSON 快照读取。Phase 11 需要把身份和状态源前移到可验证的
服务端边界，同时保留 Agent command dry-run 和 rollback dry-run 的只读性质。

## 实现方案

- 使用最小服务端 token/session 认证模型接入生产路径。
- 新增 Requirement/Risk 正式表，保留来源 summary JSON 引用。
- 迁移从现有 summary JSON 复制候选对象，不删除、不修改原 summary JSON。
- 更新 `DatabaseAuthoritativeStateProvider`，使 Requirement/Risk 不再扫描 summary
  JSON。
- 所有 Agent API 状态读取继续通过服务端 principal 校验 tenant、project、object
  scope 和操作权限。

## 修改内容

- 新增 Alembic revision `20260721_0013`：
  - `requirements`
  - `risks`
  - `agent_users`
  - `agent_auth_sessions`
  - `action_items.tenant_id`
  - `action_items.project_id`
- `AgentPrincipal` 增加 `project_scope`、`object_scope` 和
  `authentication_source` 语义。
- `get_agent_principal` 生产路径改为读取 `Authorization: Bearer <token>`，哈希后
  匹配服务端 session。
- `DatabaseAuthoritativeStateProvider` 改为：
  - Requirement -> `requirements`
  - AgentActionItem -> `action_items`
  - Risk -> `risks`
- 扩展 API 测试覆盖 Phase 11 认证、隔离和正式表读取。
- 新增 PostgreSQL 验收脚本
  `services/api/scripts/run_agent_phase11_postgres_acceptance.py`。
- 更新 README、Schema boundaries、Current Tasks、Changelog、Testing 和 Session
  Handoff。

## 影响范围

影响范围限于 API 认证/授权、API authoritative state provider、Alembic migration、
API 测试、PostgreSQL 验收脚本和文档。未修改 Worker Prompt、RAG、Validator、
Shadow promotion、Expo UI 或正式 Qwen3 + RAG 分析链路。

## 测试结果

已执行并通过：

```powershell
services\api\.venv\Scripts\python.exe -m compileall -q services\api\app services\api\scripts services\api\alembic\versions
services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api
services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase11_postgres_acceptance.py
.\scripts\test-all.ps1
```

`test_agent_confirmation_api` 当前通过 45 项；默认 `test-all.ps1` 中 API
测试总计通过 54 项、Worker 单测通过 138 项，并完成 Mobile TypeScript typecheck
和 `npm run test:agent-review-ui`。

PostgreSQL Phase 11 验收输出通过，覆盖 production token auth、expired/revoked
denial、Requirement/Risk table migration、review fallback、migration idempotency、
rollback、tenant/project/object isolation、summary JSON retention 和 no Agent
business writes。

## 已知限制

- `agent_users` 和 `agent_auth_sessions` 是最小生产认证适配层，仍需后续与完整产品
  用户/session/SSO 体系对齐。
- 历史 `action_items` 在迁移中使用 `default-tenant` / `default-project` 回填，真实
  多租户环境需要后续按业务归属回填。
- Requirement/Risk 表已成为一等读取源，但本阶段没有实现任何正式对象状态写入。
- real write executor 和 real rollback executor 仍是拒绝执行的后续阶段工作。

## 后续建议

- 在进入真实写入阶段前，先评审 Phase 11 token/session 表与正式用户体系的合并策略。
- 为历史 ActionItem、Requirement、Risk 制定真实 tenant/project 回填规则。
- 继续保持 `AGENT_COMMAND_EXECUTION_ENABLED=false`、
  `AGENT_COMMAND_DRY_RUN_ONLY=true`、`AGENT_ROLLBACK_EXECUTION_ENABLED=false`，
  直到真实写入事务、审计和 rollback 执行单独实现并验收。
