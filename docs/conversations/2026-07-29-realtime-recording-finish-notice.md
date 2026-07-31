# Realtime Recording Finish Notice

## 开发目标

优化移动端实时录音结束后的反馈：点击结束会议后先显示强提示“已进入AI结构化分析”，等待 500ms 后返回首页，并在会议列表“处理中”状态左侧显示 loading 图标。

## 背景

实时录音结束流程已改为直接停止录音并返回首页，上传、转写和 AI 结构化分析在移动端后台流程启动。用户需要在离开录音页前得到明确反馈，并能在首页列表中更直观看到会议仍在处理。

## 实现方案

在 `App.tsx` 录音结束回调中显示全局 modal 提示，启动后台处理流程后延迟 500ms 清理录音会话并返回首页。会议列表抽出 `StatusBadge` 小组件，只对 `recording` 和 `analyzing` 状态在状态文字左侧显示小型 `ActivityIndicator`。

## 修改内容

- `apps/mobile/App.tsx`
  - 新增 `recordingAnalysisNoticeVisible` 状态和 500ms 定时器清理。
  - 录音结束后显示“已进入AI结构化分析”强提示。
  - 500ms 后返回首页，不阻塞后台 `uploadAudio -> processMeeting -> analyzeMeeting`。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 新增 `StatusBadge`。
  - `recording` 和 `analyzing` 的“处理中/分析中”状态左侧显示 loading。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加提示、500ms 回首页和列表 loading 的静态检查。
- `docs/CHANGELOG.md`
  - 记录本次体验调整。

## 影响范围

影响移动端实时录音结束反馈和会议列表状态徽标。录音对象、上传 API、转写 API、AI 分析 API、后端、数据库、Worker、Prompt、RAG、Validator 和六维 Schema 未改变。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。

## 已知限制

会议列表的数据刷新仍依赖现有列表加载和刷新机制；loading 图标只表达当前列表项状态为处理中，不新增实时推送。

## 后续建议

如后续要求状态即时刷新，可单独评估首页列表轮询或后台任务状态订阅。
