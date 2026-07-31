# Bottom Navigation Height Minus 5

## 开发目标

将当前移动端底部菜单高度降低 5%，并对应调整图标和文字位置。

## 背景

底部导航已贴底并提高到 `minHeight: 106`。当前需要略微降低高度，同时保持图标和文字同步上移但减少偏移量。

## 实现方案

- 保留底部导航贴底绝对定位。
- 将导航容器 `minHeight` 从 106 调整为 101。
- 将单个 tab item `minHeight` 从 87 调整为 83。
- 将整体上移偏移从 `translateY: -10` 调整为 `translateY: -8`。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 底部导航高度降低约 5%。
  - 图标和文字整体上移量对应回调。
- `apps/mobile/scripts/test-bottom-nav-ui.js`
  - 更新高度与整体上移静态检查。

## 影响范围

仅影响 Expo 移动端底部导航视觉样式。未修改后端、数据库、Worker、Prompt、RAG、Validator、Schema 或 API。

## 测试结果

- `npm run test:bottom-nav-ui`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未启动真机或模拟器截图验证；实际视觉效果仍建议在目标设备上确认。

## 后续建议

如果底栏仍遮挡页面底部内容，应针对具体页面补充底部 content padding。
