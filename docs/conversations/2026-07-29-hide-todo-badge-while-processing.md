# Hide Todo Badge While Processing

## 开发目标

会议处于处理中时，首页会议卡右下角不显示“待办”徽标；只有 AI 结构化结果生成成功后才显示待办数量或“无待办”。

## 背景

实时录音结束后会议会先进入上传、转写和 AI 结构化分析流程。在结果未生成前显示待办徽标容易让用户误以为待办已经计算完成。

## 实现方案

在 `MeetingListScreen` 的首页紧凑会议卡中，将右下角 `actionCountBadge` 限制为 `status === 'completed'` 时渲染。处理中、录音中、待处理、失败等状态不显示该徽标。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 首页会议卡右下角待办徽标仅在 `completed` 状态展示。
  - 兼容 `miniRecordingVisible` prop 类型，保持现有 App 调用通过类型检查。
- `apps/mobile/src/screens/RecordingScreen.tsx`
  - 兼容现有 App 传入的 `displayState` 等录音展示 props。
- `apps/mobile/App.tsx`
  - 恢复当前 App 使用的 React Native 导入、浮动录音图标和拖拽响应器类型依赖，确保类型检查通过。
- `apps/mobile/scripts/test-recording-upload-ui.js`
  - 静态检查覆盖待办徽标只在完成状态展示。
- `docs/CHANGELOG.md`
  - 记录本次展示规则调整。

## 影响范围

影响移动端首页会议卡展示。没有修改上传、转写、AI 分析、会议详情、任务数据、后端、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:recording-upload-ui`：通过。

## 已知限制

该改动只隐藏首页紧凑会议卡的右下角待办徽标，不新增实时任务状态推送。

## 后续建议

如历史列表也需要隐藏统计行中的待办数量，可单独调整非紧凑会议卡的 `statsRow` 展示规则。
