# Home Meeting List Duplicate Date Label Fix

## 开发目标

修复首页 `全部会议` 区域同时显示 `7月30日 今天` 和 `7月30日 周四` 这类重复日期的问题。

## 背景

首页会议列表已经使用 `groupMeetingsByDate` 生成日期分组，并通过 `SectionList` 的 section header 展示日期。`全部会议` 标题区还额外渲染了当天日期，因此同一天会出现两种日期表达。

## 实现方案

保留会议列表的日期分组 header 作为唯一日期来源，移除 `全部会议` 标题区下方的额外日期副标题。不修改会议分组、排序或 API 数据。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 删除首页 `全部会议` 标题区的 `recentDate` 日期文案。
  - 删除不再使用的 `formatHomeSectionDate()`。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加静态检查，禁止首页会议列表重新渲染第二个日期标签。
- `docs/CHANGELOG.md`
  - 记录本次 UI 修复。

## 影响范围

仅影响首页会议列表标题区视觉文案。会议列表按日期分组、全部会议页、会议卡片、录音、知识库、待办、会议详情、后端、Worker、Prompt、RAG、Validator、Schema 和数据库不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机截图验证。

## 后续建议

如后续需要在标题区展示日期，应与 section header 合并设计，避免同屏重复表达同一天。
