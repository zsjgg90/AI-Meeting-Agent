# History Meeting List Title Count And Spacing

## 开发目标

调整移动端 `历史会议` 页面：将会议数量移动到标题后，移除单独的 `共 n 场会议` 文案，将 `选择` 颜色改为黑色，并收紧历史会议列表顶部间距。

## 背景

原历史会议页在 AppHeader 下方单独显示 `共 n 场会议`，并在右侧显示紫色 `选择` 按钮。截图反馈中该区域占用高度偏大，列表日期分组和首张会议卡片整体偏下。

## 实现方案

让历史会议列表通过可选回调把当前已加载会议数量回传给 `App.tsx`，由顶部 AppHeader 显示 `历史会议（n）`。历史页内部移除独立统计文案，只保留右侧选择按钮，并为历史页添加专用紧凑容器、列表内容和日期标题样式。

## 修改内容

- `apps/mobile/App.tsx`
  - 增加 `historyMeetingCount` 状态。
  - `allMeetings` 标题显示为 `历史会议（n）`。
  - 向历史会议列表传入 `onMeetingCountChange`。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 增加可选 `onMeetingCountChange` 属性。
  - 移除单独 `共 n 场会议` 文案。
  - 历史页选择和全选文字改为黑色。
  - 新增历史页专用紧凑间距样式。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加标题计数、移除独立统计文案、黑色选择控件和紧凑样式静态检查。
- `services/api/tests/test_agent_confirmation_api.py`
  - 将有效 bearer token 测试夹具的默认过期时间从固定时间改为当前时间后一天，修复 `2026-07-30T12:00Z` 后默认测试过期的问题。

## 影响范围

主要影响移动端历史会议列表 UI 和对应静态检查。另包含一个 API 测试夹具时间稳定性修正，不修改运行时代码、会议分页、API 合同、后端业务逻辑、Worker、数据库、Prompt、RAG、Validator、Schema 或会议分析链路。

## 测试结果

已执行并通过：

- `npm run typecheck`
- `node scripts/test-meeting-history-ui.js`
- `.\scripts\test-all.ps1`

## 已知限制

标题中的数量来自当前移动端已加载列表数量；现有 `GET /meetings` 返回数组而非总数，因此本次不新增总数接口或后端字段。

## 后续建议

如果后续需要展示全库总数而非已加载数量，应先扩展列表 API 返回 `total`，再调整移动端标题计数来源。
