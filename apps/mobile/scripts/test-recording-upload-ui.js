const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');
const processing = fs.readFileSync(path.join(root, 'src', 'screens', 'AIProcessingScreen.tsx'), 'utf8');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const meetingList = fs.readFileSync(path.join(root, 'src', 'screens', 'MeetingListScreen.tsx'), 'utf8');
const importMeeting = fs.readFileSync(path.join(root, 'src', 'screens', 'ImportMeetingScreen.tsx'), 'utf8');
const meetingTitle = fs.readFileSync(path.join(root, 'src', 'utils', 'meetingTitle.ts'), 'utf8');
const recording = fs.readFileSync(path.join(root, 'src', 'screens', 'RecordingScreen.tsx'), 'utf8');

const requiredApiSnippets = [
  'function audioUploadMetadata',
  "m4a: 'audio/x-m4a'",
  'async function fetchWithTimeout',
  'DEFAULT_REQUEST_TIMEOUT_MS',
  'function friendlyUploadError',
  '}/meetings/${meetingId}/audio`',
  '}/meetings/${meetingId}/audio-chunks`',
  'friendlyUploadError(response.status, body)',
];

for (const snippet of requiredApiSnippets) {
  if (!api.includes(snippet)) {
    throw new Error(`api.ts is missing recording upload snippet: ${snippet}`);
  }
}

const forbiddenApiSnippets = [
  'throw new Error(body ||',
  'fetch(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio`',
  'fetch(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio-chunks`',
];

for (const snippet of forbiddenApiSnippets) {
  if (api.includes(snippet)) {
    throw new Error(`api.ts must not use raw upload failure path: ${snippet}`);
  }
}

const requiredImportProcessingSnippets = [
  'await uploadAudio(meeting.id, recordingUri, endedAt)',
  'await processMeeting(meeting.id)',
  'await analyzeMeeting(meeting.id)',
  'const displayedTitle = meetingDetail?.title || meeting.title',
];

for (const snippet of requiredImportProcessingSnippets) {
  if (!processing.includes(snippet)) {
    throw new Error(`AIProcessingScreen is missing import processing flow snippet: ${snippet}`);
  }
}

const requiredRecordingAppSnippets = [
  "type RecordingDisplayState = 'hidden' | 'expanded' | 'collapsed'",
  'recordingDisplayState',
  "setRecordingDisplayState('expanded')",
  "setRecordingDisplayState('collapsed')",
  'runRecordingProcessingInBackground(meeting, recordingUri, endedAt)',
  'recordingAnalysisNoticeVisible',
  'recordingProcessingMeeting',
  'setRecordingProcessingMeeting(processingMeeting)',
  'setMeetingListRefreshKey((current) => current + 1)',
  '已进入AI结构化分析',
  '}, 500)',
  "setRoute({ name: 'home' })",
  'discardSignal={recordingDiscardSignal}',
  'onCollapse={() => setRecordingDisplayState(',
  'miniRecordingVisible',
];

for (const snippet of requiredRecordingAppSnippets) {
  if (!app.includes(snippet)) {
    throw new Error(`App.tsx is missing recording finish or overlay flow snippet: ${snippet}`);
  }
}

const requiredMeetingListProcessingSnippets = [
  'function StatusBadge',
  'processingRecordingMeeting',
  'refreshKey',
  "{ ...processingRecordingMeeting, status: 'processing' }",
  "const showHomeStatusBadge = status !== 'pending'",
  "status === 'analyzing' || status === 'recording'",
  '<ActivityIndicator color="#6657ff" size="small" style={styles.statusSpinner} />',
  "status === 'completed' && actions > 0 ? (",
  'statusSpinner',
];

for (const snippet of requiredMeetingListProcessingSnippets) {
  if (!meetingList.includes(snippet)) {
    throw new Error(`MeetingListScreen is missing processing loading status snippet: ${snippet}`);
  }
}

const requiredCreationSnippets = [
  "defaultMeetingTitle('recording', createdAtDate)",
  "defaultMeetingTitle('import')",
  "title_source: 'fallback'",
  'start_at: createdAt',
  'creatingRecordingMeeting',
  "setRecordingDisplayState('expanded')",
  "setRoute({ name: 'home' })",
  'creatingMeeting ?',
  "padStart(2, '0')",
];

const creationFiles = [app, meetingList, importMeeting, meetingTitle].join('\n');
for (const snippet of requiredCreationSnippets) {
  if (!creationFiles.includes(snippet)) {
    throw new Error(`Meeting creation UI is missing snippet: ${snippet}`);
  }
}

if (app.includes("onCreateMeeting={() => setRoute({ name: 'newMeeting' })}")) {
  throw new Error('Realtime recording must create a meeting directly instead of opening NewMeetingScreen.');
}

