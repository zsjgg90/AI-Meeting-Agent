# Mobile Task Detail Editable Interactions

## 开发目标

根据最新移动端任务详情要求，调整任务详情页的完成状态、标题、描述、来源会议、负责人、截止时间、优先级、来源证据和附件备注交互。

## 背景

当前后端任务能力仍只有 `GET /tasks` 和 `PATCH /tasks/{task_id}/status`。没有独立 `GET /tasks/{id}`、通用任务编辑 API 或任务附件上传 API。本次实现继续不修改后端、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 实现方案

任务详情页继续使用入口传入的真实 `TaskListItem`，并通过现有 `/tasks` 列表接口 best-effort 刷新。状态复选框改为方形并接入正式状态更新 API。标题、负责人、截止时间和优先级在当前 App 会话中同步到待办列表和任务搜索结果；描述编辑和附件备注仅在任务详情页本地展示。

来源会议通过 `getMeeting(meeting_id)` 查询真实会议标题，点击后进入现有会议详情页 `actions` Tab，并继续传递 `sourceSegmentId` 和 `evidenceText`。来源证据只读展示。

## 修改内容

- 重建 `apps/mobile/src/screens/TaskDetailScreen.tsx` 的交互结构和中文文案。
- 在 `apps/mobile/App.tsx` 增加 `taskOverrides`，用于详情页改动同步到当前待办/搜索页面。
- 修改 `TodoScreen.tsx` 和 `TaskSearchScreen.tsx`，按 `taskOverrides` 展示当前会话中的任务标题、状态和元数据更新。
- 更新任务详情、待办、搜索静态 UI 检查。
- 同步 README、Current Tasks、Changelog 和 Session Handoff。

## 影响范围

影响 Expo 移动端任务详情覆盖页、待办首页任务卡片展示、任务搜索结果展示。后端 API 合同、数据库结构、Worker、Prompt、RAG、Validator 和会议详情数据合同未修改。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:todo-ui`：通过。
- `npm run test:task-search-ui`：通过。
- `npm run test:task-detail-ui`：通过。
- `.\scripts\test-all.ps1`：通过，包含 Python compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck 和移动端静态 UI 回归。

## 已知限制

- 任务状态是唯一真实持久化更新字段。
- 标题、负责人、截止时间和优先级只在当前 App 会话内同步到列表/搜索；刷新 App 或重新拉取后以后端数据为准。
- 描述编辑只在当前任务详情页本地可见。
- 附件备注使用本地文件选择器，不上传服务器，退出详情页后不会作为任务附件持久化。
- 截止时间使用轻量弹窗和文本输入/快捷按钮实现，没有引入新的原生日期选择依赖。

## 后续建议

- 若需要真正编辑任务字段，应先定义正式任务编辑 API、权限、并发冲突和失败回滚合同。
- 若需要长期保存备注附件，应先定义任务附件上传、下载和删除 API。
