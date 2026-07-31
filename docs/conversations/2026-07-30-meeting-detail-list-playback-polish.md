# Meeting Detail And List Playback Polish

## 开发目标

处理移动端会议纪要详情页和会议列表的四个 UI 体验问题：

- 会议原文单个 speaker 播放 icon 过大。
- 会议列表没有待办时不展示右下角 `无待办`。
- 首页 `全部会议` 下方日期和卡片间距过大。
- 会议纪要详情页顶部播放器点击播放 icon 仍有闪烁。

## 背景

这些问题都集中在 Expo 移动端 UI 层。现有音频播放、会议列表和摘要数据来源可复用，不需要新增后端能力，也不需要修改录音、Worker、Prompt、RAG、Validator、Schema 或数据库。

## 实现方案

在现有 React Native 页面内做最小样式和渲染调整：

- 将会议原文分段播放按钮缩小为 18x18 的透明小按钮，图标尺寸改为 12，视觉上与时间文字接近。
- 仅当会议完成且 `actions > 0` 时渲染右下角待办数量 badge。
- 压缩首页 `全部会议` 标题、日期 header 和第一张会议卡之间的垂直 margin。
- 顶部主播放器保留预加载和播放意图逻辑，但移除主播放按钮内部的 loading spinner 分支，点击后只在 play/pause icon 间切换。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 缩小会议原文分段播放按钮和 icon。
  - 移除顶部播放器主播放按钮的 loading spinner 渲染。
- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 隐藏 0 待办时的右下角 badge。
  - 收紧首页 `全部会议` 区域的日期 header 间距。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 增加分段播放小图标和禁止主播放按钮 spinner 回归的静态检查。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加隐藏 `无待办` 和首页间距收紧的静态检查。

## 影响范围

仅影响移动端会议详情页和会议列表 UI。后端 API、Worker、Prompt、RAG、Validator、Schema、数据库、录音流程、会议详情数据、知识库和待办页面不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-detail-ui.js`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `node scripts/test-meeting-date-sections.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机/Expo 截图验证。顶部播放器真实出声时间仍受音频文件读取、网络和平台播放器初始化影响。

## 后续建议

如果真机仍看到顶部播放器闪烁，需要进一步检查 `LucideIcon` 渲染、Pressable pressed 态或原生播放状态回调是否触发了额外视觉变化。
