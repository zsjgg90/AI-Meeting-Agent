const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'MeetingDetailScreen.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const icons = fs.readFileSync(path.join(root, 'src', 'components', 'LucideIcon.tsx'), 'utf8');
const agentStart = screen.indexOf('function renderAgentToolsTab');
const agentEnd = screen.indexOf('function renderAgentTab', agentStart);
const agentUi = agentStart >= 0 && agentEnd > agentStart ? screen.slice(agentStart, agentEnd) : '';

const requiredScreenSnippets = [
  'function renderAgentToolsTab',
  'const unavailableAgentTools',
  '邮箱推送',
  '当前版本暂未接入邮箱推送',
  '飞书任务',
  '当前版本尚未接入飞书任务',
  '思维导图',
  '当前版本暂未接入正式思维导图生成',
  '知识库',
  'reindexMeetingKnowledge(meetingId)',
  "runningAgentTool === 'knowledge'",
  'disabled={checkingAgentTools || Boolean(runningAgentTool)}',
  '暂无工具使用记录',
  '当前项目尚未提供邮箱、飞书、思维导图或知识库工具执行记录接口。',
  '更多功能即将上线',
  "activeTab === 'agent' ? renderAgentToolsTab() : null",
];

for (const snippet of requiredScreenSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`Meeting Agent tools UI is missing required snippet: ${snippet}`);
  }
}

for (const forbidden of ['已推送到关联邮箱', '已生成飞书待办任务', 'setTimeout(() =>', 'SMTP', 'Gmail']) {
  if (agentUi.includes(forbidden)) {
    throw new Error(`Meeting Agent tools UI must not fake unavailable tool results: ${forbidden}`);
  }
}

if (!api.includes('export type KnowledgeSync') || !api.includes('export function reindexMeetingKnowledge')) {
  throw new Error('api.ts must expose the existing knowledge reindex endpoint.');
}

if (!app.includes("initialTab?: 'summary' | 'transcript' | 'agent'") || !app.includes("onOpenKnowledgeBase={() => setRoute({ name: 'knowledge' })}")) {
  throw new Error('App must preserve detail routing and pass the existing knowledge route to MeetingDetailScreen.');
}

for (const icon of ["'mail'", "'git-branch'", "'book-open'", "'clock-3'"]) {
  if (!icons.includes(icon)) {
    throw new Error(`LucideIcon is missing required Agent tool icon: ${icon}`);
  }
}

console.log('Meeting Agent tools UI static checks passed.');
