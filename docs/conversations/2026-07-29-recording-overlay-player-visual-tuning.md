# Recording Overlay Player Visual Tuning

## 开发目标

根据录音覆盖层最新视觉反馈，微调顶部左侧收起按钮、底部声纹和计时器的尺寸与间距。

## 背景

当前首页内实时录音覆盖层已经完成直接结束录音、强提示返回首页和底部播放器精简。本次只针对视觉细节做最小改动，不调整录音、上传、分析、路由或会议状态链路。

## 实现方案

- 将顶部左侧收起按钮整体上移，使其更接近顶部控件对齐位置。
- 将声纹柱从 12 条改为 10 条。
- 将声纹容器、柱宽和迷你条声纹按约 70% 缩小。
- 将完整播放器计时器字号从 24 调整为 22，迷你条计时器从 17 调整为 15。
- 收紧声纹与计时器之间的水平间距。
- 继续将左上角收起按钮、录音状态/标题/创建时间文案组向上微调，并进一步收紧声纹与计时器间距。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
- 更新 `waveform` 数组为 10 条。
  - 调整 `sheetTopRow`、`soundprintRow`、`timerLarge`、`waveform`、`waveformCompact`、`waveBar`、`waveBarCompact`、`miniWaveBlock`、`miniTimer` 样式。
  - 微调 `titleBlock` 上间距，使中部文案整体上移。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 更新声纹数组静态断言。
- `docs/CHANGELOG.md`
  - 同步底部播放器声纹数量说明。
- `SESSION_HANDOFF.md`
  - 同步当前录音覆盖层状态说明。
- `docs/conversations/2026-07-29-recording-overlay-direct-finish-ui-simplification.md`
  - 修正上一份记录中的声纹数量。

## 影响范围

仅影响移动端实时录音覆盖层和迷你录音条的视觉呈现。录音实例、暂停/继续、停止、上传、AI 分析和首页状态展示链路不变。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

尚未在真实 iPhone 或 Android 设备上做视觉截图验证。

## 后续建议

如继续做像素级调整，建议在真实设备或 Expo Go 截图上确认顶部安全区、BottomNav 和迷你条间距。
