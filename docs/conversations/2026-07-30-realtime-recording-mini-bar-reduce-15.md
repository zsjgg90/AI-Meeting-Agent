# 实时录音迷你条高度和控件降低 15%

## 开发目标

将实时录音折叠条整体高度降低约 15%，并将声纹、计时器、播放/暂停和结束按钮在当前基础上同步降低约 15%。

## 背景

上一版为增强可操作性将折叠态控件放大，并引入固定底部遮挡层避免上拉时露出底部导航。实际视觉权重偏大，需要回调一档，同时保留固定遮底结构。

## 实现方案

保留 `miniBar` 固定覆盖底部导航、`miniPanel` 跟随拖动的结构，只调整尺寸参数。高度从 `164` 降到 `140`，compact 声纹、计时字号和操作按钮缩放按约 0.85 系数回调。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - `miniBar` / `miniPanel` 高度调整为 `140`。
  - compact 声纹调整为 `60 x 24`。
  - compact 声纹条高度调整为 `Math.max(9, baseHeight * 0.61)`。
  - 计时器字号调整为 `20`。
  - 播放/暂停和结束按钮折叠态缩放调整为 `1.01`。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 同步更新静态 UI 尺寸断言。

## 影响范围

仅影响移动端实时录音折叠条的高度和折叠态控件尺寸。不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、会议 API、会议详情、知识库或待办。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

当前仍未进行真机视觉回归。不同屏幕宽度下控制按钮间距可能需要继续按实机微调。

## 后续建议

在真机上验证折叠条高度是否仍能完整覆盖底部导航，并检查大字号计时器和右侧按钮是否在窄屏下保持间距。
