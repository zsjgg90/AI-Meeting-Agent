# Realtime Recording Direct Finish

## 开发目标

调整移动端实时录音结束流程：点击结束录音后直接停止录音并返回首页，不再弹出结束确认，也不再进入 AI 处理页面。用户通过首页会议列表查看上传、转写和 AI 分析状态。

## 背景

实时录音页此前复用 `AIProcessingScreen`，结束录音前需要二次确认，确认后进入处理页等待上传、转写和纪要生成。最新交互要求实时录音更轻量：结束即回首页，处理状态由会议列表承载。

## 实现方案

保留 `RecordingScreen` 的真实 `expo-av` 录音对象和快速点击防护。结束按钮直接调用停止逻辑；返回/收起仍保留放弃录音确认。录音结束后由 `App.tsx` 清理当前录音会话、切回首页，并启动录音专用后台流程，依次复用 `uploadAudio`、`processMeeting` 和 `analyzeMeeting`。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 移除结束录音按钮触发的二次确认路径。
  - 结束按钮直接调用 `stopRecording`，仍通过 `stoppingRef` 防止重复停止和重复上传。
  - 确认弹窗仅用于返回/收起时放弃录音。
- `apps/mobile/App.tsx`
  - 新增 `runRecordingProcessingInBackground`。
  - 录音结束后立即 `setRoute({ name: 'home' })`。
  - 后台补写 `end_at`，上传音频，等待真实转写片段后触发 AI 结构化分析，并等待摘要完成或失败状态。
  - 文件导入继续使用 `AIProcessingScreen`。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 更新静态检查，覆盖录音结束直接回首页和后台处理链路。
  - 不再要求结束确认弹窗。
- `README.md`、`docs/CHANGELOG.md`、`docs/CURRENT_TASKS.md`、`SESSION_HANDOFF.md`
  - 同步实时录音结束后的新流程。

## 影响范围

影响移动端实时录音结束后的导航与处理触发位置。录音、暂停、继续、停止、上传、转写、AI 分析 API、会议列表、会议详情、文件导入、后端、数据库、Worker、Prompt、RAG、Validator 和六维 Schema 未做结构性变更。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。

## 已知限制

实时录音结束后处理流程在移动端前台 JavaScript 中启动；如果应用在上传或排队前被系统终止，可能需要用户稍后通过首页状态和现有重试能力处理。当前任务未新增后端常驻上传队列。

## 后续建议

如需更强的离开应用可靠性，应单独评估原生后台上传或后端接管队列，不应混入本次 UI 流程调整。
