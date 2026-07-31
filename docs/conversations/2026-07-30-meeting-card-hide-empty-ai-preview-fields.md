# Meeting Card Hide Empty AI Preview Fields

## 开发目标

首页和历史会议列表中，`会议总结`、`会议议程`、`核心结论`、`待办事项` 四个 AI 预览维度没有有效识别结果时不展示该行，卡片高度随有效内容自然缩小。

## 背景

此前完成态会议卡片会固定展示四个 AI 预览行，缺失字段以 `暂无` 兜底，导致列表出现无信息空行并撑高卡片。

## 实现方案

- 保持现有 summary 获取字段和兼容字段不变。
- 在共享 compact 会议卡片中先构造四个预览维度。
- 仅保留 `text.trim()` 非空的维度进行渲染。
- 完成态但四个维度均为空时，不渲染四维预览块，沿用现有非完成预览分支。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 新增 `previewRows` 过滤逻辑。
  - 完成态预览块改为按有效维度 `map` 渲染。
  - 移除四个维度内的 `暂无` 兜底展示。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 更新共享卡片静态检查。
  - 增加禁止四维预览使用 `暂无` 兜底的回归检查。
- `docs/CHANGELOG.md`
  - 记录空 AI 维度隐藏行为。
- `SESSION_HANDOFF.md`
  - 更新当前交接说明。

## 影响范围

影响首页会议列表和历史会议列表的共享 compact 卡片展示。数据获取、会议详情、录音、上传、AI 分析、后端和 Worker 均不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真实设备截图验证；本次改动依赖 React Native 布局按内容自然收缩。

## 后续建议

如后续增加更多 AI 预览维度，应继续沿用“有有效内容才展示”的规则，避免空字段撑高列表卡片。
