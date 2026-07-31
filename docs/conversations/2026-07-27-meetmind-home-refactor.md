# MeetMind Home Refactor

## 开发目标

根据 MeetMind AI 首页 HTML 原型，使用现有 Expo React Native 技术重构 `apps/mobile` 首页展示。

## 背景

当前首页由 `MeetingListScreen mode="home"` 承载，已接入真实会议列表、会议摘要统计、录音入口、会议详情跳转和底部导航。本次仅调整首页视觉和信息层级，不修改后端、Worker、RAG、Prompt、Schema 或数据库。

## 实现方案

保留现有数据加载和导航链路，为首页会议卡片新增 `compactHome` 展示分支。历史会议 `mode="all"` 继续使用原有列表、分页、刷新、批量删除和滑动删除逻辑。文件导入不接入新依赖或上传链路，仅提供占位点击提示。

## 修改内容

- 首页增加品牌区、搜索按钮、实时录音和导入文件操作区。
- 首页洞察改为原型风格的四项卡片，数据仍来自真实会议和已完成会议摘要。
- 最近会议卡片展示标题、时间、时长、处理状态、AI 摘要状态和待办数量。
- 底部导航仅调整视觉样式，保持现有 tab key、路由和页面数量。
- 已完成会议摘要请求只补拉未缓存项，请求失败缓存为 `null` 并降级为 0 统计。

## 影响范围

影响 `apps/mobile` 首页展示和底部导航视觉。历史会议列表、录音页、会议详情页、API、Worker、RAG、Prompt、Schema 和数据库不在本次变更范围内。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `npm run test:meeting-history-ui`：失败，现有静态测试在 `api.ts` 中未找到期望的中文超时文案 `网络请求超时，请稍后重试`。
- `npm run test:recording-upload-ui`：失败，原因同上。

## 已知限制

文件导入仍是占位入口，点击仅提示“文件导入功能开发中”。项目当前没有 `lint` 脚本，本次未新增 lint 配置。

## 后续建议

如需真实文件导入，应单独设计移动端文件选择、音视频上传、处理触发和错误恢复链路，再决定是否新增依赖与后端契约。
