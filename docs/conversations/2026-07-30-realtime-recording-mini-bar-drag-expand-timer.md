# 实时录音迷你条拖动展开与计时修复

## 开发目标

为实时录音折叠条顶部增加可拖动图标，向上拖动后恢复到折叠前的录音页；调整折叠条内容对齐，并修复折叠态计时器不跳动的问题。

## 背景

实时录音折叠条已改为底部全宽覆盖层，但缺少明确的上拉恢复入口。折叠态内容与播放控制不够对齐，计时器依赖 `expo-av` 原生录音状态回调，在部分状态下可能不继续刷新。

## 实现方案

保持 `RecordingScreen` 同一个实例挂载，不引入路由跳转。折叠态新增顶部 `chevron-up` 拖动手柄，使用 `PanResponder` 识别上拉手势并调用现有 `onExpand`。折叠条主体拆为居中的内容行，使声纹、计时器、播放/停止控制垂直对齐。计时器增加基于 JS wall-clock 的定时兜底，在录音中每 250 ms 刷新一次，并在暂停、继续、结束时同步累计秒数。

## 修改内容

- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 新增折叠态上拉手柄和 `miniPanResponder`。
  - 折叠态上拉恢复展开页，仍在同一个录音 overlay 内完成。
  - 调整 `miniContentRow` 让计时器与播放控制对齐。
  - 新增计时器 wall-clock 兜底，避免只依赖 `durationMillis` 回调。
- `apps/mobile/src/components/LucideIcon.tsx`
  - 增加 `chevron-up` 图标。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 增加拖动展开、手柄、计时器兜底和折叠条对齐静态检查。

## 影响范围

仅影响移动端实时录音折叠态和录音计时显示。不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、会议 API、会议详情、知识库或待办。

## 测试结果

- `node apps/mobile/scripts/test-recording-upload-ui.js`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

当前验证为静态检查和类型检查，未在真机上验证不同屏幕安全区下的拖动手感。手势阈值后续可按实机反馈微调。

## 后续建议

后续如引入真实底部安全区适配，应同时检查折叠条高度、顶部手柄位置和底部导航覆盖关系。
