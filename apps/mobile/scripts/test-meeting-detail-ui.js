const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'MeetingDetailScreen.tsx'), 'utf8');
const audioPlayer = fs.readFileSync(path.join(root, 'src', 'screens', 'AudioPlayerScreen.tsx'), 'utf8');
const audioFiles = fs.readFileSync(path.join(root, 'src', 'utils', 'audioFiles.ts'), 'utf8');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const icons = fs.readFileSync(path.join(root, 'src', 'components', 'LucideIcon.tsx'), 'utf8');

const requiredScreenSnippets = [
  'FlatList',
  "type DetailTab = 'transcript' | 'summary' | 'agent'",
  "label: '会议原文'",
  "label: 'AI纪要'",
  "label: 'Agent工具'",
  'function renderAudioPlayer',
  'chooseMeetingAudioFile(meeting?.audio_files || [])',
  'const selectedAudioKey = meeting && selectedAudio',
  'loadedAudioKeyRef.current',
  'PanResponder.create',
  'pendingSeekMillisRef.current',
  'isScrubbingRef.current',
  'async function seekToSeconds',
  'async function jumpToSegment',
  'const wasTranscriptTab = activeTab ===',
  'setTimeout(scrollToSegment, 250)',
  'async function toggleSegmentPlayback',
  'segmentPlaybackRef.current = { id: segment.id, endMillis }',
  'segmentPlaybackId === item.id && isPlaying',
  'isMainPlaybackActive',
  'segmentStart(item)',
  "onPress={() => openExport('transcript', format)}",
  "supportedTranscriptExports: ExportFormat[] = ['md', 'pdf', 'docx', 'txt']",
  'function buildQuickLookSegments',
  'removeClippedSubviews',
  'initialNumToRender={14}',
  '音频加载失败',
  '当前会议没有可播放的录音文件',
  '转写处理中',
  '暂无转写文本',
  '{resultSourceText(summary)}',
  "meetingExportUrl(meetingId, kind, format)",
  "if (kind === 'summary' && exportingSummaryFormat) return;",
  "disabled={!enabled || Boolean(exportingSummaryFormat)}",
  '导出失败，请稍后重试。',
  "supportedSummaryExports: ExportFormat[] = ['md', 'pdf', 'docx', 'txt']",
  "onPress={() => openExport('summary', format)}",
  'function renderSummaryExportButtons',
  'function renderEvidence',
  'function renderAgendaSection',
  'function renderActionSection',
  'function parseTimeValue',
  "normalized.split(':').map(Number)",
  'summaryEmpty',
  '暂无AI纪要内容',
  '未找到对应原文片段，已切换到会议原文。',
  "summary?.meeting_agenda?.length ? summary.meeting_agenda : summary?.agenda || []",
  "summary?.meeting_summary || summary?.overview || fallbackOutput?.summary || ''",
  "summary?.key_conclusions?.length ? summary.key_conclusions : summary?.decisions || []",
  "summary?.unresolved_issues?.length ? summary.unresolved_issues : summary?.open_questions || []",
  "summary?.risks_and_focus?.length ? summary.risks_and_focus : summary?.risks || []",
  'readonlyCheckbox',
  '状态：${statusLabel(status)}',
  'source_text',
  'source_segment_id',
  'segment_id',
  'timestamp',
  'function hasSummaryContent',
  'function summaryDisplayStatus',
  "status === 'failed' || status === 'summary_failed'",
  'hasSummaryContent(summary, fallbackOutput)',
];

for (const snippet of requiredScreenSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`MeetingDetailScreen is missing required transcript/player UI snippet: ${snippet}`);
  }
}

const forbiddenScreenSnippets = [
  'Agen工具',
  '<ScrollView contentContainerStyle={styles.container}',
  'function toggleSummaryAction',
  'setCompletedAction',
  'onPress={() => setCompleted',
  'onclick=',
  'playbackRates',
  'changeRate',
  'rateButton',
  'rateText',
  'result_source=',
  "summary?.metadata?.result_source || 'unknown'",
  'audio_files[0]',
  'latestAudio',
];

for (const snippet of forbiddenScreenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`MeetingDetailScreen must not contain forbidden snippet: ${snippet}`);
  }
}

for (const snippet of ['playableAudioExtensions', 'hasPlayableAudioShape', 'chooseMeetingAudioFile', 'uploaded_at', 'file_size_bytes']) {
  if (!audioFiles.includes(snippet)) {
    throw new Error(`Audio file selector is missing required snippet: ${snippet}`);
  }
}

for (const snippet of ['chooseMeetingAudioFile(meeting?.audio_files || [])', 'selectedAudioKey', 'loadedAudioKeyRef.current', 'audioBusyRef.current']) {
  if (!audioPlayer.includes(snippet)) {
    throw new Error(`AudioPlayerScreen is missing required audio selection/lifecycle snippet: ${snippet}`);
  }
}

for (const snippet of ['PanResponder.create', 'pendingSeekMillisRef.current', 'isScrubbingRef.current']) {
  if (!audioPlayer.includes(snippet)) {
    throw new Error(`AudioPlayerScreen is missing required draggable progress snippet: ${snippet}`);
  }
}

for (const snippet of ['audio_files[0]', 'latestAudio']) {
  if (audioPlayer.includes(snippet)) {
    throw new Error(`AudioPlayerScreen must not contain forbidden snippet: ${snippet}`);
  }
}

if (!app.includes('onBack={handleBack}')) {
  throw new Error('App must pass existing navigation back handler into MeetingDetailScreen.');
}

const renderTabsStart = screen.indexOf('function renderTabs()');
const renderTabsEnd = screen.indexOf('function renderQuickLook()', renderTabsStart);
const renderTabsBody = renderTabsStart >= 0 && renderTabsEnd > renderTabsStart ? screen.slice(renderTabsStart, renderTabsEnd) : '';
for (const forbidden of ['ensureSound(', 'unloadAsync(', 'loadMeeting(']) {
  if (renderTabsBody.includes(forbidden)) {
    throw new Error(`Tab switching must not recreate, reload, or release audio: ${forbidden}`);
  }
}

for (const icon of ["'share-2'", "'more-horizontal'", "'play'", "'pause'"]) {
  if (!icons.includes(icon)) {
    throw new Error(`LucideIcon is missing required icon: ${icon}`);
  }
}

console.log('Meeting detail UI static checks passed.');
