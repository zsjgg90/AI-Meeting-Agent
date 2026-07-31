const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'MeetingListScreen.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');

const requiredScreenSnippets = [
  'const HISTORY_PAGE_SIZE = 30',
  'const HOME_MEETING_LIMIT = 10',
  'onMeetingCountChange?: (count: number) => void',
  'hasMoreMeetings',
  'loadingMore',
  'loadMoreMeetings',
  'listMeetings({ limit, offset })',
  'onEndReached={loadMoreMeetings}',
  'SectionList',
  'sections={meetingSections}',
  'groupMeetingsByDate(visibleMeetings, sectionClock)',
  'renderSectionHeader={({ section }) => <Text style={styles.meetingDateHeader}>{section.title}</Text>}',
  'renderSectionHeader={({ section }) => <Text style={[styles.meetingDateHeader, styles.historyDateHeader]}>{section.title}</Text>}',
  'recentListContentWithMiniRecording',
  'historyListContent',
  'historyContainer',
  'homeListContentWithMiniRecording',
  '加载更多',
];

for (const snippet of requiredScreenSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`MeetingListScreen is missing paged history loading snippet: ${snippet}`);
  }
}

const requiredAppSnippets = [
  'historyMeetingCount',
  'onMeetingCountChange={setHistoryMeetingCount}',
  '`历史会议（${historyMeetingCount}）`',
];

for (const snippet of requiredAppSnippets) {
  if (!app.includes(snippet)) {
    throw new Error(`App is missing history title count snippet: ${snippet}`);
  }
}

const requiredUnifiedCardSnippets = [
  'summary={summaryByMeeting[item.id]}',
  'compactHome={true}',
  'flushBottom={!selecting}',
  'cardFlushBottom',
  "const hasCompletedPreview = status === 'completed' && previewRows.length > 0",
  'previewRows.map((row)',
  'record.item',
  '会议总结：',
  '会议议程：',
  '核心结论：',
  '待办事项：',
  'summaryPreviewText(summary)',
  "status === 'completed' && actions > 0",
  '<Text style={[styles.actionCountText, styles.actionCountTextActive]}>{actions}项待办</Text>',
  'marginBottom: 8',
  'marginTop: 2',
  'marginTop: 5',
];

for (const snippet of requiredUnifiedCardSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`Meeting history/home unified card is missing snippet: ${snippet}`);
  }
}

const forbiddenUnifiedCardSnippets = [
  "{meetingSummaryPreview || '暂无'}",
  "{agendaPreview || '暂无'}",
  "{conclusionPreview || '暂无'}",
  "{actionPreview || '暂无'}",
  "'无待办'",
  'actions > 0 ? `${actions}项待办`',
];

for (const snippet of forbiddenUnifiedCardSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Meeting history/home unified card must hide empty AI preview rows instead of rendering fallback text: ${snippet}`);
  }
}

const requiredApiSnippets = [
  'DEFAULT_REQUEST_TIMEOUT_MS',
  'AbortController',
  '网络请求超时，请稍后重试',
  'limit',
  'offset',
];

for (const snippet of requiredApiSnippets) {
  if (!api.includes(snippet)) {
    throw new Error(`api.ts is missing bounded request/list loading snippet: ${snippet}`);
  }
}

if (screen.includes('const data = await listMeetings();')) {
  throw new Error('Meeting history must not load the unbounded meeting list.');
}

if (screen.includes('<ScrollView') || screen.includes('data={visibleMeetings}')) {
  throw new Error('Meeting list should use SectionList sections without same-direction nested scrolling or direct FlatList data.');
}

if (screen.includes('formatHomeSectionDate') || screen.includes('styles.recentDate')) {
  throw new Error('Home meeting list should not render a second date label above the date-section headers.');
}

if (screen.includes('共 {meetings.length} 场会议') || screen.includes('historySub')) {
  throw new Error('History meeting count should be shown in the header title, not as a separate subtitle.');
}

if (!screen.includes("selectToggleText: {\n    color: '#111827'") || !screen.includes("batchText: {\n    color: '#111827'")) {
  throw new Error('History selection controls should use black text.');
}

console.log('Meeting history UI static checks passed.');
