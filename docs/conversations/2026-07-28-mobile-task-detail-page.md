# Mobile Task Detail Page

## 开发目标

根据 `docs/design/meetmind-app_task-detail.html` 原型，实现 Expo 移动端独立任务详情页，并让我的待办列表和任务搜索结果优先进入任务详情。

## 背景

当前任务数据来自现有 `/tasks` API。后端只有 `GET /tasks` 和 `PATCH /tasks/{task_id}/status`，没有独立 `GET /tasks/{id}`、通用任务编辑接口或任务附件下载接口。本次任务要求不新增后端接口、不伪造任务字段、不影响会议详情和现有列表/搜索页面状态。

## 实现方案

新增 `TaskDetailScreen` 作为全屏覆盖页。待办首页和任务搜索结果点击任务卡片时传入真实 `TaskListItem`，覆盖页打开后保持底层列表或搜索页面挂载，从而保留筛选、搜索词、结果和滚动状态。详情页使用入口传入任务作为首屏数据，并通过现有 `GET /tasks` 携带 `meeting_id` 和任务标题做 best-effort 刷新，再按 id 匹配最新任务。

## 修改内容

- 新增 `apps/mobile/src/screens/TaskDetailScreen.tsx`。
- 修改 `apps/mobile/App.tsx`，增加任务详情覆盖页状态和来源会议跳转。
- 修改 `TodoScreen.tsx` 和 `TaskSearchScreen.tsx`，任务卡片主点击进入任务详情，原有复选框状态更新继续使用真实状态 API。
- 扩展移动端 `TaskListItem` 可选兼容字段，用于未来真实描述、负责人别名和附件字段透传。
- 新增 `npm run test:task-detail-ui` 静态检查，并同步待办/搜索回归检查。

## 影响范围

影响 Expo 移动端 Todo、任务搜索、任务详情覆盖页和来源会议跳转。未修改 API、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:task-detail-ui`：通过。
- `npm run test:todo-ui`：通过。
- `npm run test:task-search-ui`：通过。
- `npm run test:meeting-detail-ui`：通过。

全量 `.\scripts\test-all.ps1` 在文档生成后执行，以最终实施报告记录为准。

## 已知限制

- 没有独立任务详情接口，刷新只能通过现有 `/tasks` 列表/搜索结果匹配 id；如果任务不在刷新结果内，会继续显示入口传入数据并提示刷新失败。
- 详情页状态只读，不提供本地切换。
- 未检测到任务编辑 API，编辑入口只提示当前版本暂不支持。
- 未检测到任务附件 API，附件区域显示暂无附件，只有未来真实字段提供 URL 时才尝试打开。
- 会议详情当前复用既有 `initialTab='actions'` 和证据参数，实际定位能力由现有会议详情实现决定。

## 后续建议

- 如产品需要直接刷新任务详情，可在后端正式增加 `GET /tasks/{task_id}` 后替换当前 best-effort 刷新。
- 如任务附件或编辑进入正式 API 合约，再将详情页禁用/空状态切换为真实入口。
