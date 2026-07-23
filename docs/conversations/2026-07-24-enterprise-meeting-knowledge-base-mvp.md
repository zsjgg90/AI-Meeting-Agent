# Enterprise Meeting Knowledge Base MVP

## 开发目标

基于当前会议分析能力实现企业会议知识库 MVP，并接入现有会议业务闭环。范围包括知识库首页、会议记录、关键决策、问题与风险、知识搜索、筛选、搜索结果和来源会议追溯。

## 背景

现有正式链路为 Expo -> API -> Worker -> RAG + Qwen3 -> MeetingAnalysisSchema -> PostProcessor -> Validator -> PostgreSQL -> Expo。知识库此前只有移动端入口和空状态，没有 API、数据库索引、搜索或同步能力。

## 实现方案

MVP 采用 PostgreSQL 作为权威数据源，在 API 侧新增知识同步与查询层。Worker 继续负责 ASR、说话人分离、RAG、Qwen3、Validator 和 Summary/ActionItem 持久化。API 在 Worker 成功返回后调用 `knowledge_sync_service`，同步失败只记录状态，不影响会议主链路。

## 修改内容

- 新增 Alembic revision `20260724_0016`，创建 `meeting_knowledge_items` 和 `meeting_knowledge_syncs`。
- 新增 API 模型、DTO、`knowledge_sync_service` 和 `/knowledge` 查询 router。
- 在会议 process/analyze 成功后触发知识同步。
- 在会议删除前软删除知识条目。
- 新增 `POST /meetings/{meeting_id}/knowledge/reindex` 手动重试同步。
- 移动端新增知识库首页、会议记录、关键决策、问题与风险、搜索首页、搜索结果、筛选弹窗和知识卡片状态组件。
- 扩展 `MeetingDetailScreen` 支持 `initialTab`、`sourceSegmentId`、`startTime`、`evidenceText`。

## 影响范围

- API 数据库迁移、模型、schemas、routers、同步服务和测试。
- 移动端 API client、App 路由、Knowledge 页面组、通用知识卡片和状态组件。
- 文档：README、API_CONTRACT、SCHEMA_AND_BOUNDARIES、CURRENT_TASKS、CHANGELOG、SESSION_HANDOFF。

## 测试结果

已执行：

- `services\api\.venv\Scripts\python.exe -m compileall -q services\api\app`
- `services\api\.venv\Scripts\python.exe -m unittest services.api.tests.test_api_contract services.api.tests.test_knowledge_api`
- `npm run typecheck`
- `npm run test:knowledge-base-ui`
- `.\scripts\test-all.ps1`
- `.\scripts\check-services.ps1`

`.\scripts\test-all.ps1` 通过，包含 API contract、Worker unit tests、Mobile TypeScript typecheck、knowledge base UI static checks、Agent review UI static checks、Meeting detail/history/upload UI static checks，共 140 个 Python 测试通过。

`.\scripts\check-services.ps1` 通过：PostgreSQL、Ollama、Worker、API、Expo Metro 可用；Redis 端口未监听，脚本输出 WARN，但整体 Service check passed。

真实会议验收使用 `ffe4d629-05ea-4578-ac92-816e69751fb7`：

- 真实音频文件：`recording-CAA3FDFB-3B64-4A44-9336-DF621A8A4D9C.m4a`
- 会议状态：`completed`
- transcript segments：47
- Summary：存在
- ActionItems：3
- 手动 reindex：`completed`，`item_count=60`
- Overview：`decision_count=2`、`unresolved_issue_count=2`、`risk_count=2`、`all_count=60`
- 关键词 `接口` 搜索：命中 15 条，首条为 `key_decision`，包含 `source_segment_id`、`speaker_label`、`start_time/end_time`。
- Transcript 搜索：命中 8 条，首条带 `source_segment_id=cd62c1b2-371b-4ce6-8e50-5cc0f54773d1`、`speaker_3`、`87.11-93.71`。

## 已知限制

- 项目筛选未开放，因为 `project_id` 尚未稳定贯穿会议数据。
- `meeting_type` 查询参数已保留，但会议表当前没有稳定 meeting type 字段。
- 第一阶段搜索使用 PostgreSQL 关键词匹配，不接入新的 Chroma collection。
- Knowledge Base 不提供 AI 问答，不重新开放 AI 助手入口。

## 后续建议

- 在更多真实会议上验证知识同步质量和搜索命中。
- 等会议 scope 稳定后再开放 project 维度筛选。
- 后续如需语义搜索，使用独立 Chroma collection：`meeting_knowledge`。
