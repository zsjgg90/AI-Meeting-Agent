# Meeting Transcript Player Acceptance

## 开发目标

对 Expo 移动端“会议原文”和录音播放器进行最终验收与必要修复，重点覆盖音频资源选择、播放器状态、时间戳联动、会议速览和会议原文导出入口。

## 背景

会议原文页面已经完成原型化重构，但仍需要确认多音频文件场景、快速切换会议、片段播放暂停、导出格式和回归测试结果。本次不修改后端、数据库、Worker、Prompt、RAG、Validator、六维 Schema、AI 纪要业务逻辑或 Agent 工具逻辑。

## 实现方案

- 在移动端新增共享音频选择工具，按真实可播放条件和上传时间选择音频文件。
- 在会议详情页和独立录音播放器中复用该选择规则。
- 为已加载的 `expo-av` sound 绑定 meeting/audio key，切换会议或音频文件时释放旧资源。
- 用 busy guard 包裹播放、暂停、拖动进度、前进和后退操作，降低快速连续点击导致的状态竞争。
- 保持会议速览继续来自真实 `transcript_segments`，不新增章节伪数据。
- 保持导出入口继续调用现有 API，不新增本地导出或后端能力。

## 修改内容

- `apps/mobile/src/utils/audioFiles.ts`
  - 新增 `chooseMeetingAudioFile()` 和 `hasPlayableAudioShape()`。
  - 优先选择具有 id、path、正文件大小，且 MIME 为 `audio/*` 或文件扩展名为常见音频格式的最新音频。
  - 如没有完全符合条件的音频，兜底选择最新的 id/path 存在音频，保持接口兼容。
- `apps/mobile/src/screens/MeetingDetailScreen.tsx`
  - 替换 `audio_files[0]` 为共享选择规则。
  - 增加 loaded audio key，切换会议或音频文件时卸载旧 sound。
  - 普通时间戳和速览跳转会清理片段播放边界；片段播放按真实音频时长做边界裁剪。
  - 片段播放按钮再次点击时读取 `expo-av` 实时状态并暂停当前片段。
  - 进度条改为 `PanResponder` 拖动交互，拖动中即时更新显示位置，松手时提交一次 seek。
- `apps/mobile/src/screens/AudioPlayerScreen.tsx`
  - 替换 `audio_files[0]` 为共享选择规则。
  - 增加 loaded audio key、卸载清理和快速操作 guard。
  - 播放按钮改为黑白圆形 Lucide 图标，前后 15 秒按钮居中显示。
  - 进度条同步改为拖动预览、松手 seek，避免连续 move 事件被 busy guard 吞掉。
- `apps/mobile/scripts/test-meeting-detail-ui.js`
  - 增加音频选择、生命周期和禁止 `audio_files[0]` 的静态检查。

## 影响范围

- 影响移动端会议详情页内音频播放和独立录音播放器的音频选择及播放状态管理。
- 不影响首页、录音上传流程、AI 处理、后端接口、Worker、Prompt、RAG、Validator、数据库、AI 纪要业务或 Agent 工具逻辑。

## 测试结果

- `npm run typecheck`：通过。
- `npm run test:meeting-detail-ui`：通过。
- `npm run test:recording-upload-ui`：通过。
- `npm run test:meeting-history-ui`：通过。
- `.\scripts\test-all.ps1`：通过。
- 导出函数级验证：MD、PDF、DOCX、TXT 均生成成功；中文文件名、中文内容和基本可打开性检查通过。

## 已知限制

- 没有新增真机音频自动化测试；播放、暂停、拖动、片段播放停止点和系统播放器打开文件仍需 iOS/Android 真机或模拟器手工确认。
- 会议速览仍由真实 `transcript_segments` 派生，后端未提供正式章节字段时不展示伪造章节。

## 后续建议

- 在移动端端到端测试环境稳定后，补充真实 `expo-av` 播放器交互自动化测试。
- 如后端后续提供正式章节或 topic segment 字段，可替换当前 transcript-derived 速览逻辑。
