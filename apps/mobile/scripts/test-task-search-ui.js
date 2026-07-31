const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const screen = read('src/screens/TaskSearchScreen.tsx');
const todo = read('src/screens/TodoScreen.tsx');
const app = read('App.tsx');
const api = read('src/api.ts');
const pkg = JSON.parse(read('package.json'));

const requiredSnippets = [
  [api, 'export function listTasks'],
  [api, 'export function updateTaskStatus'],
  [api, 'q?: string'],
  [pkg.dependencies['@react-native-async-storage/async-storage'] || '', '2.2.0'],
  [screen, "import AsyncStorage from '@react-native-async-storage/async-storage'"],
  [screen, 'export function TaskSearchScreen'],
  [screen, 'TASK_SEARCH_HISTORY_KEY'],
  [screen, 'MAX_RECENT_SEARCHES = 10'],
  [screen, 'submittedKeyword'],
  [screen, 'function handleQueryChange(value: string)'],
  [screen, 'function submitSearch(value?: string)'],
  [screen, 'onChangeText={handleQueryChange}'],
  [screen, 'onSubmitEditing={(event: NativeSyntheticEvent<TextInputSubmitEditingEventData>) => submitSearch(event.nativeEvent.text)}'],
  [screen, 'enablesReturnKeyAutomatically'],
  [screen, 'autoCorrect={false}'],
  [screen, 'autoCapitalize="none"'],
  [screen, 'requestSeqRef'],
  [screen, 'latestKeywordRef'],
  [screen, 'listTasks({'],
  [screen, 'q: normalized'],
  [screen, "offset: mode === 'more' ? results.length : 0"],
  [screen, 'updateTaskStatus(task.id, nextStatus)'],
  [screen, 'previousTask'],
  [screen, 'setUpdatingTaskIds'],
  [screen, 'autoFocus'],
  [screen, 'inputRef.current?.focus'],
  [screen, 'clearQuery'],
  [screen, 'removeRecentSearch'],
  [screen, 'clearRecentSearches'],
  [screen, 'onOpenTask?.(item)'],
  [screen, 'onOpenTask?: (task: TaskListItem) => void'],
  [screen, 'taskOverrides?: Record<string, Partial<TaskListItem>>'],
  [screen, 'displayedResults'],
  [screen, '<Pressable onPress={() => handleOpenTask(item)} style={[styles.card, completed ? styles.cardDone : null]}>'],
  [screen, 'event.stopPropagation();'],
  [screen, "Alert.alert('更新失败'"],
  [screen, 'KeyboardAvoidingView'],
  [screen, 'FlatList'],
  [screen, '<LucideIcon name="square-check-big"'],
  [screen, 'emptySquare'],
  [screen, 'priorityMeta(item.priority)'],
  [todo, 'onOpenSearch?: () => void'],
  [todo, 'onOpenSearch?.();'],
  [app, "import { TaskSearchScreen }"],
  [app, "| { name: 'taskSearch' }"],
  [app, "onOpenSearch={() => setRoute({ name: 'taskSearch' })}"],
  [app, '<TaskSearchScreen'],
  [app, "onBack={() => setRoute({ name: 'todo' })}"],
  [app, 'onOpenTask={handleOpenTask}'],
  [app, 'taskOverrides={taskOverrides}'],
  [app, 'overlayScreen'],
  [app, 'taskDetailOverlay'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Task search UI is missing required snippet: ${snippet}`);
  }
}

const forbiddenSnippets = [
  '接口优化',
  'PRD 更新',
  'mock',
  'tailwind',
  'Iconify',
  'onclick=',
  'meetmind-app',
  'status-bar',
  'bottom-nav',
  'Math.random',
  'getMeetingSummary',
  '}, 300)',
  "}, 300);",
  'onChangeText={setQuery}',
  'searchSubmitButton',
  'searchSubmitText',
  'meetingTitle',
  'statusTag',
  'ownerTag',
];

for (const snippet of forbiddenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Task search UI must not contain forbidden snippet: ${snippet}`);
  }
}

const handleQueryChangeMatch = screen.match(/function handleQueryChange\(value: string\) \{[\s\S]*?\n  \}/);
if (!handleQueryChangeMatch) {
  throw new Error('Task search UI must define handleQueryChange.');
}
if (handleQueryChangeMatch[0].includes('runSearch(') || handleQueryChangeMatch[0].includes('listTasks(')) {
  throw new Error('Task search input changes must not trigger API searches.');
}

const submitSearchMatch = screen.match(/function submitSearch\(value\?: string\) \{[\s\S]*?\n  \}/);
if (!submitSearchMatch || !submitSearchMatch[0].includes("runSearch(submittedValue, 'reset')")) {
  throw new Error('Task search must run after IME submit with the submitted text.');
}

console.log('Task search UI static checks passed.');
