# 实时录音迷你条自然拖拽优化

## 开发目标

优化实时录音折叠条的拖拽体验：顶部提示从箭头改为横杠，拖动目标从图标扩展为整个悬浮录音条模块。

## 背景

上一版折叠条顶部使用上箭头图标，并将拖动手势主要绑定在顶部小区域。实际交互不够自然，用户预期是整个底部录音模块都可以拖动，顶部横杠只作为可拖动提示。

## 实现方案

保留同一 `RecordingScreen` 内展开/折叠状态切换，不引入路由跳转。将 `miniPanResponder.panHandlers` 绑定到整个 `miniBar`，顶部改为纯横杠 `miniDragHandle`。点击主体仍可展开，上拉任意模块区域也可展开。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 将折叠态拖拽手势绑定到整个 `miniBar`。
  - 将顶部箭头图标替换为横杠提示。
- `apps/mobile/src/components/LucideIcon.tsx`
  - 移除不再使用的 `chevron-up` 图标支持。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加整个模块拖动和横杠提示静态检查。
  - 禁止折叠录音条继续使用箭头拖拽提示。

## 影响范围

仅影响移动端实时录音折叠条的拖拽交互和视觉提示。不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、会议 API、会议详情、知识库或待办。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

当前验证仍以静态检查和类型检查为主，未在真机上验证拖动阻尼和阈值手感。手势阈值后续可按设备反馈调整。

## 后续建议

如后续继续优化手感，可在真机上比较上拉距离、速度阈值和回弹动画参数。
