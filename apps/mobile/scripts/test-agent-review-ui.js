const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'AIAssistantScreen.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');

const requiredScreenSnippets = [
  'Agent Review',
  'Proposal Detail',
  'Approve proposal?',
  'Reject proposal?',
  'conflict',
  'expired',
  'duplicate',
  'Dry-run selected command',
  'Audit Records',
  'Rollback preview',
  'Writes performed',
];

const requiredApiSnippets = [
  'listAgentProposals',
  'approveAgentProposal',
  'rejectAgentProposal',
  'dryRunAgentCommand',
  'listAgentCommandAudits',
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

console.log('Agent review UI static checks passed.');
