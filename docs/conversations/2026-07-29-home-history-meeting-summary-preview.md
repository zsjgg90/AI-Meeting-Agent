# Home And History Meeting Summary Preview

## 开发目标

在首页会议列表原有 `会议议程`、`核心结论`、`待办任务` 预览上新增 `会议总结` 字段，并将历史会议页面统一为和首页列表一致的卡片展示。

## 背景

首页 compact 会议卡片已经展示 AI 结构化结果中的会议议程、核心结论和待办任务。历史会议页面使用另一套列表卡片，只显示状态、元信息和统计项，缺少首页的 AI 预览区域，造成两个列表体验不一致。

## 实现方案

- 新增 `summaryPreviewText()`，优先读取 `summary.meeting_summary`，其次读取 legacy `summary.overview`。
- 首页 compact 卡片的完成态预览区域新增 `会议总结：`，与会议议程、核心结论、待办任务使用同样的单行预览逻辑。
- 历史会议页面的 `MeetingCard` 改为传入 `compactHome={true}` 和 `summary={summaryByMeeting[item.id]}`，复用首页同款卡片结构。
- summary 加载逻辑从仅首页扩展为当前可见会议，历史分页列表也能加载已完成会议的摘要预览。
- 历史页保留原有选择、分页、刷新和左滑删除行为。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 新增 `summaryPreviewText()`。
  - 首页卡片新增 `会议总结` 预览行。
  - 历史页复用首页 compact 卡片。
  - 扩展 summary 加载逻辑到当前可见列表。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加历史页和首页卡片统一展示的静态检查。

## 影响范围

仅影响移动端首页会议列表和历史会议列表的卡片展示。会议详情、上传、录音、AI 分析、后端接口和 Worker 链路不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `npm run test:recording-upload-ui`：通过。

## 已知限制

未做真实设备截图验证；历史页在大量已完成会议场景下会按当前可见分页加载 summary，后续可按性能情况增加更细粒度缓存。

## 后续建议

如历史页需要和首页完全一致的 header 和空态，也可以后续单独收敛页面外层布局。
