# Realtime Recording Save And Pending Badge Fix

## 开发目标

修复实时录音进入后结束录音无法保存的问题，并移除首页会议列表未录音状态下的 `未生成摘要` 状态提示。

## 背景

实时录音结束保存依赖 `expo-av` 的本地录音 URI。此前停止录音后才读取 URI，并且如果本地计时状态小于 1 秒会直接走 `onDiscard()` 删除会议。由于录音状态回调并不保证在用户点击结束前已经更新到 1 秒，该判断可能误删有效录音和会议。

首页 compact 会议卡片会对 `pending` 会议渲染状态徽标，显示为 `未生成摘要`，这不符合未录音状态下的展示要求。

## 实现方案

- 在 `RecordingScreen.stopRecording()` 中先读取 `activeRecording.getURI()`，再执行 `stopAndUnloadAsync()`。
- 移除 `elapsedSecondsRef.current < 1` 时自动放弃录音的判断。
- 只有真实没有 URI 时才停留并提示 `录音文件保存失败。`，不再删除会议。
- 首页 compact 会议卡片在 `pending` 状态下不渲染顶部状态徽标。
- 更新录音 UI 静态检查，防止重新引入按本地计时丢弃录音的逻辑。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 停止录音前读取本地 URI。
  - 删除小于 1 秒自动 `onDiscard()` 的保存拦截。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 首页 compact 卡片隐藏 `pending` 状态徽标。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加 URI 读取顺序和 pending 徽标隐藏的静态检查。

## 影响范围

仅影响移动端实时录音保存可靠性和首页会议卡片 pending 状态展示。上传、转写、AI 分析、后端接口、Worker 和文件导入链路不变。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未在真实 iOS/Android 设备上录一段音频做端到端手动验证。

## 后续建议

如果仍遇到极短录音无法上传，可在上传前增加文件存在性和大小检测，并在 UI 中给出可恢复的重试入口。
