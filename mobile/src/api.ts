export type MeetingCreated = {
  meeting_id: string;
  status: string;
};

export type TaskCreated = {
  task_id: string;
  meeting_id: string;
  status: string;
};

export type TaskRead = {
  id: string;
  meeting_id: string;
  status: string;
  error_message: string | null;
};

export type MeetingRead = {
  id: string;
  title: string;
  status: string;
  output: null | {
    raw_transcript: string;
    speaker_segments: Array<{ speaker: string; text: string }>;
    summary: string;
    action_items: Array<Record<string, string>>;
    decisions: Array<Record<string, string>>;
  };
};

function cleanBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '');
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function createMeeting(baseUrl: string, title: string): Promise<MeetingCreated> {
  return requestJson(`${cleanBaseUrl(baseUrl)}/meetings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function uploadAudio(baseUrl: string, meetingId: string, uri: string): Promise<void> {
  const form = new FormData();
  form.append('file', {
    uri,
    name: 'meeting-recording.m4a',
    type: 'audio/m4a',
  } as any);

  const response = await fetch(`${cleanBaseUrl(baseUrl)}/meetings/${meetingId}/audio`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Upload failed with status ${response.status}`);
  }
}

export async function startTranscription(baseUrl: string, meetingId: string): Promise<TaskCreated> {
  return requestJson(`${cleanBaseUrl(baseUrl)}/meetings/${meetingId}/process`, {
    method: 'POST',
  });
}

export async function getTask(baseUrl: string, taskId: string): Promise<TaskRead> {
  return requestJson(`${cleanBaseUrl(baseUrl)}/tasks/${taskId}`);
}

export async function getMeeting(baseUrl: string, meetingId: string): Promise<MeetingRead> {
  return requestJson(`${cleanBaseUrl(baseUrl)}/meetings/${meetingId}`);
}
