const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const profile = fs.readFileSync(path.join(root, 'src', 'screens', 'ProfileScreen.tsx'), 'utf8');
const screen = fs.readFileSync(path.join(root, 'src', 'screens', 'PushConfigScreen.tsx'), 'utf8');

const requiredSnippets = [
  [app, "import { PushConfigScreen }"],
  [app, "{ name: 'pushConfig' }"],
  [app, "onPushConfig={() => setRoute({ name: 'pushConfig' })}"],
  [app, "<PushConfigScreen onBack={() => setRoute({ name: 'me' })} />"],
  [profile, 'onPushConfig: () => void'],
  [profile, "onPress: onPushConfig"],
  [screen, '推送配置'],
  [screen, '让 AI 自动分发会议纪要、任务和提醒'],
  [screen, '飞书推送'],
  [screen, '连接后自动同步会议纪要和任务'],
  [screen, '邮箱推送'],
  [screen, '短信提醒'],
  [screen, '高优先级任务、风险事项、截止提醒'],
  [screen, '未配置'],
  [screen, '暂未开放'],
  [screen, '待接入'],
  [screen, 'disabled'],
  [screen, 'value={false}'],
];

for (const [source, snippet] of requiredSnippets) {
  if (!source.includes(snippet)) {
    throw new Error(`Push config UI is missing required snippet: ${snippet}`);
  }
}

const forbiddenSnippets = [
  '飞书连接成功',
  '邮件发送成功',
  '短信发送成功',
  'OAuth',
  'SMTP',
  'sendEmail',
  'sendSms',
  'sendFeishu',
  'pushHistory',
];

for (const snippet of forbiddenSnippets) {
  if (screen.includes(snippet)) {
    throw new Error(`Push config UI must not imply unavailable push capability: ${snippet}`);
  }
}

console.log('Push config UI static checks passed.');
