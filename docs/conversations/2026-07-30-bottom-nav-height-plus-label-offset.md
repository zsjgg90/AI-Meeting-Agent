# Bottom Navigation Height Plus Label Offset

## 开发目标

在已贴底的移动端底部菜单基础上，将高度继续提高 15%，并让图标和文字一起上移。

## 背景

上一轮调整已将底部导航高度提高到 `minHeight: 80`，并只上移图标。当前需要进一步增加高度，并让图标和字体作为一组内容同步上移。

## 实现方案

- 保留底部导航贴底绝对定位。
- 将导航容器 `minHeight` 从 80 调整为 92。
- 将单个 tab item `minHeight` 从 66 调整为 76。
- 将上移 transform 放到 tab item 上：`transform: [{ translateY: -6 }]`。
- 移除图标容器上的单独上移，避免图标和文字错位。

## 修改内容

- `apps/mobile/src/components/BottomNav.tsx`
  - 底部导航高度继续提高约 15%。
  - 图标和文字整体上移。
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
