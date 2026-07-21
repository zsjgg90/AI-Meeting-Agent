# Agent v1 Phase 10 Production Permission Safety

## 开发目标

完成真实写入前的安全准备：生产认证适配、权限映射、写入事务边界、rollback dry-run、故障演练和安全验收。本阶段继续禁止正式业务写入。

## 背景

Phase 9 已提供 Expo Agent Review 工作台和 command dry-run 沙箱，但 Agent API 仍依赖开发阶段的客户端自报 reviewer/permission headers，且没有 rollback dry-run 执行器。进入真实写入试点前必须先移除对客户端权限声明的信任，并明确写入事务和回滚边界。

## 实现方案

- 新增 API 侧 `AgentPrincipal` 认证适配接口。当前项目没有完整生产 auth/session/JWT 模块，因此默认适配器 fail-closed，返回 401；测试和本地安全验收通过 FastAPI dependency override 注入服务端测试 principal。
- 将 Agent Proposal、Command、Audit API 的授权从客户端 header 改为服务端 principal。
- 定义 `proposal_view`、`proposal_review`、`command_dry_run`、`command_execute`、`audit_view`、`rollback_execute` 权限，并校验 user、tenant、project、object、operation、risk。
- 新增 rollback dry-run 执行器，仅接受已持久化 command id，要求原 dry-run audit，重新读取权威状态，校验版本并生成 rollback command preview 和审计。
- 增加真实写入事务合同 stub，明确后续必须在单事务内完成权威状态二次读取、乐观锁、幂等恢复、业务写入、audit 写入、失败回滚和状态变更；Phase 10 调用该 stub 一律拒绝。
- Expo 移除 `X-Agent-Reviewer` 和 `X-Agent-Permissions` 发送逻辑，继续只调用 API 合同。

## 修改内容

- `services/api/app/agent_security.py`：新增认证适配接口、principal、权限和 scope/risk 校验。
- `services/api/app/routers/agent_proposals.py`：提案保存、列表、详情、批准、拒绝改用服务端 principal。
- `services/api/app/routers/agent_commands.py`：命令列表、详情、dry-run、audit 读取和 rollback dry-run 改用服务端 principal。
- `services/api/app/agent_command_executor.py`：dry-run 改用 principal，新增 rollback dry-run executor 和真实写入事务合同 stub。
- `services/api/app/schemas.py`：新增 rollback dry-run API 响应 schema。
- `services/api/app/config.py`、`.env.example`：新增 `AGENT_ROLLBACK_EXECUTION_ENABLED=false`。
- `apps/mobile/src/api.ts`：移除客户端 Agent reviewer/permission headers。
- `apps/mobile/scripts/test-agent-review-ui.js`：增加静态检查，防止恢复客户端权限 headers。
- `services/api/tests/test_agent_config.py`、`services/api/tests/test_agent_confirmation_api.py`：扩展 Phase 10 安全测试。
- `services/api/scripts/run_agent_phase10_security_acceptance.py`：新增 PostgreSQL 安全验收脚本。
- `README.md`、`docs/SCHEMA_AND_BOUNDARIES.md`、`docs/CURRENT_TASKS.md`、`docs/CHANGELOG.md`、`docs/TESTING.md`、`SESSION_HANDOFF.md`：同步 Phase 10 状态、边界、测试和风险。

## 影响范围

- API Agent proposal/command/audit 路由的认证授权边界。
- API dry-run 和 rollback dry-run 执行器。
- Expo Agent Review API helper 的请求 headers。
- 测试门禁和 PostgreSQL 安全验收脚本。

不影响 Worker Prompt、RAG、Validator、Shadow promotion、正式 Qwen3 + RAG 链路或正式业务表写入逻辑。

## 测试结果

- `services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config services.api.tests.test_agent_confirmation_api`：通过，41 tests OK。
- `.\scripts\test-all.ps1`：通过。包含 API/Worker compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck、`npm run test:agent-review-ui`。
- `services\api\.venv\Scripts\python.exe services\api\scripts\run_agent_phase10_security_acceptance.py`：通过。输出 `PASS: Phase 10 PostgreSQL safety checks passed: auth fail-closed, scope/risk denial, idempotent dry-run, rollback dry-run, conflict rejection, and business isolation.`

## 正式业务数据未写入证据

- API 单测验证 approve、command dry-run、rollback dry-run、audit 失败和真实写入 stub 均保持 `ActionItem.owner == "Alice"`，summary JSON 未被改写。
- Dry-run 和 rollback dry-run 审计均记录 `writes_performed=false`。
- PostgreSQL 安全验收脚本使用 `phase10_pg_` 前缀合成数据并在 finally 清理，验证正式 `ActionItem` owner 未变化。
- Phase 10 没有实现真实 write executor，也没有实现真实 rollback executor。
- 不得通过修改环境变量绕过未实现的正式执行器；真实写入和真实 rollback 仍必须由后续阶段单独实现并验收。

## 已知限制

- 当前 `AgentPrincipal` 是认证适配接口，不是生产认证实现；默认 fail-closed。
- Header 权限已不可信，但生产用户、角色、tenant/project/object scope 仍需真实认证/授权系统接入。
- Requirement/Risk 权威状态仍来自 `meeting_summaries` JSON 快照，没有独立生产业务表。
- rollback executor 仅支持 dry-run，没有真实 rollback 执行。
- 真实写入事务合同只有拒绝式 stub，不能进入生产写入。

## 后续建议

- 接入真实生产 auth/session/JWT provider，并映射用户、角色、tenant、project、object scope。
- 在试点前补充独立 Requirement/Risk 生产状态源决策。
- 在真实写入 phase 中实现单事务 executor、真实 rollback executor、审计持久化故障演练和最小灰度开关。
- 保持 `AGENT_COMMAND_EXECUTION_ENABLED=false`、`AGENT_COMMAND_DRY_RUN_ONLY=true`、`AGENT_ROLLBACK_EXECUTION_ENABLED=false` 直到安全验收批准。
