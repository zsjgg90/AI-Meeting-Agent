# MeetMind Mobile Home RC1

## 开发目标

根据 `meetmind-app (2).html` 首页原型，重构 Expo 移动端会议首页，并接入真实文件导入入口。

## 背景

当前移动端首页入口为 `apps/mobile/App.tsx` 中的 `MeetingListScreen mode="home"`。会议列表读取 API `GET /meetings`，已完成会议按需读取 `GET /meetings/{id}/summary`。实时录音已通过创建会议、录音页、上传和 AI 处理页完成闭环；文件导入此前是占位弹窗。

## 实现方案

保持现有路由、API 合同和 AI 处理链路不变。首页继续使用单个 `FlatList` 承载整页内容和会议列表，避免 `ScrollView` 嵌套 `FlatList`。导入音频新增一个薄屏幕，只负责选择音频文件和创建会议，随后交给现有 `AIProcessingScreen` 上传、处理和分析。

## 修改内容

- 首页结构调整为 MeetMind AI 品牌/搜索区、实时录音、导入音频、全部会议列表。
- 首页会议卡片展示标题、状态、开始时间、时长、AI 摘要状态和待办数量。
- 已完成会议卡片预览 `meeting_agenda`、`key_conclusions`、`action_items` 的第一条；正式字段为空时兼容 `agenda`、`decisions`、`next_steps`。预览行使用黑色单行文本，超长内容尾部省略，并随可用模块数量自适应卡片高度。
- 新增 `ImportMeetingScreen`，使用 `expo-document-picker` 选择单个音频文件。
- 导入音频后创建会议，并复用 `AIProcessingScreen` 的 `uploadAudio -> processMeeting -> analyzeMeeting` 链路。
- 首页日期显示为 `M月D日 今天` 或 `M月D日 周X`，`浏览全部` 改为 `更多`，并收紧 `全部会议` 区块上方间距。
- 修正移动端 API 超时文案为正常中文用户提示。

## 影响范围

影响 Expo 首页展示、文件导入入口和移动端依赖。未修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema 或会议详情数据合同。历史会议、会议详情、录音、知识库、待办和底部导航路由保持兼容。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-history-ui`：通过。
- `npm run test:recording-upload-ui`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `npm run test:knowledge-base-ui`：通过。

## 已知限制

音频导入支持的实际格式仍以后端 `/meetings/{id}/audio` 接口和 Worker 转写能力为准。导入屏不提供手动编辑会议标题，标题默认来自文件名。

## 后续建议

补充真机或 Dev Client 的导入音频端到端 smoke test，覆盖大文件、取消选择、上传失败和分析失败状态。
