# Meeting Creation And Title Flow

## 开发目标

优化实时录音、文件导入和 AI 自动标题生成流程，减少创建前表单输入，并确保用户手动标题优先级最高。

## 背景

实时录音此前需要进入 `NewMeetingScreen` 手动填写会议标题；文件导入使用文件名作为会议标题。系统缺少可持久判断标题来源的字段，AI 分析成功后也不会自动替换默认标题。

## 实现方案

移动端实时录音入口直接创建会议并进入录音页，文件导入选择音频后创建会议并进入现有 AI 处理链路。API 增加 `title_source` 区分 `fallback`、`ai_generated` 和 `user_edited`。Worker 在正式 Qwen3 + RAG 分析的同一次返回中接收 `meeting_title`，校验通过后只覆盖仍为系统默认标题且未被用户编辑的会议。

## 修改内容

- 新增本地时间默认标题工具：`apps/mobile/src/utils/meetingTitle.ts`。
- 实时录音入口改为直接创建 `YYYY-MM-DD HH:mm 实时录音` 并进入 `RecordingScreen`。
- 文件导入默认标题改为 `YYYY-MM-DD HH:mm 文件导入`。
- `PATCH /meetings/{id}` 支持标题更新，并将来源标记为 `user_edited`。
- 新增 Alembic revision `20260729_0018` 添加 `meetings.title_source`。
- Worker 新增 `meeting_title` 透传、校验和默认标题替换逻辑。
- 会议详情更多菜单支持手动编辑会议标题。

## 影响范围

影响移动端会议创建入口、会议详情标题编辑、API 会议模型/合同、Worker 正式分析持久化。录音、上传、AIProcessingScreen、会议列表、会议详情、知识库和待办链路继续复用原有接口与状态。

## 测试结果

已执行 `.\scripts\test-all.ps1`，通过。覆盖 Python compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck 和移动端静态 UI 检查。

## 已知限制

AI 标题候选依赖同一次正式分析输出；如果模型未返回标题，或返回泛化、过短、过长、含不允许标点等无效标题，会保留默认标题。旧会议不会批量重命名。

## 后续建议

观察真实会议标题质量，必要时只调整标题校验规则或标题字段提示，避免扩大六维字段含义或引入额外模型请求。
