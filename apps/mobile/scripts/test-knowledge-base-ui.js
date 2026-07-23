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
  [nav, "{ key: 'knowledge', label: '知识库', icon: 'book-open' }"],
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
  [home, '会议记录'],
  [home, '关键决策'],
  [home, '问题与风险'],
  [home, '全部知识'],
  [home, '知识搜索'],
  [home, '最近会议'],
  [meetings, 'loadingMore'],
  [meetings, 'RefreshControl'],
  [meetings, 'KnowledgeMeetingCard'],
  [decisions, 'listKnowledgeDecisions'],
  [issues, "type Tab = 'issues' | 'risks'"],
  [issues, 'listKnowledgeRisks'],
  [search, '最近搜索'],
  [results, 'KnowledgeFilterSheet'],
  [results, 'searchKnowledge'],
  [filter, "content_type: KnowledgeContentType"],
  [filter, "dateRange: 'all' | 'today' | '7d' | '30d'"],
  [detail, 'sourceSegmentId?: string | null'],
  [detail, 'setTranscriptSearch(evidenceText.trim())'],
];

for (const [source, snippet] of requiredSnippets) {
  if (snippet === '最近会议') {
    if (source.includes(snippet)) {
      throw new Error('Knowledge base home must not show recent meetings.');
    }
    continue;
  }
  if (!source.includes(snippet)) {
    throw new Error(`Knowledge base UI is missing required snippet: ${snippet}`);
  }
}

if (home.includes('AI 问答') || home.includes('AI 助手')) {
  throw new Error('Knowledge base home must not expose AI assistant or AI Q&A.');
}

console.log('Knowledge base UI static checks passed.');
