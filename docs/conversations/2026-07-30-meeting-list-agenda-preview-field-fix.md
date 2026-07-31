# Meeting List Agenda Preview Field Fix

## 开发目标

检查并修复会议列表中 `会议议程` 没有获取到的问题。

## 背景

首页和历史会议列表复用同一个 compact 会议卡片。后端 `GET /meetings/{id}/summary` 已返回 `meeting_agenda`，并兼容 legacy `agenda`，但列表预览提取函数没有读取结构化议程对象中的 `item` 字段。

## 实现方案

- 保持现有 summary 请求和后端返回结构不变。
- 在列表预览通用文本提取函数中加入 `record.item`。
- 保持空维度隐藏逻辑不变，只有真正提取到有效文本才展示对应行。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - `textFromSummaryItem()` 增加 `record.item` 候选字段。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加 `record.item` 静态检查，防止议程字段再次漏取。
- `docs/CHANGELOG.md`
  - 记录议程预览字段修复。
- `SESSION_HANDOFF.md`
  - 记录当前交接说明。

## 影响范围

影响首页会议列表和历史会议列表的 AI 预览文本提取。数据获取、会议详情、录音、上传、AI 分析、后端和 Worker 均不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真实设备截图验证。

## 后续建议

如果后续 summary 字段增加新的结构化 key，应优先补充统一提取函数，而不是在每个维度单独写解析逻辑。
