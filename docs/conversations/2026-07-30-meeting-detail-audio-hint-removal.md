# Meeting Detail Audio Hint Removal

## 开发目标

移除会议纪要详情页顶部播放器点击播放后出现的 `音频加载失败，请确认录音文件仍然存在。` 提示。

## 背景

会议详情页顶部内联播放器维护 `audioState` 和 `audioError`。当没有可播放音频或 `expo-av` 加载失败时，页面通过 `audioHint` 在播放器下方渲染提示。用户反馈该提示不管是否有音频都会出现，影响详情页体验。

## 实现方案

保留现有音频选择、加载、播放、暂停、进度拖动和状态降级逻辑，只移除顶部播放器的错误提示渲染和该具体错误文案赋值。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 移除 `renderAudioPlayer()` 中的 `audioHint` 计算和渲染。
  - 移除不再使用的 `audioHint` 样式。
  - 音频缺失或加载失败时不再写入面向 UI 的错误提示文案。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 不再要求音频错误提示文案存在。
  - 增加禁止 `audioHint`、`styles.audioHint` 和 `audioError ||` 回归的静态检查。
- `apps/mobile/scripts/test-meeting-agent-tools-ui.js`
  - 恢复为稳定 UTF-8 静态检查，保持现有 Agent 工具 tab 覆盖。

## 影响范围

仅影响会议详情页顶部播放器的提示文案展示。音频文件选择、播放控制、会议详情、AI 纪要、Agent 工具、后端 API、Worker、Prompt、RAG、Validator、Schema 和数据库不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-detail-ui.js`：通过。
- `node scripts/test-meeting-agent-tools-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机点击播放截图验证。

## 后续建议

如果后续需要展示音频不可用状态，建议改为非阻塞图标状态或按钮 disabled 态，不在播放器主体下方重复显示长错误文案。
