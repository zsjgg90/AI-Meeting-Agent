# Recording Mini Bar Timer Stability

## 开发目标

修复首页悬浮录音条和实时录音播放器计时器回退、抖动、被截断为省略号，以及暂停/继续点击反馈延迟的问题。

## 背景

实时录音页同时存在展开态播放器和折叠态悬浮录音条。此前计时显示既会被 JS wall-clock 定时器更新，也会被 `Audio.Recording` 的 native status 回调按 `durationMillis` 更新，暂停/继续时两个来源可能出现短暂不一致，造成 `9 -> 8 -> 9` 这类回退观感。折叠态计时文本宽度也不足，截图中显示为 `00:00:...`。

## 实现方案

- 保留现有 `RecordingScreen` 和全局录音会话，不新增录音页面或录音状态。
- 计时只由 JS 累计时钟驱动：`elapsedBeforeResumeSeconds + 当前录音段 wall-clock`。
- `Audio.Recording` status 回调只更新 metering 声纹电平，不再参与计时。
- 暂停/继续点击后先更新 UI 状态，再等待原生 `pauseAsync()` / `startAsync()`，失败时回滚状态。
- 播放/暂停按钮在暂停/继续原生操作期间不切换 spinner，不因 busy 状态变灰，减少闪烁。
- 录音计时显示改为 1 小时内 `MM:SS`，超过 1 小时显示 `HH:MM:SS`。
- 展开态和折叠态计时器使用 tabular numbers 和固定宽度，折叠态波形与计时器保持同一行。
- 折叠态悬浮录音条高度降低约 15%，但保留播放/停止按钮原有点击尺寸。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 移除 native `status.durationMillis` 对显示计时的写入。
  - 调整暂停/继续为即时 UI 反馈，并增加失败回滚。
  - 调整计时格式和播放器/悬浮条布局宽度。
  - 将折叠态 `miniBar` / `miniPanel` 高度从 `140` 调整为 `120`，内容行从 `95` 调整为 `81`。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加禁止 `status.durationMillis` 写计时的静态检查。
  - 更新计时格式、按钮反馈和悬浮条布局回归检查。
- `docs/CHANGELOG.md`
  - 记录本次录音计时稳定性修复。

## 影响范围

仅影响移动端实时录音 Overlay 和首页悬浮录音条的显示与交互反馈。不修改 API、Worker、Prompt、RAG、Validator、Schema、数据库、会议详情、知识库、待办和会议列表业务逻辑。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

尚未在真实手机或 Expo 设备上做人工录音 smoke test。当前修复基于代码路径和静态/类型回归。

## 后续建议

在真机上按真实使用流程验证：开始录音，观察 8-12 秒，暂停 3 秒，继续录音，再折叠/展开，确认计时不回退、不省略、不横向抖动。
