# Knowledge Base Home Redesign

## 开发目标

根据 `docs/design/meetmind-app_knowledge-base.html` 重构 Expo 移动端知识库首页，并只接入项目已有真实能力。

## 背景

当前项目已有 API 侧 PostgreSQL 知识库 MVP，包括知识概览、会议知识列表、决策列表、问题风险列表、知识搜索和会议知识 reindex。项目当前没有独立知识库问答 API、问答历史持久化、知识库语音输入或文档知识上传索引 API。

## 实现方案

保留现有 `App.tsx` 路由和 `BottomNav`，重写 `KnowledgeBaseScreen` 为单页 `FlatList` 布局。按后续产品要求，移除知识库内容概览区域；页面不再为首页概览加载 `/knowledge/overview`、`/knowledge/meetings` 或 `/tasks`。快捷问题只填入输入框；提交问题时提示当前版本暂未开放知识库问答，不生成静态回答。

## 修改内容

- 重构 `apps/mobile/src/screens/KnowledgeBaseScreen.tsx`：
  - 顶部 `MeetMind AI` 标题栏和禁用历史入口。
  - 欢迎区、静态 React Native 机器人头像和 RC1 文案。
  - 三个快捷问题入口。
  - 知识搜索、关键决策、问题风险入口。
  - 已移除知识库内容概览区域。
  - 固定底部输入区、禁用语音按钮、复用音频导入加号入口。
- 更新 `apps/mobile/App.tsx`，向知识库首页传入待办页和音频导入路由回调。
- 更新 `apps/mobile/scripts/test-knowledge-base-ui.js`，覆盖新首页关键约束。
- 更新 `docs/CHANGELOG.md`、`docs/CURRENT_TASKS.md` 和 `SESSION_HANDOFF.md`。

## 影响范围

影响范围限定为 Expo 知识库首页、其路由回调和对应静态测试。未修改后端业务、数据库、Worker、Prompt、RAG、Validator、六维 Schema 或模型调用。

## 测试结果

- 已执行：`npm run typecheck`
- 已执行：`npm run test:knowledge-base-ui`

## 已知限制

- 当前没有真实知识库问答 API，因此页面不展示聊天结果列表。
- 当前没有知识库语音输入 API，因此语音按钮为禁用提示。
- 当前没有独立文档知识上传和索引 API，首页不展示文档知识概览。
- 首页不展示会议、待办或文件统计概览。

## 后续建议

- 如后续新增正式知识库问答 API，应在前端保留引用来源、会议名、文件名、证据片段和跳转元数据。
- 如后续新增文档知识上传 API，应将文件知识卡片和加号入口改为复用正式文档上传流程。
