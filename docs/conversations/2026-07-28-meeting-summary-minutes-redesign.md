# Meeting Summary Minutes Redesign

## 开发目标

根据 `docs/design/meeting-minutes.html` 重构 Expo 移动端会议详情页中的 `AI纪要` 标签页。

## 背景

会议详情页已完成 `会议原文` 页和页内播放器重构，但 `AI纪要` 标签仍是较简单的摘要和列表展示。本阶段只调整移动端前端展示和既有交互，不修改 API、Worker、数据库、Prompt、RAG、Validator 或六维 Schema。

## 实现方案

- 继续复用 `MeetingDetailScreen` 的顶部导航、`expo-av` 播放器、三标签栏和单个 `FlatList` 页面结构。
- AI纪要页使用当前会议详情和 `GET /meetings/{id}/summary` 的真实数据。
- 六维展示优先 canonical 字段，字段为空时保留 legacy 兼容。
- AI纪要导出复用现有 `/meetings/{id}/exports/summary.{format}` 后端能力。
- 待办状态按当前数据只读展示，不接入本地临时 checkbox 状态。
- 对已有证据和时间字段做轻量展示，并复用会议原文的跳转和音频定位能力。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 新增 AI纪要会议基础卡片、基本信息、summary 导出按钮、六维结果卡片、只读待办状态和证据展示。
  - `meeting_summary` 不再用转写片段拼接伪造总结；为空时显示空状态。
  - `action_items` 展示任务、状态、负责人、截止时间、优先级和证据字段，已完成项弱化并加删除线。
  - evidence/time 字段可跳转到会议原文并定位对应片段或时间。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 更新静态检查，覆盖 summary 导出、canonical 字段、legacy fallback、只读待办和证据字段。
- 文档同步更新：
  - `README.md`
  - `apps/mobile/README.md`
  - `docs/CHANGELOG.md`
  - `docs/CURRENT_TASKS.md`
  - `SESSION_HANDOFF.md`

## 影响范围

- 影响 Expo 会议详情页 `AI纪要` 标签页展示。
- 不影响会议原文页数据、播放器实现、首页、录音、上传、AI 处理、后端接口、Worker、Prompt、RAG、Validator、数据库和六维 Schema。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_meeting_summary_exports`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

- 会议详情页当前没有正式 ActionItem 状态更新 API，因此待办 checkbox 为只读状态展示。
- 失败态不新增后端重试调用，仅保留刷新状态和引导使用现有处理页重试。
- 本阶段没有新增真机自动化视觉测试，UI 覆盖以 TypeScript 和静态结构检查为主。

## 后续建议

- 如后续要在 AI纪要页直接完成待办，应先定义正式 API contract 和权限边界。
- 如 summary 证据字段后续统一结构，可将当前轻量 evidence 展示抽成共享组件。
