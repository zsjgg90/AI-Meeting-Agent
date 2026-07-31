const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'App.tsx'), 'utf8');
const appHeader = fs.readFileSync(path.join(root, 'src', 'components', 'AppHeader.tsx'), 'utf8');
const profile = fs.readFileSync(path.join(root, 'src', 'screens', 'ProfileScreen.tsx'), 'utf8');
const help = fs.readFileSync(path.join(root, 'src', 'screens', 'HelpFeedbackScreen.tsx'), 'utf8');
const faq = fs.readFileSync(path.join(root, 'src', 'screens', 'FaqScreen.tsx'), 'utf8');
const feedback = fs.readFileSync(path.join(root, 'src', 'screens', 'FeedbackScreen.tsx'), 'utf8');
const about = fs.readFileSync(path.join(root, 'src', 'screens', 'AboutScreen.tsx'), 'utf8');

const requiredSnippets = [
  { name: 'AppHeader.tsx', source: appHeader, snippets: [
    'accentColor?: string',
    "const nextAccentColor = accentColor || '#111827'",
    'color={nextAccentColor}',
    'accentColor ? { color: accentColor } : null',
  ] },
  { name: 'ProfileScreen.tsx', source: profile, snippets: [
    'color="#111827" size={22}',
    "icon: 'message-square'",
    "icon: 'info'",
  ] },
  { name: 'HelpFeedbackScreen.tsx', source: help, snippets: [
    'icon?: LucideIconName',
    'function HelpEntry',
    "shadowColor: '#6b7280'",
  ] },
  { name: 'FaqScreen.tsx', source: faq, snippets: [
    "backgroundColor: '#f7f8fc'",
    "color: '#111827'",
  ] },
  { name: 'FeedbackScreen.tsx', source: feedback, snippets: [
    "backgroundColor: '#eaf1ff'",
    "borderColor: '#bcd3ff'",
    "backgroundColor: '#2B6CFF'",
  ] },
  { name: 'AboutScreen.tsx', source: about, snippets: [
    '当前版本 V1.0.0',
    "backgroundColor: '#f7f8fc'",
    "shadowColor: '#6b7280'",
    "backgroundColor: '#111827'",
    "color: '#2B6CFF'",
  ] },
];

for (const file of requiredSnippets) {
  for (const snippet of file.snippets) {
    if (!file.source.includes(snippet)) {
      throw new Error(`${file.name} is missing profile UI snippet: ${snippet}`);
    }
  }
}

const forbiddenAppSnippets = [
  'profileAccentHeader',
  "accentColor={profileAccentHeader ? '#2B6CFF' : undefined}",
];

for (const snippet of forbiddenAppSnippets) {
  if (app.includes(snippet)) {
    throw new Error(`Profile help/about headers must stay black and must not use: ${snippet}`);
  }
}

const forbiddenProfileSnippets = [
  'isBlueEntry',
  "color={item.accent || isBlueEntry ? '#2B6CFF' : '#111827'}",
];

for (const snippet of forbiddenProfileSnippets) {
  if (profile.includes(snippet)) {
    throw new Error(`Profile help/about entry icons must stay black and must not use: ${snippet}`);
  }
}

const forbiddenHelpSnippets = [
  'styles.entryIcon',
  'entryIcon:',
  '<LucideIcon name={icon}',
];

for (const snippet of forbiddenHelpSnippets) {
  if (help.includes(snippet)) {
    throw new Error(`HelpFeedbackScreen help entries must not show left icons: ${snippet}`);
  }
}

const forbiddenPurpleSnippets = ['#6c4dff', '#f0edff', '#d9d2ff', '#b3a5ff'];
for (const [name, source] of [
  ['HelpFeedbackScreen.tsx', help],
  ['FaqScreen.tsx', faq],
  ['FeedbackScreen.tsx', feedback],
  ['AboutScreen.tsx', about],
]) {
  for (const snippet of forbiddenPurpleSnippets) {
    if (source.includes(snippet)) {
      throw new Error(`${name} must not use old purple profile style: ${snippet}`);
    }
  }
}

if (about.includes('v1.0.0') || about.includes('当前版本 v')) {
  throw new Error('AboutScreen must display the current version as V1.0.0.');
}

console.log('Profile UI static checks passed.');
