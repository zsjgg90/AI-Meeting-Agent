# Knowledge Base Entry Default

## 开发目标

关闭默认 AI 助手入口，将移动端底部导航入口改为知识库，并保留后续重新开启 AI 助手和 Agent 能力的配置开关。

## 背景

AI Meeting Agent v1.0 RC1 已具备 Agent Review、Proposal、Command、Audit 和 Rollback 相关能力，但本阶段产品入口需要默认收敛，避免用户从底部导航进入 AI 助手工作台。

## 实现方案

- 移动端底部导航默认显示知识库入口。
- 新增知识库基础页面和空状态，不接入 RAG 问答。
- 保留 AI 助手页面、记录详情、Agent API helper 和后端 Agent 路由。
- 新增前端和后端功能开关，默认关闭 AI 助手 UI、Proposal 自动生成和本地 Agent 登录入口。

## 修改内容

- 新增 `apps/mobile/src/screens/KnowledgeBaseScreen.tsx`。
- 更新 `apps/mobile/src/components/BottomNav.tsx`，默认用知识库替换 AI 助手 tab。
- 更新 `apps/mobile/App.tsx`，接入知识库路由，并用前端开关隐藏 AI 助手页面入口。
- 更新 `apps/mobile/src/config.ts` 和 `apps/mobile/src/env.d.ts`，增加前端功能开关。
- 更新 `services/api/app/config.py` 和 `services/api/app/routers/meetings.py`，增加并使用 Proposal 自动生成开关。
- 更新 `services/api/start-api-local.ps1`，本地 API 启动不再默认开启本地 Agent 登录。
- 新增 `apps/mobile/scripts/test-knowledge-base-ui.js`，并纳入移动端和全量测试脚本。

## 影响范围

影响范围限定在移动端入口、知识库空页面、配置开关、会议分析完成后的 Agent Proposal 自动生成门禁、测试和文档。未修改 Prompt、RAG 数据、Validator、Shadow、会议分析链路、待办生成逻辑、数据库结构或破坏性迁移。

## 测试结果

- `npm run typecheck`: passed.
- `npm run test:knowledge-base-ui`: passed.
- `npm run test:agent-review-ui`: passed.
- `services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_agent_config`: passed.

全量测试结果以最终实施报告为准。

## 已知限制

知识库本阶段只有基础页面和空状态，没有文件管理、搜索、上传、RAG 检索或问答能力。

## 后续建议

- 后续如需恢复 AI 助手入口，显式设置 `EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=true` 并重新执行移动端静态检查。
- 后续如需恢复会议完成后的 Proposal 自动生成，显式设置 `AGENT_PROPOSAL_AUTO_GENERATION_ENABLED=true` 并保留现有 evidence-bound 生成规则。
