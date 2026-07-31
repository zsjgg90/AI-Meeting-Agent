# Mobile Todo Home Redesign

## 开发目标

根据 `docs/design/meetmind-app_todo.html` 重构 Expo 移动端 `我的待办` 首页，使用真实 `/tasks` 数据展示待办列表、统计、搜索、筛选、任务元信息和来源会议跳转。

## 背景

现有 `TodoScreen` 已接入 `/tasks` 分页接口，但页面中文文案存在编码损坏，完成状态使用本地 `toggleTask` 伪更新。项目当前没有面向待办首页的普通任务状态更新接口；Agent 内部受控写入能力不适合直接作为本页面 checkbox 更新能力。

## 实现方案

保留 API-only 移动端边界，不修改后端、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。待办首页继续使用 `GET /tasks` 获取真实任务数据，使用 `FlatList` 承载顶部统计和列表。状态按钮改为只读提示，不在本地制造完成状态。任务卡片点击复用现有会议详情路由并进入 `actions` tab。

## 修改内容

- 重写 `apps/mobile/src/screens/TodoScreen.tsx`，实现顶部标题栏、搜索状态、统计卡片、筛选 tabs、真实任务卡片、加载/空/失败/刷新/分页状态。
- `apps/mobile/App.tsx` 向 `TodoScreen` 传入来源会议跳转回调。
- 新增 `apps/mobile/scripts/test-todo-ui.js`，覆盖真实 `/tasks`、只读状态、统计、搜索、筛选、分页刷新和会议详情跳转结构。
- `scripts/test-all.ps1` 加入 `npm run test:todo-ui`。
- 更新移动端 README、Current Tasks、Changelog 和 Session Handoff。
- 后续按产品要求移除独立的“全部 / 进行中 / 已完成 / 超期”选项卡，并将任务状态图标改为方形 checkbox 样式。任务标题和 checkbox 使用同一个状态操作入口；由于当前没有正式状态更新 API，该入口仍保持只读提示。

## 影响范围

影响 Expo 待办首页和从待办卡片进入会议详情 actions tab 的导航。底部导航继续复用现有 `BottomNav`。不影响首页、知识库、会议详情数据契约、录音、上传、API、Worker 或分析链路。

## 测试结果

- `npm run typecheck`
- `npm run test:todo-ui`

完整回归将在任务结束前继续执行并记录最终结果。

## 已知限制

- 任务状态更新为只读，因为当前没有普通待办状态更新 API。
- 超期统计基于当前已加载的真实 `/tasks` 数据；如果后续需要全量权威统计，应由后端提供统计字段或统计接口。
- `due_date` / `deadline` 为字符串字段，无法解析的值会安全降级为未设置截止时间且不计入超期。

## 后续建议

- 如产品需要在待办首页直接完成/恢复任务，应先定义正式任务状态更新 API、权限、并发和回滚契约。
- 如待办数据量扩大，应考虑后端提供按状态聚合的统计接口，避免移动端用分页数据自行统计。
