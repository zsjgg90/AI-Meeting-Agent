# History Swipe Delete Overflow Fix

## 开发目标

修复历史会议页面左滑删除红色背景超出会议卡片边界的问题。

## 背景

历史会议页面改为复用首页 compact 会议卡片后，卡片自身仍保留 `marginBottom: 12`，而左滑删除背景沿用了旧卡片的 `bottom: 8` 裁剪方式。两者不一致导致红色删除层在卡片右下角露出。

## 实现方案

- 为 `MeetingCard` 增加 `flushBottom` 参数。
- 历史页非选择状态下的左滑卡片传入 `flushBottom={!selecting}`。
- 左滑容器 `swipeRow` 统一负责 `marginBottom: 12`。
- 删除背景 `swipeDelete` 改为 `bottom: 0`，与卡片高度完全一致。
- 新增 `cardFlushBottom` 样式，在左滑容器内移除 compact 卡片自身底部 margin。

## 修改内容

- `apps/mobile/src/screens/MeetingListScreen.tsx`
  - 调整历史会议左滑删除容器和卡片间距。
- `apps/mobile/scripts/test-meeting-history-ui.js`
  - 增加左滑卡片去除内部底部 margin 的静态检查。

## 影响范围

仅影响历史会议列表左滑删除的视觉边界。首页列表、会议详情、删除 API 和批量选择删除逻辑不变。

## 测试结果

- `npm run typecheck`：通过。
- `node scripts/test-meeting-history-ui.js`：通过。
- `.\scripts\test-all.ps1`：通过。

## 已知限制

未在真实设备上截图验证左滑手势的像素效果。

## 后续建议

后续如继续调整历史列表卡片间距，优先改 `swipeRow`，避免卡片 margin 与删除背景再次不一致。
