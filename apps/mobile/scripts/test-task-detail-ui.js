const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const screen = read('src/screens/TaskDetailScreen.tsx');
const todo = read('src/screens/TodoScreen.tsx');
const search = read('src/screens/TaskSearchScreen.tsx');
const app = read('App.tsx');
const api = read('src/api.ts');

const requiredSnippets = [
  [api, 'description?: string | null'],
  [api, 'reminder_offset_minutes?: number | null'],
  [api, 'attachments?: Array'],
  [api, 'export function updateTask('],
  [api, 'export async function uploadTaskAttachment('],
  [api, 'export function taskAttachmentUrl('],
  [screen, "import * as DocumentPicker from 'expo-document-picker'"],
  [screen, 'export function TaskDetailScreen'],
  [screen, 'initialTask: TaskListItem | null'],
  [screen, 'onTaskChange?: (task: TaskListItem) => void'],
  [screen, 'listTasks({'],
  [screen, 'response.items.find((item) => item.id === seed.id)'],
  [screen, 'getMeeting(meetingId)'],
  [screen, 'updateTaskStatus(task.id, nextStatus)'],
  [screen, "updateTask(task.id, patch)"],
  [screen, 'uploadTaskAttachment(task.id'],
  [screen, "taskAttachmentUrl(taskId, item.id"],
  [screen, 'function taskDescriptionValue(item: TaskListItem): string'],
  [screen, 'function normalizeDueDraft(value: string): string'],
  [screen, 'return `${year}-${month.padStart'],
  [screen, 'normalizeText(item.due_date) || normalizeText(item.deadline)'],
  [screen, "return `${monthDay} ${formatClock(due)}`"],
  [screen, 'function isOverdueTask(item: TaskListItem): boolean'],
  [screen, 'if (isCompletedTask(item)) return false'],
  [screen, "if (normalized === 'high') return { label: '高优先级'"],
  [screen, "if (normalized === 'medium') return { label: '中优先级'"],
  [screen, "if (normalized === 'low') return { label: '低优先级'"],
  [screen, "return { label: '未设置'"],
  [screen, '当前任务'],
  [screen, "renderSectionHeader('settings', '基本信息')"],
  [screen, "renderSectionHeader('bell', '提醒设置')"],
  [screen, "renderSectionHeader('file-text', `附件 (${attachments.length})`)"],
  [screen, '暂无附件'],
  [screen, '附件上传失败'],
  [screen, '<TextInput'],
  [screen, 'style={styles.descriptionInput}'],
  [screen, "onBlur={() => persistTaskPatch({ task: taskTitle(task) }, 'task')}"],
  [screen, "onBlur={() => persistTaskPatch({ description: taskDescriptionValue(task) || null }, 'description')}"],
  [screen, "onBlur={() => persistTaskPatch({ owner: ownerValue(task) || null }, 'owner')}"],
  [screen, '<Modal transparent visible={duePickerOpen}'],
  [screen, '<Modal transparent visible={priorityPickerOpen}'],
  [screen, '<Modal transparent visible={reminderPickerOpen}'],
  [screen, '截止前 1 小时'],
  [screen, '截止前 3 小时'],
  [screen, '截止前 5 小时'],
  [screen, '短信通知'],
  [screen, 'DocumentPicker.getDocumentAsync'],
  [screen, 'square-check-big'],
  [screen, "textDecorationLine: 'line-through'"],
  [screen, 'emptySquare'],
  [screen, 'FlatList'],
  [screen, 'SafeAreaView'],
  [todo, "return `${monthDay} ${formatClock(due)}`"],
  [search, "return `${monthDay} ${formatClock(due)}`"],
  [todo, 'onOpenTask?.(item)'],
  [todo, 'taskOverrides?: Record<string, Partial<TaskListItem>>'],
  [search, 'onOpenTask?.(item)'],
  [search, 'taskOverrides?: Record<string, Partial<TaskListItem>>'],
  [app, "import { TaskDetailScreen }"],
  [app, 'const [taskDetail, setTaskDetail]'],
  [app, 'const [taskOverrides, setTaskOverrides]'],
  [app, 'const activeTab = taskDetail ? null : bottomTabForRoute(route)'],
  [app, 'taskDetailOverlay'],
  [app, '<TaskDetailScreen'],
  [app, 'onTaskChange={handleTaskDetailChange}'],
  [app, 'setTaskDetail(null);'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Task detail UI is missing required snippet: ${snippet}`);
  }
}

const forbiddenScreenSnippets = [
  '接口优化方案_v2.docx',
  '性能测试报告.xlsx',
  '张三',
  '基本配置',
  '当前版本附件仅作为本页本机备注',
  '不会上传到服务器',
  'handleOpenMeeting',
  "initialTab: 'actions'",
  'sourceSegmentId: task?.source_segment_id || null',
  'evidenceText: task?.source_text || task?.source || null',
  'Math.random',
  'mock',
  'tailwind',
  'Iconify',
  'onclick=',
  'task-edit',
  '430px',
  'status-bar',
  'bottom-nav',
  'pencil-line',
  'handleEditPress',
];

for (const snippet of forbiddenScreenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Task detail UI must not contain forbidden snippet: ${snippet}`);
  }
}

console.log('Task detail UI static checks passed.');
