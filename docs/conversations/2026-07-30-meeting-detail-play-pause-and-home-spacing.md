# Meeting Detail Play Pause And Home Spacing

## 开发目标

修正会议纪要详情页顶部播放器播放/暂停逻辑，并将首页 `全部会议` 下方模块间距从过紧状态稍微放开。

## 背景

详情页顶部播放器为优化首次播放体验引入了预加载和 `pendingPlayIntentRef`。检查后发现一个边界问题：首次播放仍在加载时再次点击，原逻辑会被 `audioBusyRef` 直接忽略，待播放意图没有取消，加载完成后仍可能开始播放，造成暂停操作不生效的体验。

首页 `全部会议` 区域前一次调整压缩了标题、日期 header 和会议卡片之间的距离，视觉上偏紧，需要略微恢复呼吸感。

## 实现方案

- 顶部播放器在 `audioState === 'missing'` 时直接返回。
- 如果音频操作正在进行中且存在待播放意图，第二次点击会取消 `pendingPlayIntentRef` 并立即回到非播放态。
- 真正执行 `playAsync()` 前再次确认待播放意图仍然存在，避免加载完成后执行已取消的播放。
- 将首页 `recentHeader` 和 `meetingDateHeader` 的 margin 从极紧凑值略微调大。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 修正首次加载期间二次点击不能取消播放的问题。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 微调首页 `全部会议` 区域的标题、日期和卡片间距。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 增加加载中取消播放意图的静态检查。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 同步首页间距静态检查。

## 影响范围

仅影响移动端会议详情页顶部播放器交互和首页会议列表局部间距。未修改后端 API、Worker、Prompt、RAG、Validator、Schema、数据库或录音流程。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-detail-ui.js`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `node scripts/test-recording-upload-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机/Expo 点击播放、暂停的手动验证；真实出声时间仍受音频文件读取和平台播放器初始化影响。

## 后续建议

如果真机仍出现状态错乱，下一步应加一个小型播放器状态机测试，覆盖 idle/loading/ready/playing/paused/failed 的点击序列。
