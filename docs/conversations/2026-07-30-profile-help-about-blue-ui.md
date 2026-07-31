# Profile Help And About Blue UI

## 开发目标

将移动端 `我的` 页面中“帮助与反馈”和“关于 MeetMind AI”的一级入口与后续页面统一调整为新版蓝色视觉风格，并将关于页当前版本展示改为 `V1.0.0`。

## 背景

`我的` 页面入口在 `ProfileScreen`，点击后由 `App.tsx` 切换到 `HelpFeedbackScreen`、`FaqScreen`、`FeedbackScreen` 和 `AboutScreen`。这些页面原先仍保留紫色视觉 token，与新版 MeetMind 蓝色风格不一致。

## 实现方案

- 保持现有路由和真实反馈提交 API 不变。
- 在 `AppHeader` 增加可选 `accentColor`，默认不影响其他页面。
- 仅对 `helpFeedback`、`faq`、`feedback`、`about` 路由传入新版蓝色。
- 将帮助、FAQ、反馈、关于页中旧紫色 token 替换为 `#2B6CFF` 及浅蓝辅助色。
- 将 `ProfileScreen` 中帮助与关于两个入口图标显示为蓝色。
- 将关于页版本号显示为 `当前版本 V1.0.0`。
- 根据后续视觉要求，将帮助/关于相关顶部标题与返回箭头恢复为黑色，并将我的页入口图标、帮助页入口图标、FAQ 序号、关于页声纹图标调整为黑色。

## 修改内容

- `apps/mobile/App.tsx`
  - 为我的帮助/关于相关子路由传入蓝色头部 accent。
- `apps/mobile/src/components/AppHeader.tsx`
  - 新增可选 `accentColor`，用于局部覆盖返回箭头、标题和右侧操作文字颜色。
- `apps/mobile/src/screens/ProfileScreen.tsx`
  - 帮助与反馈、关于 MeetMind AI 入口图标改为蓝色。
- `apps/mobile/src/screens/HelpFeedbackScreen.tsx`
  - 主视觉、入口图标和装饰色改为蓝色。
- `apps/mobile/src/screens/FaqScreen.tsx`
  - FAQ 序号徽标改为浅蓝底和蓝色文字。
- `apps/mobile/src/screens/FeedbackScreen.tsx`
  - 选中反馈类型和提交按钮改为蓝色。
- `apps/mobile/src/screens/AboutScreen.tsx`
  - Logo、阴影、版本号改为蓝色，版本文案改为 `当前版本 V1.0.0`。
- `apps/mobile/scripts/test-profile-ui.js`
  - 新增 profile UI 静态检查。
- `apps/mobile/package.json`
  - 新增 `test:profile-ui`。
- `scripts/test-all.ps1`
  - 将 profile UI 静态检查纳入默认全量检查。
- 后续调整
  - 移除帮助/FAQ/反馈/关于路由的蓝色头部 accent，保持共享头部黑色。
  - 入口和序号类图形元素使用黑色，蓝色保留在主按钮、版本号和品牌强调处。
  - 移除帮助与反馈页“常见问题”和“意见反馈”卡片左侧 icon，仅保留文字和右侧箭头。

## 影响范围

仅影响移动端我的页帮助/关于相关 UI 和共享头部的可选样式参数。默认头部样式保持不变，不影响首页、知识库、待办、会议详情、录音流程、后端 API、Worker、Prompt、RAG、Validator、Schema 或数据库。

## 测试结果

- `npm run test:profile-ui`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未做真机/Expo 截图验收；本次通过代码静态检查和类型检查验证样式 token、路由头部 accent 和版本文案。

## 后续建议

在真机上进入 `我的 -> 帮助与反馈 -> 常见问题 / 意见反馈` 以及 `我的 -> 关于 MeetMind AI`，确认头部、按钮、徽标和版本号均为新版蓝色展示。
