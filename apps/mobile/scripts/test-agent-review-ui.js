const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'AIAssistantScreen.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');

const requiredScreenSnippets = [
  'AI 助手',
  'AI 根据会议内容提出修改建议，需要你的确认',
  '你控制节奏，数据安全有保障',
  '所有修改都需要你确认后才会生效',
  '待你确认的建议',
  '全部建议',
  '修改前',
  '修改后（建议）',
  '会议原话证据',
  '不采纳',
  '采纳建议',
  '确认采纳这条建议？',
  '采纳后系统会生成待执行命令，不会直接修改数据。',
  '确认不采纳这条建议？',
  '建议已采纳，等待执行',
  '最近处理',
  '全部记录',
  '全部状态',
  '按时间排序',
  '加载更多',
  '查看原因',
  '详情',
  'Audit 时间线',
  '是否真实写入',
  '对象版本变化',
  '登录状态已失效，请重新登录',
  '暂无权限查看 AI 建议',
  'AI 建议加载失败',
  '重新登录',
  '本地登录存储不可用，请重启应用',
];

const requiredApiSnippets = [
  'getAgentReviewOverview',
  'listAgentReviewRecords',
  'getAgentReviewRecord',
  'listAgentProposals',
  'approveAgentProposal',
  'rejectAgentProposal',
  'loginAgentSession',
  'loadStoredAgentSession',
  'clearAgentSession',
  'AgentStorageError',
  'storage_unavailable',
  'getAsyncStorage',
  "await import('@react-native-async-storage/async-storage')",
  'suppressStorageError',
  'useAgentSessionInMemory',
  'isAgentStorageError',
  'AGENT_SESSION_STORAGE_KEY',
  "path.startsWith('/agent/')",
  "headers.set('Authorization'",
  '登录已失效，请重新登录后再试',
  '你没有权限处理这条建议',
  '数据已更新，请刷新后再处理',
  '这条建议已过期',
  '这条建议已被其他人处理',
];

for (const snippet of requiredScreenSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`AIAssistantScreen is missing required Agent review UI snippet: ${snippet}`);
  }
}

for (const snippet of requiredApiSnippets) {
  if (!api.includes(snippet)) {
    throw new Error(`api.ts is missing required Agent API helper: ${snippet}`);
  }
}

const submittedBodies = Array.from(api.matchAll(/body:\s*JSON\.stringify\(([\s\S]*?)\)/g)).map((match) => match[1]).join('\n');

if (submittedBodies.includes('expected_object_version')) {
  throw new Error('Client API helpers must not submit expected_object_version.');
}

if (submittedBodies.includes('idempotency_key')) {
  throw new Error('Client API helpers must not submit idempotency_key.');
}

if (submittedBodies.includes('changes')) {
  throw new Error('Client API helpers must not submit Agent command changes.');
}

if (submittedBodies.includes('permissions')) {
  throw new Error('Client API helpers must not submit Agent permissions.');
}

if (submittedBodies.includes('tenant_id') || submittedBodies.includes('project_id')) {
  throw new Error('Client API helpers must not submit tenant/project scope.');
}

if (submittedBodies.includes('reviewer')) {
  throw new Error('Client API helpers must not submit reviewer identity.');
}

if (api.includes('X-Agent-Reviewer') || api.includes('X-Agent-Permissions')) {
  throw new Error('Client API helpers must not submit Agent identity or permissions headers.');
}

if (api.includes("import AsyncStorage from '@react-native-async-storage/async-storage'")) {
  throw new Error('AsyncStorage must not be touched by a top-level static import.');
}

if (!api.includes('await clearAgentSession({ suppressStorageError: true })')) {
  throw new Error('Agent 401 handling must clear the in-memory session even when storage is unavailable.');
}

if (!screen.includes('isAgentStorageError(err) && getAgentAuthToken()')) {
  throw new Error('AI assistant must keep using the in-memory token when persistent storage is unavailable.');
}

if (!screen.includes("setViewState('error')") || !screen.includes('本地登录存储不可用，请重启应用')) {
  throw new Error('AI assistant must show a Chinese storage-unavailable state instead of crashing.');
}

const forbiddenScreenSnippets = [
  'Dry-run selected command',
  'Execute internal pilot?',
  'Rollback internal pilot?',
  'Pilot Write Result',
  'Rollback preview',
];

for (const snippet of forbiddenScreenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Productized AI assistant UI must not expose internal pilot control: ${snippet}`);
  }
}

console.log('Agent review UI static checks passed.');
