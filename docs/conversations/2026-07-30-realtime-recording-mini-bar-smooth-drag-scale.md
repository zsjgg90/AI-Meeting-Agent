# 实时录音迷你条丝滑拖拽与控件放大

## 开发目标

进一步优化实时录音折叠条的真实使用手感，并将声纹、计时器、播放按钮和结束按钮视觉尺寸放大约 25%。

## 背景

上一版已支持整个悬浮录音条上拉展开，但手势一开始就接管触摸，点击和拖动边界偏硬。折叠态声纹、计时器和控制按钮相对底部覆盖条偏小。

## 实现方案

折叠条拖动改为用户出现明确纵向位移后再接管手势，避免普通点击被过早拦截。上拉和下压位移加入阻尼，并在拖动时给模块轻微缩放反馈；未触发展开时使用更柔和的 spring 回弹。折叠态声纹、计时器和控制按钮通过 compact waveform、字号、动作区 scale 和条高同步放大。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - `miniPanResponder` 改为移动后接管，纵向优先。
  - 上拉/下压加入不同阻尼。
  - 回弹 spring 改为 `tension: 170`、`friction: 20`。
  - 增加 `miniScale` 拖动反馈。
  - 折叠态声纹、计时器、播放/停止按钮和条高放大。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加手势阻尼、回弹参数、缩放反馈和放大尺寸静态检查。

## 影响范围

仅影响移动端实时录音折叠条的手势体验和视觉尺寸。不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、会议 API、会议详情、知识库或待办。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

当前没有真机手势录屏验证。阻尼、展开阈值和 spring 参数是按移动端常见手感做的保守调优，后续仍可根据真实设备反馈继续微调。

## 后续建议

在 iOS 和 Android 真机分别验证：轻点展开、短距离上拉回弹、快速上滑展开、横向误触不抢手势。
