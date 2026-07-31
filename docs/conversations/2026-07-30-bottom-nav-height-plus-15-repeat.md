# Bottom Navigation Height Plus 15 Repeat

## 开发目标

在当前底部菜单基础上继续将高度提高 15%，并让图标和文字进一步上移。

## 背景

底部导航已贴底，并已提高到 `minHeight: 92`。当前需要再次按 15% 提高高度，同时保持图标和文字同步上移。

## 实现方案

- 保留底部导航贴底绝对定位。
- 将导航容器 `minHeight` 从 92 调整为 106。
- 将单个 tab item `minHeight` 从 76 调整为 87。
- 将整体上移偏移从 `translateY: -6` 调整为 `translateY: -10`。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 底部导航高度继续提高约 15%。
  - 图标和文字整体进一步上移。
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

如果更高的底栏遮挡列表或详情页底部内容，应按页面补充底部 content padding。
