# Mobile Push Config

## 开发目标

实现移动端个人中心下的 `推送配置` 页面，参考提供的 HTML 原型，以 React Native 展示飞书推送、邮箱推送和短信提醒三个渠道。

## 背景

产品定位为 AI 会议成果自动分发中心。当前项目没有正式飞书、邮箱、短信、推送配置或推送历史 API，因此页面必须保持真实状态展示，不能伪造连接成功、发送成功或历史记录。

## 实现方案

新增独立 Profile 子页面，并在 `App.tsx` 中增加 `pushConfig` 路由。页面自身包含返回按钮、标题、副标题和三个渠道卡片。所有渠道开关均 disabled 且关闭，只展示 `未配置`、`暂未开放`、`待接入` 等状态文案。

## 修改内容

- 新增 `apps/mobile/src/screens/PushConfigScreen.tsx`
- `apps/mobile/App.tsx` 增加 `pushConfig` 路由、返回处理和页面渲染
- `apps/mobile/src/screens/ProfileScreen.tsx` 将 `推送配置` 入口接入新页面
- `apps/mobile/src/components/LucideIcon.tsx` 增加 `send` 图标用于飞书推送卡片
- 新增 `apps/mobile/scripts/test-push-config-ui.js`
- `apps/mobile/package.json` 增加 `test:push-config-ui`
- `scripts/test-all.ps1` 将推送配置静态检查纳入默认移动端检查
- 同步更新 README、移动端 README、CURRENT_TASKS、CHANGELOG 和 SESSION_HANDOFF

## 影响范围

仅影响移动端个人中心 UI、共享图标组件和文档。未修改 API、Worker、数据库、Prompt、RAG、Validator、Schema 或会议分析链路。

## 测试结果

已执行并通过：

- `npm run typecheck`
- `npm run test:push-config-ui`
- `.\scripts\test-all.ps1`

## 已知限制

当前没有真实飞书、邮箱、短信、推送配置或推送历史 API。页面不能保存配置，不能执行发送，也不会展示历史记录。

## 后续建议

后续如开放推送能力，应先定义 API 合同、鉴权/密钥配置、错误处理、审计记录和隐私策略，再开放开关、配置编辑、发送状态和历史记录。
