# Recording Finish Home Processing Status Fix

## 开发目标

修复实时录音结束后首页会议列表无法立即展示 `处理中` loading 状态的问题，并确认结束录音后强提示 `已进入AI结构化分析` 与 500ms 回首页流程仍然存在。

## 背景

结束录音后已有强提示和后台处理逻辑，但首页会议列表依赖接口刷新。由于录音覆盖层本身在首页内渲染，结束后回到首页时列表组件不会必然重新挂载，刚结束的会议也可能还没有出现在本地列表 state 中，导致 `处理中` 状态和 loading 图标不可见。

## 实现方案

- 在 `App.tsx` 增加 `recordingProcessingMeeting` 本地覆盖状态。
- 结束录音时立即构造一个 `status: processing` 的会议快照并传给会议列表。
- `MeetingListScreen` 接收 `processingRecordingMeeting`，将其合并到当前列表；若本地列表中尚无该会议，则插入列表顶部。
- 复用现有 `StatusBadge`，因此 `处理中` 左侧继续使用既有 `ActivityIndicator` loading 图标。
- 后台上传、转写、分析流程结束后清除覆盖并触发列表刷新。

## 修改内容

- `apps/mobile/App.tsx`
  - 新增 `recordingProcessingMeeting` 和 `meetingListRefreshKey`。
  - 结束录音时立即设置本地 processing 会议覆盖。
  - 后台处理完成后清除覆盖并刷新列表。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 新增 `processingRecordingMeeting` 和 `refreshKey` props。
  - 合并/插入本地 processing 会议，确保首页和全部会议列表立即显示。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加结束录音强提示、500ms 回首页、本地 processing 覆盖和 loading 状态的静态检查。

## 影响范围

仅影响移动端实时录音结束后的首页列表即时展示。录音、上传、转写、AI 分析、后端接口和 Worker 链路不变。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未在真实设备上手动验证 500ms 提示的视觉时长和首页列表动画效果。

## 后续建议

如需更强一致性，可在后台分析任务完成后增加 App 级列表轮询或事件通知，减少用户手动刷新的需求。
