# 实时录音迷你条底部覆盖布局

## 开发目标

将实时录音折叠后的悬浮录音条改为贴屏幕底部的全宽覆盖条，左右铺满，并通过足够高度覆盖底部菜单导航。

## 背景

当前底部菜单已经固定到屏幕最底部。实时录音折叠条仍使用较窄的浮层样式并位于底部菜单上方，不符合参考图中录音状态下底部区域由录音条接管的视觉要求。

## 实现方案

保持现有实时录音状态、展开/折叠交互、停止录音、后台上传分析流程不变，只调整 `RecordingScreen` 中折叠态 `miniBar` 的布局样式。录音条改为 `bottom: 0`、`left: 0`、`right: 0`，提高 `minHeight` 和层级，使其覆盖底部导航。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 将折叠录音条改为全宽底部覆盖层。
  - 调整顶部圆角、顶部内边距、阴影方向、`zIndex` 和 `elevation`。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加 `miniBar` 样式静态检查，防止回退到旧的窄浮层布局。

## 影响范围

仅影响移动端实时录音折叠态迷你条的视觉位置和尺寸。不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、会议 API、会议详情、知识库或待办。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

本次为静态布局和类型验证，未在真实设备上做不同机型安全区截图回归。当前实现依赖 React Native 绝对定位和原生层级属性覆盖底部导航。

## 后续建议

后续如继续调整底部菜单高度，需要同步检查折叠录音条 `minHeight` 是否仍能完整覆盖菜单区域。
