# Mobile Task Search Page

## 开发目标

根据待办搜索原型实现 Expo 移动端独立“搜索任务”页面，并从待办首页搜索按钮进入。

## 背景

待办首页已接入真实 `/tasks` 数据源。此次搜索页需要复用现有 `GET /tasks?q=...` 能力，不新增后端搜索、历史接口或任务状态更新接口。

## 实现方案

- 新增 `TaskSearchScreen`，页面独立展示返回按钮、标题、自动聚焦搜索框、清空按钮、搜索结果和最近搜索。
- 输入非空关键词后，用户点击键盘搜索才调用 `listTasks({ q })`，空关键词不请求接口。服务端 `q` 使用中英文模糊匹配，支持混合关键词拆词，并把常见中文状态/优先级标签映射到存储枚举。
- 使用请求序号和最新关键词引用防止旧请求覆盖新结果。
- 最近搜索使用现有 AsyncStorage 本地保存，最多 10 条，自动去重，支持删除单条和清空全部。
- 搜索结果复用待办卡片视觉语言，展示完成状态、标题、截止时间、来源会议、优先级和状态。
- 有 `meeting_id` 的结果进入现有会议详情 `actions` Tab；缺少来源时弹出安全提示。

## 修改内容

- 新增 `apps/mobile/src/screens/TaskSearchScreen.tsx`
- 修改 `apps/mobile/App.tsx`，新增 `taskSearch` 路由并保持待办首页挂载在搜索页后方
- 修改 `apps/mobile/src/screens/TodoScreen.tsx`，搜索按钮支持进入独立搜索页
- 新增 `apps/mobile/scripts/test-task-search-ui.js`
- 修改 `apps/mobile/package.json` 和 `scripts/test-all.ps1`，接入搜索页结构测试
- 更新移动端 README、变更日志、当前任务和交接文档

## 影响范围

影响 Expo 移动端待办首页搜索入口和新增独立搜索页。底部导航、首页、知识库、会议详情、录音、上传、后端、数据库、Worker、Prompt、RAG、Validator 和六维 Schema 未改动。

## 测试结果

- `npm run typecheck`：通过
- `npm run test:task-search-ui`：通过
- `npm run test:todo-ui`：通过
- `.\scripts\test-all.ps1`：通过

## 已知限制

- 最近搜索仅保存在当前设备本地，不跨设备同步。
- 任务完成状态仍只读，直到移动端可用的正式任务状态更新接口暴露。
- 搜索范围覆盖任务标题、证据文本、负责人、负责人名称、任务状态、优先级和来源会议标题；不提供拼音转中文语义检索。

## 后续建议

- 若后端未来提供权威搜索历史接口，可替换本地 AsyncStorage 历史。
- 若未来暴露任务状态更新接口，可在搜索结果卡片中复用真实更新和失败回滚能力。
