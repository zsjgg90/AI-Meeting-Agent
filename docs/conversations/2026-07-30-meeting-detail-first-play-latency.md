# Meeting Detail First Play Latency

## 开发目标

优化会议纪要详情页顶部播放器首次点击播放的体验，避免播放 icon 闪烁并等待约 500ms 后才切换为暂停 icon。

## 背景

详情页顶部播放器原本在首次点击播放时才创建并加载 `Audio.Sound`。加载期间按钮处于 `loading` 状态，视觉上会先显示 loading，再等待 native playback status 回调后切换为暂停 icon，导致用户感知播放延迟。

## 实现方案

复用现有详情页播放器和 `expo-av` 生命周期，不新增播放器、不新增音频业务状态。进入详情页并选中可播放音频后后台预加载 `Audio.Sound`；如果用户在预加载未完成时点击播放，则复用同一个加载 Promise 继续执行播放。点击播放时记录播放意图并立即显示暂停 icon，失败时回退为非播放态。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 增加 `soundLoadingPromiseRef`，让预加载和用户点击共享同一个音频加载 Promise。
  - 增加 `pendingPlayIntentRef`，点击播放后立即反馈暂停 icon，避免等待 status 回调。
  - 页面进入后对选中的音频文件执行后台预加载。
  - 播放按钮不再因为 `audioState === 'loading'` 被禁用。
  - 加载中且已有播放意图时显示暂停 icon，而不是 loading 闪烁。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 增加静态检查，防止首次播放优化相关逻辑被误删。

## 影响范围

仅影响会议详情页顶部播放器的首次播放交互。音频文件选择、播放/暂停、进度、会议详情、AI 纪要、Agent 工具、后端 API、Worker、Prompt、RAG、Validator、Schema 和数据库不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-detail-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机/Expo 点击播放延迟实测。真实出声时间仍受音频文件读取、网络和平台播放器初始化影响。

## 后续建议

如果真机仍感知明显出声延迟，可以继续在详情页骨架加载完成后更早触发音频 metadata 预取，或对本地/远程音频缓存策略单独优化。
