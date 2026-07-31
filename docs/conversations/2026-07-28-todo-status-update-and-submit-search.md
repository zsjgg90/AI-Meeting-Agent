# Todo Status Update And Submit Search

## 开发目标

将待办列表勾选改为真实 API 更新，精简任务卡片展示字段，并把任务搜索改为用户提交后再请求结果。

## 背景

待办首页和任务搜索页已使用真实 `/tasks` 数据源。此前普通待办状态更新 API 不存在，移动端只能只读展示；搜索页按输入变化请求结果。

## 实现方案

- 新增正式 `PATCH /tasks/{task_id}/status`，当前只接受 `open` 和 `completed`。
- 移动端新增 `updateTaskStatus` API helper。
- 待办首页复选框和标题点击时执行真实状态更新，使用乐观更新、单任务 loading、重复点击禁用和失败回滚。
- 任务卡片和搜索结果卡片只展示复选框、标题、截止时间和优先级，不再展示状态标签、负责人或来源会议字段。
- 搜索页取消输入过程中的联想搜索；输入框只更新本地文本，用户点击键盘搜索后才调用 `GET /tasks?q=...`。
- 完成任务时，乐观更新阶段立即显示选中方形复选框、灰色标题和删除线；搜索页输入变更会清空旧提交结果并作废旧请求，避免继续输入时触发或展示旧查询。

## 修改内容

- `services/api/app/routers/tasks.py`
- `services/api/app/schemas.py`
- `services/api/tests/test_tasks_api.py`
- `services/api/tests/test_api_contract.py`
- `apps/mobile/src/api.ts`
- `apps/mobile/src/screens/TodoScreen.tsx`
- `apps/mobile/src/screens/TaskSearchScreen.tsx`
- `apps/mobile/scripts/test-todo-ui.js`
- `apps/mobile/scripts/test-task-search-ui.js`
- `docs/API_CONTRACT.md`
- `apps/mobile/README.md`
- `docs/CHANGELOG.md`
- `docs/CURRENT_TASKS.md`
- `SESSION_HANDOFF.md`

## 影响范围

影响 API 的任务状态更新读写面，以及 Expo 待办首页和任务搜索页。未修改数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `python -m unittest services.api.tests.test_tasks_api services.api.tests.test_api_contract`：通过
- `npm run typecheck`：通过
- `npm run test:todo-ui`：通过
- `npm run test:task-search-ui`：通过
- `.\scripts\test-all.ps1`：通过

## 已知限制

- 状态更新接口当前只支持 `open` 与 `completed`。
- 搜索仍是关键词模糊匹配和状态/优先级别名匹配，不包含拼音或语义搜索。

## 后续建议

- 如果未来需要更多状态流转，可在 API 层扩展允许状态并补充状态机校验。
