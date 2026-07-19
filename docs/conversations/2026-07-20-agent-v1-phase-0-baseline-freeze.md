# Agent v1.0 Phase 0 Baseline Freeze

## 开发目标

为 MeetMind 从 RC 阶段进入 Agent v1.0 改造建立阶段 0 基线冻结：记录当前正式链路、版本边界和回退边界，增加 Agent 功能开关，并建立基线验收数据集目录规范。

## 背景

后续 Agent 化升级会引入会议场景识别、项目历史读取、受控工具调用、跨会议状态追踪和人工确认后的状态更新。阶段 0 的目标是确保这些改造可被关闭、可回退，并且不破坏当前正式 Qwen3 + RAG 六维分析链路。

## 实现方案

采用最小改动方案：只新增 API/Worker 配置开关、环境变量示例、基线冻结文档和配置测试。不接入 Agent Runtime，不修改 Prompt、RAG、Validator、Schema、数据库和 API Contract。

## 修改内容

- API Settings 新增 `agent_mode_enabled`、`agent_shadow_mode`、`agent_actions_enabled`。
- Worker Settings 新增同名配置项。
- `.env.example` 新增 Agent v1.0 rollout guardrails。
- 新增 `docs/AGENT_V1_PHASE_0_BASELINE.md` 记录当前 RC 基线和阶段 0 验收状态。
- 新增 `data/eval/agent_v1_baseline/README.md` 记录基线数据集目录规范。
- 新增 API/Worker 配置单元测试。

## 影响范围

影响范围限定在配置读取、测试与文档。默认值保持 Agent 正式链路关闭，不改变现有会议处理、分析、持久化或移动端展示行为。

## 测试结果

- 已执行 `.\scripts\test-all.ps1`，通过。
- 覆盖 API/Worker Python compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck。
- 额外执行 API/Worker Agent 配置测试，均通过。
- 已执行 `.\scripts\check-services.ps1`，失败。PostgreSQL、Ollama、Worker 8001、Worker health/ready、Prompt、RAG manifest、Vector DB、Alembic head 正常；API 8002 port、health、ready 无法连接。

## 已知限制

- 当前工作区 Git 元数据不可用，`git status` 和 `git rev-parse HEAD` 均失败，暂不能记录真实分支与提交，也不能确认已建立 Agent 升级分支。
- 阶段 0 所需 19 场会议基线 artifact 尚未导入，本次只建立目录规范和清单。
- 本机 API 8002 未连通，阶段 0 运行态验收未完成。

## 后续建议

修复 Git 元数据后创建 Agent 升级分支，并补齐 19 场基线会议 artifact。随后运行默认测试和服务诊断，再进入阶段 1 的业务对象与 Agent 数据契约设计。
