# Todo Completion And Search Fix

## 开发目标

修复移动端待办完成状态交互没有生效、搜索任务仍在输入时自动查询的问题。

## 背景

待办首页已经接入真实 `PATCH /tasks/{task_id}/status`，搜索页也已改为提交后搜索。但现场验证发现移动端勾选仍返回 404，搜索行为仍不符合“输入法点击搜索后才返回结果”的要求。

## 实现方案

- 移除 `TodoScreen` 中残留的内联搜索状态和 `q: searchText` 请求参数。
- 待办首页搜索按钮只进入独立 `TaskSearchScreen`，不再在首页输入或触发搜索。
- 保持搜索页 `TextInput` 的 `onChangeText` 只更新本地输入和清理旧结果，真实搜索只由 `onSubmitEditing`、显式搜索按钮、重试、加载更多或最近搜索选择触发。
- 增强移动端静态 UI 测试，禁止首页恢复 `searchText/searchOpen/TextInput/q: searchText`，并禁止搜索页输入变化直接调用 `runSearch` 或 `listTasks`。
- 重启本地 8002 API 服务，确认运行中的 OpenAPI 已包含 `/tasks/{task_id}/status`。

## 修改内容

- `apps/mobile/src/screens/TodoScreen.tsx`
- `apps/mobile/scripts/test-todo-ui.js`
- `apps/mobile/scripts/test-task-search-ui.js`
- `docs/CHANGELOG.md`
- `docs/conversations/2026-07-28-todo-completion-search-fix.md`

## 影响范围

影响 Expo 待办首页和任务搜索页的前端交互测试。未修改后端业务逻辑、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `npm run typecheck`: 通过
- `npm run test:todo-ui`: 通过
- `npm run test:task-search-ui`: 通过
- `.\scripts\test-all.ps1`: 通过

## 已知限制

- 任务状态更新依赖当前运行的 API 进程已经重启到包含 `PATCH /tasks/{task_id}/status` 的代码版本。
- 搜索页最近搜索仍使用本地 AsyncStorage，不提供后端历史同步。

## 后续建议

- 每次后端路由变更后重启本地 API，并用 `/openapi.json` 或接口 smoke check 确认可用后再验证移动端。
