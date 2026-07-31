# Bottom Navigation Height And Icon Offset

## 开发目标

将移动端底部菜单导航高度提高约 20%，并让图标在导航条内向上移动。

## 背景

底部菜单已贴到屏幕底部，但当前视觉高度偏低，图标位置需要更靠上。

## 实现方案

- 保留底部导航贴底绝对定位。
- 将导航容器 `minHeight` 从 66 调整为 80，约提升 20%。
- 将单个 tab item `minHeight` 从 54 调整为 66。
- 给图标容器增加 `transform: [{ translateY: -5 }]`，仅上移图标区域。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 提高底部导航和 tab item 高度。
  - 图标容器上移 5px。
- `apps/mobile/scripts/test-bottom-nav-ui.js`
  - 增加高度和图标上移样式检查。

## 影响范围

仅影响 Expo 移动端底部导航视觉样式。未修改后端、数据库、Worker、Prompt、RAG、Validator、Schema 或 API。

## 测试结果

- `npm run test:bottom-nav-ui`：通过。
- `npm run typecheck`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未启动真机或模拟器截图验证；实际视觉效果仍建议在目标设备上确认。

## 后续建议

如果增加高度后页面底部内容被导航条遮挡，应针对受影响页面补充滚动容器底部 padding。
