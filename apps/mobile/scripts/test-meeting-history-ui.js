const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'MeetingListScreen.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');

const requiredScreenSnippets = [
  'const HISTORY_PAGE_SIZE = 30',
  'const HOME_MEETING_LIMIT = 10',
  'hasMoreMeetings',
  'loadingMore',
  'loadMoreMeetings',
  'listMeetings({ limit, offset })',
  'onEndReached={loadMoreMeetings}',
  '加载更多',
];

for (const snippet of requiredScreenSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`MeetingListScreen is missing paged history loading snippet: ${snippet}`);
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

console.log('Meeting history UI static checks passed.');
