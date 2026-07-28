# Meeting Summary Final Acceptance

## 开发目标

对 Expo 移动端会议详情页 `AI纪要` tab 做最终验收和必要修复。

## 背景

`AI纪要` tab 已根据 `docs/design/meeting-minutes.html` 完成重构。本次只验证和修补边界行为，不开发 Agent 工具，不修改会议原文页面，不扩大后端或 AI 分析能力。

## 实现方案

- 保持 `MeetingDetailScreen` 的现有顶部导航、播放器、三标签栏和单个 `FlatList` 结构。
- 继续优先使用 canonical 六维字段，并保留 legacy fallback。
- 补强证据时间解析、跨 tab 定位时序、全空状态和待办空对象过滤。
- 扩展静态测试和 summary 导出 API 回归测试，不新增后端业务能力。

## 修改内容

- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - `meeting_summary` 保留段落换行，不再压成单行文本。
  - `timestamp` 支持数字秒、`mm:ss` 和 `hh:mm:ss`。
  - 从 AI纪要点击证据定位时，切到会议原文后延迟滚动到对应片段。
  - 找不到 `segment_id` / `source_segment_id` 对应片段时切到会议原文并显示明确降级提示。
  - 六个维度全部为空时显示整体空状态。
  - 待办列表先过滤无有效内容的对象，避免空白待办行。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 增加 summary 导出防重复点击、失败提示、标签切换不重建播放器、证据跳转时序、全空状态和时间戳解析静态检查。
- `services/api/tests/test_meeting_summary_exports.py`
  - 验证 summary MD/TXT/PDF/DOCX 四种格式可下载，中文内容保留，PDF 文件头和 DOCX zip 结构有效，并覆盖不支持格式失败。

## 影响范围

- 影响 Expo 会议详情页 `AI纪要` tab 的展示和边界交互。
- 不影响会议原文现有逻辑、播放器实现、Agent 工具、后端业务实现、数据库、Worker、Prompt、RAG、Validator 或六维 Schema。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `.venv\Scripts\python.exe -m unittest tests.test_meeting_summary_exports`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

- iPhone 安全区域、Android 页面适配、超长真实会议数据和下载文件打开体验仍需要真机或模拟器手工验收。
- 当前详情页没有正式 ActionItem 状态更新 API，待办 checkbox 继续保持只读展示。

## 后续建议

- 后续如果接入待办真实更新，应先定义明确 API contract、权限边界和失败回滚行为。
- 建议在稳定的真机自动化环境中补充截图级布局回归。