const requiredRecordingSnippets = [
  'Audio.Recording',
  'startRecording();',
  'pauseAsync()',
  'startAsync()',
  'stopAndUnloadAsync()',
  'isMeteringEnabled: true',
  'meteringToLevel',
  "type DisplayState = 'hidden' | 'expanded' | 'collapsed'",
  "effectiveDisplayState === 'collapsed'",
  'PanResponder.create',
  'miniPanResponder',
  'miniDragHandle',
  '<Animated.View {...miniPanResponder.panHandlers} style={styles.miniBar}>',
  '<Animated.View style={[styles.miniPanel',
  'onStartShouldSetPanResponder: () => false',
  'gesture.dy * 0.86',
  'tension: 170',
  'friction: 20',
  'miniScale',
  'fontSize: 22',
  "fontVariant: ['tabular-nums']",
  'width: 76',
  'flex: 1',
  'numberOfLines={1}',
  'transform: [{ scale: 1.01 }]',
  'waveformCompact: { gap: 2, height: 24, width: 52 }',
  'Math.max(9, baseHeight * 0.61)',
  'updateElapsedFromClock',
  'resetElapsedSeconds',
  'if (hours > 0) return [hours, minutes, seconds].map(twoDigits).join(\':\')',
  'const monotonicSeconds = Math.max(elapsedSecondsRef.current, safeSeconds)',
  'setInterval(updateElapsedFromClock, 250)',
  'setOnRecordingStatusUpdate((status) => {',
  'setMeteringLevel(meteringToLevel((status as { metering?: number }).metering));',
  'const controlIconName = isPaused ? \'play\' : \'pause\'',
  'showDisabledControl',
  'onPress={stopRecording}',
  'stoppingRef',
  'onDiscard',
  'const uriBeforeStop = activeRecording.getURI()',
  'const uri = uriBeforeStop || activeRecording.getURI()',
  'onProcessing(uri, endedAt, false)',
  'const waveform = useMemo(() => [8, 14, 10, 19, 12, 23, 15, 21, 11, 17], [])',
];

for (const snippet of requiredRecordingSnippets) {
  if (!recording.includes(snippet)) {
    throw new Error(`RecordingScreen is missing realtime recording behavior snippet: ${snippet}`);
  }
}

const miniBarStart = recording.indexOf('miniBar: {');
const miniBarEnd = recording.indexOf('miniWaveBlock:', miniBarStart);
if (miniBarStart === -1 || miniBarEnd === -1) {
  throw new Error('RecordingScreen is missing mini recording bar style block.');
}

const miniBarStyle = recording.slice(miniBarStart, miniBarEnd);
const requiredMiniBarStyleSnippets = [
  "miniBar: { backgroundColor: '#ffffff'",
  'left: 0',
  'right: 0',
  'bottom: 0',
  'minHeight: 120',
  'zIndex: 95',
  'elevation: 24',
  'borderTopLeftRadius: 28',
  'borderTopRightRadius: 28',
  'miniPanel:',
  'paddingTop: 7',
  'height: 24',
  'miniContentRow:',
  'minHeight: 81',
  "justifyContent: 'space-between'",
  'miniDragHandle:',
  "alignItems: 'center'",
];

for (const snippet of requiredMiniBarStyleSnippets) {
  if (!miniBarStyle.includes(snippet)) {
    throw new Error(`RecordingScreen mini bar must cover bottom navigation: ${snippet}`);
  }
}

const forbiddenMiniBarStyleSnippets = [
  'bottom: 88',
  'left: 14',
  'right: 14',
  'miniTimer: { color: \'#111827\', fontSize: 20, fontWeight: \'900\', marginLeft',
  'updateElapsedSeconds(0)',
];

for (const snippet of forbiddenMiniBarStyleSnippets) {
  if (miniBarStyle.includes(snippet)) {
    throw new Error(`RecordingScreen mini bar must not keep old floating layout: ${snippet}`);
  }
}

if (recording.includes('chevron-up') || recording.includes('miniDragIcon')) {
  throw new Error('RecordingScreen mini bar drag affordance must use a horizontal handle, not an arrow icon.');
}

const forbiddenRecordingSnippets = [
  'Speaker A',
  'Speaker B',
  "Alert.alert('",
  "setConfirmMode('stop')",
  "setConfirmMode('end')",
  'languagePill',
  'noticeIcon',
  'noticeTitle',
  'noticeText',
  'limitBanner',
  'elapsedSecondsRef.current < 1',
  'status.durationMillis',
  'Math.floor(status.durationMillis / 1000)',
  "busy ? <ActivityIndicator color=\"#ffffff\" size=\"small\" /> : <LucideIcon name={isPaused ? 'play' : 'pause'}",
  '单条录音上限',
];

for (const snippet of forbiddenRecordingSnippets) {
  if (recording.includes(snippet)) {
    throw new Error(`RecordingScreen must not show removed recording UI or old confirmation snippet: ${snippet}`);
  }
}

console.log('Recording upload UI static checks passed.');
