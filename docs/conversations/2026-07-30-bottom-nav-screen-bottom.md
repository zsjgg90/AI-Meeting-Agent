# Bottom Navigation Screen Bottom

## 开发目标

将移动端底部菜单导航贴到手机屏幕最底部，去掉原先底部可见空隙。

## 背景

`BottomNav` 原本作为普通布局流中的组件渲染，并保留 `paddingBottom: 12` 与较高 `minHeight`。在手机屏幕底部会出现导航条没有贴底的视觉空白。

## 实现方案

- 只修改 `apps/mobile/src/components/BottomNav.tsx` 的导航容器样式。
- 使用绝对定位固定在底部：`position: 'absolute'`、`bottom: 0`、`left: 0`、`right: 0`。
- 去掉原底部 padding，并将最小高度从 78 调整为 66。
- 新增静态检查，防止底部导航恢复为带底部空隙的样式。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 底部导航改为贴底绝对定位。
  - `paddingBottom` 从 12 改为 0。
- `apps/mobile/scripts/test-bottom-nav-ui.js`
  - 新增底部导航样式静态检查。
- `apps/mobile/package.json`
  - 新增 `test:bottom-nav-ui`。
- `scripts/test-all.ps1`
  - 默认移动端检查接入底部导航测试。

## 影响范围

仅影响 Expo 移动端底部导航视觉位置。未修改后端、数据库、Worker、Prompt、RAG、Validator、Schema 或 API。

## 测试结果

- `npm run test:bottom-nav-ui`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

本次未启动 Expo 真机或模拟器做截图验证；当前验证为 TypeScript 与静态 UI 结构检查。

## 后续建议

在真机或 Expo Go 中确认不同系统手势条/安全区下的最终视觉位置。如果发现内容被底栏遮挡，再按具体页面补底部滚动 padding。
