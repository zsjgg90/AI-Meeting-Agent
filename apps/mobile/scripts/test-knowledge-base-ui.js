const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const nav = fs.readFileSync(path.join(root, 'src', 'components', 'BottomNav.tsx'), 'utf8');
const config = fs.readFileSync(path.join(root, 'src', 'config.ts'), 'utf8');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'KnowledgeBaseScreen.tsx'), 'utf8');

const requiredSnippets = [
  [config, "enableAiAssistantUi: process.env.EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI === 'true'"],
  [config, "enableKnowledgeBaseUi: process.env.EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI !== 'false'"],
  [nav, "{ key: 'knowledge', label: '知识库', icon: 'book-open' }"],
  [nav, 'featureFlags.enableAiAssistantUi'],
  [app, "| { name: 'knowledge' }"],
  [app, "if (route.name === 'knowledge') return 'knowledge';"],
  [app, "if (tab === 'knowledge') setRoute({ name: 'knowledge' });"],
  [app, "{route.name === 'knowledge' && featureFlags.enableKnowledgeBaseUi ? <KnowledgeBaseScreen /> : null}"],
  [app, "featureFlags.enableAiAssistantUi && route.name === 'ai'"],
  [screen, '知识库'],
  [screen, '暂无知识内容'],
  [screen, '本阶段仅开放知识库入口和基础空状态'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Knowledge base UI is missing required snippet: ${snippet}`);
  }
}

console.log('Knowledge base UI static checks passed.');
