# Home Meeting Card Four Preview Fields

## 开发目标

首页会议列表卡片支持展示 `会议总结`、`会议议程`、`核心结论`、`待办事项` 四个数据项，并保持数据获取逻辑不变。

## 背景

此前卡片完成态预览缺少 `会议总结`，同时待办字段文案为 `待办任务`，与当前要求不一致。

## 实现方案

- 保持现有 summary 加载逻辑不变。
- 完成态卡片支持四个预览维度。
- 继续使用现有字段来源：
  - `meeting_summary` / `overview`
  - `meeting_agenda` / `agenda`
  - `key_conclusions` / `decisions`
  - `action_items` / `next_steps`
- 缺失值不在预览区域展示。
- 将 `待办任务` 改为 `待办事项`。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 完成态 compact 卡片支持显示四个预览字段。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加四个固定预览字段的静态检查。

## 影响范围

影响首页会议列表和复用同一 compact 卡片的历史会议列表。数据获取、会议详情、录音、上传、AI 分析、后端和 Worker 不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真实设备截图验证。

## 后续建议

如果四行固定展示导致小屏卡片偏高，可后续在视觉层调整行高或折叠策略，但不改变字段集合。
