const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const nav = fs.readFileSync(path.join(root, 'src', 'components', 'BottomNav.tsx'), 'utf8');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');

const requiredSnippets = [
  "export type BottomTab = 'home' | 'knowledge' | 'recording' | 'todo' | 'me'",
  "{ key: 'home', label: '首页', icon: 'house' }",
  "{ key: 'knowledge', label: '知识库', icon: 'book-open' }",
  "{ key: 'recording', label: '麦克风', icon: 'mic' }",
  "{ key: 'todo', label: '待办', icon: 'square-check-big' }",
  "{ key: 'me', label: '我的', icon: 'user-round' }",
  'isRecordingTab',
  'styles.centerButton',
  "position: 'absolute'",
  'bottom: 0',
  'left: 0',
  'right: 0',
  'paddingBottom: 0',
  'minHeight: 101',
  'minHeight: 83',
  'transform: [{ translateY: -8 }]',
  'transform: [{ translateY: -22 }]',
  'borderColor: \'#ffffff\'',
  'height: 62',
  'width: 62',
];

for (const snippet of requiredSnippets) {
  if (!nav.includes(snippet)) {
    throw new Error(`BottomNav should be pinned to the screen bottom and is missing: ${snippet}`);
  }
}

if (nav.includes('paddingBottom: 12')) {
  throw new Error('BottomNav should not keep the old bottom padding gap.');
}

if (
  nav.includes('transform: [{ translateY: -5 }]') ||
  nav.includes('transform: [{ translateY: -6 }]') ||
  nav.includes('transform: [{ translateY: -10 }]')
) {
  throw new Error('BottomNav should move both icon and label together with the updated offset.');
}

const requiredAppSnippets = [
  "if (tab === 'recording')",
  "setRecordingDisplayState('expanded')",
  'createRecordingMeeting();',
  "setRoute({ name: 'home' })",
];

for (const snippet of requiredAppSnippets) {
  if (!app.includes(snippet)) {
    throw new Error(`BottomNav recording entry should reuse the existing recording flow and is missing: ${snippet}`);
  }
}

if (nav.includes("key: 'ai'") || nav.includes('enableAiAssistantUi')) {
  throw new Error('BottomNav should keep the RC1 five-item layout with Knowledge Base and center microphone.');
}

console.log('Bottom navigation UI static checks passed.');
