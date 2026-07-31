# Meeting Transcript Player Refactor

## 开发目标

根据 `docs/design/meetmind-app_meeting-detail.html` 重构 Expo 移动端会议详情中的“会议原文”页面，并完善详情页内录音播放、时间戳跳转、会议速览和原文导出入口。

## 背景

原会议详情页在同一个 `ScrollView` 内混合展示摘要、原文和多维度内容，会议原文直接 map 渲染全部转写分段，播放器能力分散在详情页片段播放和独立 `AudioPlayerScreen` 中。本阶段只调整移动端会议原文体验，不修改 API、Worker、数据库、Prompt、RAG、Validator 或六维 Schema。

## 实现方案

- 使用 React Native/Expo 样式实现原型视觉层级，不复用 Tailwind、Iconify、HTML 跳转或固定 iPhone 外壳。
- 详情页改为单个垂直 `FlatList`，播放器、标签栏、会议速览和导出入口放入 `ListHeaderComponent`，转写分段作为列表项渲染。
- 音频继续使用 `expo-av` 和现有 `meetingAudioUrl(meeting.id, audioFile.id)`。
- 会议速览只从真实 `transcript_segments` 派生，分段不足时显示空状态，不伪造章节标题。
- AI 纪要入口保留现有 summary 数据渲染，Agent 工具保留占位。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 新增页内顶部导航、音频播放器、三标签栏、会议速览、导出文稿入口和时间轴式原文列表。
  - 支持播放/暂停、拖动进度、前后 15 秒、时间戳跳转、片段播放、片段播放中再次点击暂停、播放到片段结束自动暂停和当前片段轻量高亮。
  - 处理页面加载、会议不存在、音频加载中、音频缺失、音频失败、转写处理中、转写为空和导出失败等状态。
- `apps/mobile/App.tsx`
  - 详情页不再使用全局 `AppHeader`，改为传入既有 `handleBack` 导航逻辑。
- `apps/mobile/src/components/LucideIcon.tsx`
  - 增加详情页需要的 `share-2`、`more-horizontal`、`play`、`pause` 图标。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 更新静态 UI 检查，覆盖新详情页结构、播放器能力、导出入口和禁止项。
- 文档更新：`apps/mobile/README.md`、`docs/CHANGELOG.md`、`docs/CURRENT_TASKS.md`、`SESSION_HANDOFF.md`。

## 影响范围

- 影响 Expo 会议详情页的移动端 UI 和详情页内音频播放体验。
- 不影响首页、录音、上传、AI 处理、后端接口、Worker、Prompt、RAG、Validator、数据库和现有 AI 纪要数据逻辑。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `npm run test:knowledge-base-ui`：通过。
- `npm run test:recording-upload-ui`：通过。
- `npm run test:meeting-history-ui`：通过。
- `node scripts/test-ai-processing-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

- 当前没有独立 chapter/topic segment API 字段，会议速览只能从真实转写分段派生；分段不足时显示空状态。
- 导出入口依赖现有 API `GET /meetings/{id}/exports/transcript.{format}`，移动端不新增本地导出实现。
- 详情页内音频测试当前以 TypeScript 和静态结构检查为主，未新增端到端真机自动化音频播放断言。

## 后续建议

- 后端如后续提供正式章节/议题时间戳字段，可替换当前 transcript-derived 速览逻辑。
- 可在已有移动端自动化能力稳定后补充真机/模拟器播放器交互测试。
