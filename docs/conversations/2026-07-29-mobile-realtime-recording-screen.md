# Mobile Realtime Recording Screen

## 开发目标

根据 `docs/design/meetmind-app_meeting-recording.html` 重构移动端实时录音页，并保持首页实时录音自动创建会议、录音结束后上传音频、转写、AI 结构化分析和 AI 自动标题更新的现有链路。

## 背景

首页实时录音入口已经改为直接创建 `YYYY-MM-DD HH:mm 实时录音` 默认标题会议并进入 `RecordingScreen`，后端和 Worker 已通过 `title_source` 与 `meeting_title` 支持只替换未被用户编辑的默认标题。录音页仍偏旧：需要手动开始录音，结束确认文案不符合新流程，返回/收起缺少放弃确认，声纹未尝试使用 metering。

## 实现方案

保留现有 `expo-av` 录音对象和 `AIProcessingScreen` 上传、处理、分析流程，不新增流式 ASR、WebSocket 移动端推流、后端接口、数据库迁移、Prompt、RAG、Validator 或六维 Schema 变更。录音页进入后自动启动真实录音，页面内处理暂停、继续、结束确认和放弃确认。自动创建会议的时间戳标题和展示创建时间使用同一个本地 `Date`。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 重构为原型对应的 React Native 页面结构：顶部收起按钮、状态、默认标题、创建时间、转写提示区、计时器、声纹、暂停/继续、结束按钮和确认弹窗。
  - 进入页面后自动调用现有 `Audio.Recording` 开始录音。
  - 暂停调用 `pauseAsync()`，继续调用 `startAsync()`，停止调用 `stopAndUnloadAsync()`。
  - 使用 `isMeteringEnabled: true` 并读取 `status.metering`，无 metering 时退化为状态动画。
  - 增加 `busyRef` 和 `stoppingRef`，避免快速点击导致重复停止或重复进入处理。
  - 不显示原型里的静态说话人和示例转写，明确提示录音结束后生成转写和 AI 纪要。
  - 放弃录音或小于 1 秒的无效录音走会议删除清理。
- `apps/mobile/App.tsx`
  - 自动创建实时录音会议时传入同一时间生成的默认标题和 `start_at`。
  - `recordingSession` 保存创建时间并传给录音页展示。
  - 录音页不再显示旧全局 AppHeader，放弃录音由 `RecordingScreen` 确认后触发清理。
- `apps/mobile/src/screens/AIProcessingScreen.tsx`
  - 顶部会议标题优先使用轮询到的最新 `meetingDetail.title`，AI 标题更新后处理页可显示新标题。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 扩展静态检查，覆盖直建会议、自动开始、真实暂停/继续/停止、结束确认、放弃确认、无假转写、metering 和空录音清理。
- `README.md`
  - 更新端到端流程和实时字幕说明，明确当前移动端录音页不展示实时字幕。
- `docs/CURRENT_TASKS.md`
  - 更新 RC1 录音流程稳定性说明。
- `docs/CHANGELOG.md`
  - 记录本次录音页重构。
- `SESSION_HANDOFF.md`
  - 补充最新录音页行为和实时 ASR 状态。

## 影响范围

影响移动端首页实时录音入口和 `RecordingScreen` 交互。上传、处理、分析、会议详情、会议列表、知识库、待办、文件导入、API 合同、数据库、Worker 正式分析链路、Prompt、RAG、Validator 和六维 Schema 未改变。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

当前 Expo 移动端依赖中没有 `@siteed/audio-studio`，没有实现 PCM/WebSocket 推流，因此录音过程中不展示实时 ASR 或实时说话人分离。声纹优先使用 `expo-av` metering；当平台不返回 metering 时使用轻量状态动画。

## 后续建议

如后续要恢复真实实时字幕，应在 Development Build 中引入原生 PCM 音频流模块，并单独设计移动端 WebSocket 推流、临时/最终转写去重、高性能列表和实时说话人颜色稳定策略。
