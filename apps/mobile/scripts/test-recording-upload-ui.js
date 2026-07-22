const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const api = fs.readFileSync(path.join(root, 'src', 'api.ts'), 'utf8');
const processing = fs.readFileSync(path.join(root, 'src', 'screens', 'AIProcessingScreen.tsx'), 'utf8');

const requiredApiSnippets = [
  'function audioUploadMetadata',
  "m4a: 'audio/x-m4a'",
  'async function fetchWithTimeout',
  'DEFAULT_REQUEST_TIMEOUT_MS',
  '网络请求超时，请稍后重试',
  'function friendlyUploadError',
  '录音文件格式暂不支持，请重新录制后上传',
  '录音文件为空，请重新录制',
  'fetchWithTimeout(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio`',
  'fetchWithTimeout(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio-chunks`',
  'friendlyUploadError(response.status, body)',
];

for (const snippet of requiredApiSnippets) {
  if (!api.includes(snippet)) {
    throw new Error(`api.ts is missing recording upload snippet: ${snippet}`);
  }
}

const forbiddenApiSnippets = [
  'throw new Error(body ||',
  'fetch(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio`',
  'fetch(`${apiBaseUrl.replace(/\\/+$/, \'\')}/meetings/${meetingId}/audio-chunks`',
];

for (const snippet of forbiddenApiSnippets) {
  if (api.includes(snippet)) {
    throw new Error(`api.ts must not use raw upload failure path: ${snippet}`);
  }
}

const requiredFlowSnippets = [
  'await uploadAudio(meeting.id, recordingUri, endedAt)',
  'await processMeeting(meeting.id)',
  'await analyzeMeeting(meeting.id)',
];

for (const snippet of requiredFlowSnippets) {
  if (!processing.includes(snippet)) {
    throw new Error(`AIProcessingScreen is missing recording processing flow snippet: ${snippet}`);
  }
}

console.log('Recording upload UI static checks passed.');
