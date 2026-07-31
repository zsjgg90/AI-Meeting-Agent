# Home Meeting List Date Sections

## 开发目标

将 MeetMind AI 首页和全部会议列表从纯时间倒序卡片流调整为按用户本地自然日分组展示。

## 背景

RC1 首页“全部会议”需要参考当前移动端视觉稿显示日期分组标题。分组必须基于真实会议开始时间，不能按 UTC 字符串截断，并且不能影响现有会议卡片、刷新、分页、选择、滑动删除、会议详情跳转或录音迷你条。

## 实现方案

- 新增 `apps/mobile/src/utils/meetingDateSections.ts`，把日期 key、今天/昨天判断、标题生成、分组和排序提取为纯函数。
- `MeetingListScreen` 改用 `SectionList` 渲染首页和全部会议列表。
- 分组字段使用 `start_at`，缺失时回退 `created_at`；无效时间进入 `时间未知`。
- 本地 `Date` getter 生成自然日 key，避免直接截断 UTC 日期。
- 组件设置本地午夜后的 timer，触发 section 标题从“今天”变为“昨天”。
- 录音迷你条显示时，首页和全部会议列表都增加底部 content padding。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 引入 `SectionList` 和日期分组工具。
  - 派生 `meetingSections` 并渲染 section header。
  - 卡片时间显示改为 `start_at || created_at`。
  - 增加本地午夜刷新和迷你条底部 padding。
- `apps/mobile/src/utils/meetingDateSections.ts`
  - 新增可测试日期分组纯函数。
- `apps/mobile/scripts/test-meeting-date-sections.js`
  - 覆盖日期标题、排序、UTC 跨日、午夜变化、空列表和无效时间降级。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加 `SectionList`、section header 和迷你条 padding 静态检查。
- `apps/mobile/package.json`
  - 增加 `test:meeting-date-sections`。
- `scripts/test-all.ps1`
  - 默认移动端检查接入日期分组测试。

## 影响范围

仅影响 Expo 移动端首页/全部会议列表展示和移动端测试脚本。未修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema 或会议 API。

## 测试结果

- `npm run test:meeting-date-sections`：通过。
- `node apps/mobile/scripts/test-meeting-history-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

日期解析仍依赖 JavaScript/React Native 对 API 时间字符串的标准解析行为。带明确时区的 ISO 字符串可以稳定转换为用户本地自然日；无效或无法解析的值会进入 `时间未知`。

## 后续建议

如果后续 API 明确返回无时区本地时间字符串，建议在 API 合约中声明其时区语义，避免不同 JS Runtime 解释差异。
