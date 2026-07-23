const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'AIProcessingScreen.tsx'), 'utf8');

const requiredSnippets = [
  "type StepStatus = 'pending' | 'running' | 'completed' | 'failed'",
  'function parseTaskError',
  'function failureStage',
  'function safeErrorMessage',
  'meetingDetail?.tasks',
  '重新分析',
  '查看错误详情',
  '会议纪要生成失败',
  '等待生成会议纪要',
  'await analyzeMeeting(meeting.id)',
];

for (const snippet of requiredSnippets) {
  if (!screen.includes(snippet)) {
    throw new Error(`AIProcessingScreen is missing required status-driven UI snippet: ${snippet}`);
  }
}

const forbiddenSnippets = [
  "await uploadAudio(meeting.id, recordingUri, endedAt);\n+      await analyzeMeeting(meeting.id)",
  'Traceback',
  'JSON.stringify(taskError)',
];

for (const snippet of forbiddenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`AIProcessingScreen exposes or mixes unsafe behavior: ${snippet}`);
  }
}

console.log('AI processing UI static checks passed.');
