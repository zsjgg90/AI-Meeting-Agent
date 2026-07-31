const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

const app = read('App.tsx');
const api = read('src/api.ts');
const nav = read('src/components/BottomNav.tsx');
const home = read('src/screens/KnowledgeBaseScreen.tsx');
const meetings = read('src/screens/KnowledgeMeetingListScreen.tsx');
const decisions = read('src/screens/KnowledgeDecisionListScreen.tsx');
const issues = read('src/screens/KnowledgeIssueRiskScreen.tsx');
const search = read('src/screens/KnowledgeSearchScreen.tsx');
const results = read('src/screens/KnowledgeSearchResultsScreen.tsx');
const filter = read('src/screens/KnowledgeFilterSheet.tsx');
const detail = read('src/screens/MeetingDetailScreen.tsx');

const requiredSnippets = [
  [api, 'getKnowledgeOverview'],
  [api, 'listKnowledgeMeetings'],
  [api, 'listKnowledgeDecisions'],
  [api, 'listKnowledgeIssues'],
  [api, 'listKnowledgeRisks'],
  [api, 'searchKnowledge'],
  [app, "| { name: 'knowledgeMeetings' }"],
  [app, "| { name: 'knowledgeSearchResults'; query: string }"],
  [app, 'openKnowledgeSource'],
  [app, 'initialTab={route.initialTab}'],
  [app, "onOpenImportAudio={() => setRoute({ name: 'importMeeting' })}"],
  [nav, "active === tab.key"],
  [home, 'MeetMind AI'],
  [home, '会议达人，有什么吩咐？'],
  [home, '最近会议重点是什么？'],
  [home, '帮我整理最近一周待办事项，并按负责人和优先级列出'],
  [home, '总结最近所有文件的核心结论和趋势变化'],
  [home, '当前版本暂未开放知识库问答'],
  [home, '当前版本没有知识库语音问答输入'],
  [home, '当前版本没有真实问答历史或持久化搜索历史'],
  [home, 'onOpenSearch(query)'],
  [home, 'FlatList'],
  [meetings, 'loadingMore'],
  [meetings, 'RefreshControl'],
  [meetings, 'KnowledgeMeetingCard'],
  [decisions, 'listKnowledgeDecisions'],
  [issues, "type Tab = 'issues' | 'risks'"],
  [issues, 'listKnowledgeRisks'],
  [results, 'KnowledgeFilterSheet'],
  [results, 'searchKnowledge'],
  [filter, "content_type: KnowledgeContentType"],
  [filter, "dateRange: 'all' | 'today' | '7d' | '30d'"],
  [detail, 'sourceSegmentId?: string | null'],
  [detail, 'evidenceText?.trim()'],
  [detail, 'scrollToIndex({ index: targetIndex'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Knowledge base UI is missing required snippet: ${snippet}`);
  }
}

const forbiddenHomeSnippets = [
  'answerKnowledge',
  'askKnowledge',
  'chatKnowledge',
  'mockAnswer',
  '模拟回答',
  'AI 回复：',
  '输入问题或按住说话',
  '知识库内容概览',
  "title: '会议知识'",
  "title: '待办知识'",
  "title: '文件知识'",
  'getKnowledgeOverview',
  'listKnowledgeMeetings({ limit: 1 })',
  'listTasks({ limit: 15 })',
];

for (const snippet of forbiddenHomeSnippets) {
  if (home.includes(snippet)) {
    throw new Error(`Knowledge base home must not include unsupported Q&A or voice behavior: ${snippet}`);
  }
}

console.log('Knowledge base UI static checks passed.');
