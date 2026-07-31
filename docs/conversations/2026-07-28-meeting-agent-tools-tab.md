# Meeting Agent Tools Tab

## 开发目标

根据 `docs/design/meeting-agent.html` 重构 Expo 移动端会议详情页的 `Agent工具` Tab，复用现有顶部导航、播放器和主标签栏，并只接入项目当前真实存在的工具能力。

## 背景

会议详情页此前已经完成会议原文和 AI 纪要重构，`Agent工具` Tab 仍是占位。项目已有 Knowledge Base 页面、查询 API 和 `POST /meetings/{meeting_id}/knowledge/reindex` 手动重建接口；未发现完整邮件发送、飞书任务推送或正式思维导图生成链路。

## 实现方案

在 `MeetingDetailScreen` 内新增 Agent 工具渲染函数，继续使用当前 `FlatList` header、`renderAudioPlayer()` 和 `renderTabs()`。工具能力用简单前端配置结构表达，知识库卡片在会议完成且存在正式纪要时调用现有 reindex API，其他工具明确禁用并通过 Alert 说明原因。生成记录区域不使用原型静态记录，当前统一显示空状态。

## 修改内容

- 新增 `reindexMeetingKnowledge()` API client 和 `KnowledgeSync` 类型。
- 新增 Agent 工具卡片、状态标签、执行中/成功/失败展示、更多功能占位和生成记录空状态。
- 新增邮件与思维导图图标支持。
- App 路由向会议详情页传入现有知识库入口。
- 新增 `test-meeting-agent-tools-ui` 静态检查，覆盖真实知识库接口、禁用工具、防重复点击和禁止假记录。
- `scripts/test-all.ps1` 纳入 `test:meeting-agent-tools-ui`，避免总验证漏检本页。

## 影响范围

影响 Expo 移动端会议详情页 `Agent工具` Tab、移动端 API client、App 内部路由类型、图标组件和移动端静态测试脚本。未修改会议原文、AI 纪要、播放器实现、首页、录音、上传、后端、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

已执行：

- `npm run typecheck`：通过。
- `npm run test:meeting-agent-tools-ui`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `npm run test:knowledge-base-ui`：通过。
- `npm run test:agent-review-ui`：通过。
- `npm run test:recording-upload-ui`：通过。
- `npm run test:meeting-history-ui`：通过。
- `npm run test:numbered-list`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

- 知识库同步仅适用于 `completed` 且已有正式纪要的会议；否则卡片禁用并显示原因。
- 当前没有四类工具的持久化执行记录接口，因此生成记录区域只能显示真实空状态。
- 邮箱推送、飞书任务、思维导图没有完整正式链路，本阶段不开放点击执行。

## 后续建议

- 后续如接入邮箱、飞书或思维导图，应先补齐正式 API 合同、错误处理和执行记录数据源，再开放卡片状态。
- 如果产品需要展示知识库同步历史，应在后端提供明确的工具执行记录或知识同步记录读取接口，而不是由前端静态模拟。
