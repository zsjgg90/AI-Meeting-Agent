const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const screen = read('src/screens/TodoScreen.tsx');
const app = read('App.tsx');
const api = read('src/api.ts');

const requiredSnippets = [
  [api, 'export function listTasks'],
  [api, 'export function updateTaskStatus'],
  [api, "`/tasks/${encodeURIComponent(taskId)}/status`"],
  [api, "method: 'PATCH'"],
  [screen, 'listTasks({'],
  [screen, 'updateTaskStatus(task.id, nextStatus)'],
  [screen, 'previousTask'],
  [screen, 'setUpdatingTaskIds'],
  [screen, "Alert.alert('更新失败'"],
  [screen, 'FlatList'],
  [screen, 'RefreshControl'],
  [screen, "type TaskStatusFilter = 'all' | 'completed' | 'overdue'"],
  [screen, 'const completedStatuses = new Set'],
  [screen, 'function isOverdueTask'],
  [screen, 'function formatDueDate'],
  [screen, 'priorityMeta(item.priority)'],
  [screen, '<LucideIcon name="square-check-big"'],
  [screen, 'emptySquare'],
  [screen, 'handleStatusPress(item);'],
  [screen, '<ActivityIndicator color="#2B6CFF" size="small" />'],
  [screen, 'pendingCompletedTaskIds'],
  [screen, 'setTimeout(() => {'],
  [screen, '}, 300);'],
  [screen, 'stats.all'],
  [screen, 'stats.completed'],
  [screen, 'stats.overdue'],
  [screen, 'loadTasks(\'more\')'],
  [screen, 'loadMoreError'],
  [screen, 'onOpenTask?: (task: TaskListItem) => void'],
  [screen, 'taskOverrides?: Record<string, Partial<TaskListItem>>'],
  [screen, 'displayedTasks'],
  [screen, 'onOpenTask?.(item)'],
  [screen, '<Pressable onPress={() => openTask(item)} style={[styles.card, completed ? styles.cardDone : null]}>'],
  [screen, 'event.stopPropagation();'],
  [app, '<TodoScreen'],
  [app, "onOpenSearch={() => setRoute({ name: 'taskSearch' })}"],
  [app, 'onOpenTask={handleOpenTask}'],
  [app, 'taskOverrides={taskOverrides}'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Todo UI is missing required snippet: ${snippet}`);
  }
}

const forbiddenSnippets = [
  'toggleTask(',
  'setCompletedTaskIds',
  'setVisualCompletedTaskIds',
  'completedAt',
  'getMeetingSummary',
  '暂不支持更新',
  '12</Text>',
  '48</Text>',
  'onclick=',
  'Iconify',
  'tailwind',
  'const filters:',
  'filters.map',
  'filterTabs',
  'filterTabActive',
  "setStatusFilter('completed')",
  '}, 500);',
  "type TaskStatusFilter = 'all' | 'open'",
  "key: 'open' as const",
  'stats.open',
  'searchOpen',
  'searchText',
  'setSearchText',
  'q: searchText',
  'TextInput',
  'emptyCircle',
  'circle-check-big',
  'meetingTitle',
  'ownerTag',
  'statusTag',
];

for (const snippet of forbiddenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Todo UI must not contain forbidden snippet: ${snippet}`);
  }
}

console.log('Todo UI static checks passed.');
