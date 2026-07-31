# Mobile Voiceprint Management

## 开发目标

实现移动端 `声纹管理` 和 `添加声纹样本` 页面，参考提供的 HTML 原型，但使用 React Native 与现有 MeetMind AI 风格。

## 背景

项目已有会议录音、说话人分离和会议内 `speaker_label -> display_name` 映射能力，但没有正式的全局声纹注册、声纹样本上传或身份匹配 API。声纹采样不能进入会议录音、转写、AI纪要或 Agent 分析流程。

## 实现方案

新增独立移动端页面和路由。声纹管理页展示不可用开关、说明、空状态和添加入口；添加声纹页使用页面内 `Audio.Recording` 采集本地样本，保存时只提示接口待接入。

## 修改内容

- 新增 `apps/mobile/src/screens/VoiceprintManagementScreen.tsx`
- 新增 `apps/mobile/src/screens/AddVoiceprintSampleScreen.tsx`
- `apps/mobile/App.tsx` 增加 `voiceprintManagement` 和 `addVoiceprintSample` 路由
- `apps/mobile/src/screens/ProfileScreen.tsx` 将 `声纹管理` 入口接入新页面
- `apps/mobile/src/components/LucideIcon.tsx` 增加 `plus` 图标
- 更新 README、移动端 README、Current Tasks、Changelog 和 Session Handoff

## 影响范围

仅影响移动端个人中心下的声纹页面入口和新增页面。未修改 API、Worker、数据库、Prompt、RAG、Validator 或会议录音处理链路。

## 测试结果

- `npm run typecheck`：通过
- `.\scripts\test-all.ps1`：通过

## 已知限制

当前没有正式声纹 API，声纹列表为空，保存样本不会上传或注册，也不会用于自动说话人身份匹配。

## 后续建议

后续应先定义声纹样本 API、存储合同、隐私与删除策略，再接入列表、保存、编辑和 Speaker Diarization 身份辅助。
