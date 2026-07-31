# Todo 300ms Completion And IME Search

## 开发目标

调整移动端待办完成交互和搜索任务提交方式，使完成状态先有可见过渡，再同步到已完成列表；搜索只由输入法自带搜索按钮提交。

## 背景

待办完成已接入真实状态更新 API，但点击后任务会立即按筛选或排序离开当前位置，用户看不到复选框选中、标题灰色删除线的状态变化过程。搜索页此前仍保留右侧搜索按钮，并且中文输入法提交时需要以最终输入法文本作为查询词。

## 实现方案

- 在 `TodoScreen` 增加 `pendingCompletedTaskIds` 过渡集合。
- 点击复选框或标题完成任务后，立即乐观展示已选中方形复选框、灰色删除线标题。
- 完成 API 成功后等待 300 ms，再移除过渡态；顶部筛选保持用户当前选择，不自动切换到已完成。
- 过渡期间任务不会进入已完成筛选，也不会计入已完成统计，避免列表和统计口径不一致。
- 将顶部第一张统计卡从进行中改为全部任务，统计所有已加载任务。
- 搜索页移除输入框右侧搜索按钮。
- 搜索页通过 `onSubmitEditing` 读取输入法提交事件的最终文本，先同步到搜索框，再调用 `GET /tasks?q=...`。
- 搜索页 `onChangeText` 仍只更新本地输入和清理旧结果，不触发接口请求。

## 修改内容

- `apps/mobile/src/screens/TodoScreen.tsx`
- `apps/mobile/src/screens/TaskSearchScreen.tsx`
- `apps/mobile/scripts/test-todo-ui.js`
- `apps/mobile/scripts/test-task-search-ui.js`
- `docs/CHANGELOG.md`
- `docs/conversations/2026-07-28-todo-500ms-ime-search.md`
- `SESSION_HANDOFF.md`

## 影响范围

影响 Expo 待办首页和任务搜索页。未修改后端业务逻辑、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `npm run typecheck`: 通过
- `npm run test:todo-ui`: 通过
- `npm run test:task-search-ui`: 通过
- `.\scripts\test-all.ps1`: 通过

## 已知限制

- 300 ms 过渡在 API 成功后开始；如果网络很慢，用户会先看到更新中/选中状态，最终同步仍依赖真实接口成功。
- 中文输入法的候选词显示由系统输入法控制，应用只在输入法触发 `onSubmitEditing` 后读取最终提交文本并发起搜索。

## 后续建议

- 真机验证中文输入法搜索时，需点击键盘自带搜索图标，不使用候选联想词作为自动查询触发。
