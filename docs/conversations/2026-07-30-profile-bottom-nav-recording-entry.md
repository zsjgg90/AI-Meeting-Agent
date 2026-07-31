# Profile Bottom Nav Recording Entry

## 开发目标

根据 `meetmind-app_profile.html` 原型重构移动端 `我的` 页面，并在底部导航中心增加实时录音入口。

## 背景

当前移动端源码入口为 `apps/mobile`。实时录音能力已经由 `apps/mobile/App.tsx` 持有全局录音会话状态，并常驻挂载 `RecordingScreen` 作为展开/收起 Overlay 和迷你播放器。首页实时录音入口已经通过 `createRecordingMeeting()` 创建会议并启动该 Overlay。

## 实现方案

保持录音链路不变，只让 BottomNav 中心麦克风按钮复用现有 `createRecordingMeeting()` 和 `openRecordingSession()` 行为。`我的` 页面使用 React Native 组件按原型重排，不复制 HTML、Tailwind 或 Iconify。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 底部导航固定为 `首页 | 知识库 | 麦克风 | 待办 | 我的`。
  - 新增中心蓝色圆形麦克风按钮，保留原有固定底部样式。
- `apps/mobile/App.tsx`
  - `BottomTab` 新增 `recording` 点击处理。
  - 无录音会话时调用现有 `createRecordingMeeting()`。
  - 已有录音会话时只展开当前 `RecordingScreen` Overlay。
- `apps/mobile/src/screens/ProfileScreen.tsx`
  - 重构为 `我的` 标题、顶部设置入口、用户信息卡、五项菜单。
  - `帮助与反馈`、`关于 MeetMind AI`、设置继续走现有路由。
  - `我的记忆`、`声纹管理`、`推送配置` 因无 API 合同，仅提示当前版本未开放。
- `apps/mobile/scripts/test-bottom-nav-ui.js`
  - 增加五项导航和中心录音入口复用的静态检查。
- 文档同步更新 README、移动端 README、Current Tasks、Changelog 和 Session Handoff。

## 影响范围

仅影响 Expo 移动端 `我的` 页面、底部导航展示和录音入口触发位置。首页、知识库、待办、会议详情、文件导入、后端 API、Worker、Prompt、RAG、Validator、Schema 和数据库未做业务改动。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:bottom-nav-ui`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

`我的记忆`、`声纹管理`、`推送配置` 当前没有真实 API 合同，本次不添加假数据或本地伪状态。

## 后续建议

后续若开放记忆、声纹或推送配置，应先定义 API 合同和持久化模型，再接入移动端路由。
