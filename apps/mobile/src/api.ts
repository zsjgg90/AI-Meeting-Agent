import { apiBaseUrl } from './config';

export type Meeting = {
  id: string;
  title: string;
  status: string;
  start_at: string | null;
  end_at: string | null;
  location: string | null;
  created_at: string;
  updated_at: string;
};

export type AudioFile = {
  id: string;
  filename: string;
  content_type: string | null;
  path: string;
  file_size_bytes: number;
  uploaded_at: string;
};

export type TranscriptSegment = {
  id: string;
  audio_file_id: string | null;
  segment_index: number;
  start_time: number;
  end_time: number;
  text: string;
  speaker_label: string | null;
  speaker_name: string | null;
  speaker_gender: string | null;
  semantic_label: string | null;
  created_at: string;
};

export type ActionItem = {
  id: string;
  task: string;
  owner: string | null;
  owner_name: string | null;
  due_date: string | null;
  deadline: string | null;
  priority: string | null;
  status: string;
  source: string | null;
  source_text: string | null;
  source_segment_id: string | null;
  confidence: number | null;
  created_at: string;
  updated_at: string;
};

export type TaskListItem = ActionItem & {
  meeting_id: string;
  meeting_title: string;
};

export type TaskListResponse = {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type SpeakerMapping = {
  id: string;
  speaker_label: string;
  display_name: string;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type MeetingSummary = {
  id?: string;
  overview?: string | null;
  agenda: Array<Record<string, any>>;
  topics: Array<Record<string, any>>;
  speaker_summaries?: Array<Record<string, any>>;
  decisions: Array<Record<string, any>>;
  risks: Array<Record<string, any>>;
  open_questions: Array<Record<string, any>>;
  next_steps?: Array<Record<string, any>>;
  meeting_agenda: Array<Record<string, any>>;
  meeting_summary: string | null;
  key_conclusions: Array<Record<string, any>>;
  unresolved_issues: Array<Record<string, any>>;
  risks_and_focus: Array<Record<string, any>>;
  model_name?: string | null;
  confidence_score?: number | null;
  metadata?: {
    schema_version?: string;
    model_name?: string;
    result_source?: 'fixture' | 'legacy_qwen_rag' | 'semantic_pipeline' | 'unknown' | string;
    confidence_score?: number;
    generated_at?: string;
    [key: string]: any;
  };
  action_items: ActionItem[];
  created_at?: string;
  updated_at?: string;
};

export type MeetingDetail = Meeting & {
  audio_files: AudioFile[];
  transcript_segments: TranscriptSegment[];
  summary: MeetingSummary | null;
  action_items: ActionItem[];
  speaker_mappings: SpeakerMapping[];
  output: null | {
    raw_transcript: string;
    speaker_segments: Array<{ speaker: string; text: string }>;
    summary: string;
    action_items: Array<Record<string, string>>;
    decisions: Array<Record<string, string>>;
  };
};

export type MeetingCreated = {
  id: string;
  title: string;
  status: string;
};

export type AudioUploaded = {
  audio_file_id: string;
  meeting_id: string;
  filename: string;
  path: string;
  file_size_bytes: number;
};

export type AudioChunkUploaded = AudioUploaded & {
  start_offset_seconds: number;
  transcript_segment_count: number;
};

export type ProcessStarted = {
  task_id: string;
  meeting_id: string;
  status: string;
};

export type MeetingTranscript = {
  meeting_id: string;
  status: string;
  raw_transcript: string | null;
  segments: TranscriptSegment[];
  speaker_segments: Array<Record<string, any>>;
};

export type MeetingBulkDeleteResult = {
  deleted_count: number;
};

export type FeedbackPayload = {
  feedback_type: string;
  description: string;
  contact?: string | null;
  image_urls?: string[];
};

export type FeedbackCreated = FeedbackPayload & {
  id: string;
  status: string;
  created_at: string;
};

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, '')}${path}`, options);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `请求失败，状态码：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listMeetings(): Promise<Meeting[]> {
  return requestJson<Meeting[]>('/meetings');
}

export function listTasks(options?: {
  limit?: number;
  offset?: number;
  meeting_id?: string;
  q?: string;
}): Promise<TaskListResponse> {
  const params = new URLSearchParams();
  params.set('limit', String(options?.limit ?? 15));
  params.set('offset', String(options?.offset ?? 0));
  if (options?.meeting_id && options.meeting_id !== 'all') {
    params.set('meeting_id', options.meeting_id);
  }
  if (options?.q?.trim()) {
    params.set('q', options.q.trim());
  }
  return requestJson<TaskListResponse>(`/tasks?${params.toString()}`);
}

export function createMeeting(
  title: string,
  options?: { start_at?: string; end_at?: string; location?: string },
): Promise<MeetingCreated> {
  return requestJson<MeetingCreated>('/meetings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, ...options }),
  });
}

export function getMeeting(meetingId: string): Promise<MeetingDetail> {
  return requestJson<MeetingDetail>(`/meetings/${meetingId}`);
}

export function getMeetingSummary(meetingId: string): Promise<MeetingSummary & { meeting_id: string; status: string; summary?: string | null }> {
  return requestJson<MeetingSummary & { meeting_id: string; status: string; summary?: string | null }>(`/meetings/${meetingId}/summary`);
}

export function getMeetingTranscript(meetingId: string): Promise<MeetingTranscript> {
  return requestJson<MeetingTranscript>(`/meetings/${meetingId}/transcript`);
}

export async function deleteMeeting(meetingId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `删除失败，状态码：${response.status}`);
  }
}

export function bulkDeleteMeetings(meetingIds: string[]): Promise<MeetingBulkDeleteResult> {
  return requestJson<MeetingBulkDeleteResult>('/meetings/bulk-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ meeting_ids: meetingIds }),
  });
}

export function updateMeeting(
  meetingId: string,
  options: { start_at?: string; end_at?: string; location?: string | null },
): Promise<MeetingDetail> {
  return requestJson<MeetingDetail>(`/meetings/${meetingId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });
}

export function meetingAudioUrl(meetingId: string, audioFileId: string): string {
  return `${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/audio/${audioFileId}`;
}

export function meetingExportUrl(meetingId: string, kind: 'transcript' | 'summary', format: 'md' | 'pdf' | 'docx' | 'txt'): string {
  return `${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/exports/${kind}.${format}`;
}

function audioUploadMetadata(uri: string): { name: string; type: string } {
  const cleanUri = uri.split('?')[0] || uri;
  const rawName = cleanUri.split('/').pop() || 'meeting-recording.m4a';
  const extension = rawName.includes('.') ? rawName.split('.').pop()?.toLowerCase() : 'm4a';
  const normalizedExtension = extension || 'm4a';
  const typeByExtension: Record<string, string> = {
    aac: 'audio/aac',
    m4a: 'audio/x-m4a',
    mp3: 'audio/mpeg',
    mp4: 'audio/mp4',
    mpeg: 'audio/mpeg',
    mpga: 'audio/mpeg',
    wav: 'audio/wav',
    webm: 'audio/webm',
    ogg: 'audio/ogg',
  };

  return {
    name: rawName.includes('.') ? rawName : `meeting-recording.${normalizedExtension}`,
    type: typeByExtension[normalizedExtension] || 'application/octet-stream',
  };
}

export async function uploadAudio(meetingId: string, uri: string, endedAt?: string): Promise<AudioUploaded> {
  const metadata = audioUploadMetadata(uri);
  const form = new FormData();
  form.append('file', {
    uri,
    name: metadata.name,
    type: metadata.type,
  } as any);
  if (endedAt) {
    form.append('ended_at', endedAt);
  }

  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/audio`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `上传失败，状态码：${response.status}`);
  }
  return response.json() as Promise<AudioUploaded>;
}

export async function uploadAudioChunk(
  meetingId: string,
  uri: string,
  startOffsetSeconds: number,
  endedAt?: string,
): Promise<AudioChunkUploaded> {
  const metadata = audioUploadMetadata(uri);
  const form = new FormData();
  form.append('file', {
    uri,
    name: metadata.name,
    type: metadata.type,
  } as any);
  form.append('start_offset_seconds', String(startOffsetSeconds));
  if (endedAt) {
    form.append('ended_at', endedAt);
  }

  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/audio-chunks`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `实时音频分片上传失败，状态码：${response.status}`);
  }
  return response.json() as Promise<AudioChunkUploaded>;
}

export function processMeeting(meetingId: string): Promise<ProcessStarted> {
  return requestJson<ProcessStarted>(`/meetings/${meetingId}/process`, {
    method: 'POST',
  });
}

export function analyzeMeeting(meetingId: string): Promise<ProcessStarted> {
  return requestJson<ProcessStarted>(`/meetings/${meetingId}/analyze`, {
    method: 'POST',
  });
}

export function updateSpeakerMapping(
  meetingId: string,
  speakerLabel: string,
  displayName: string,
  note?: string,
): Promise<SpeakerMapping> {
  return requestJson<SpeakerMapping>(`/meetings/${meetingId}/speakers/${encodeURIComponent(speakerLabel)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName, note: note || null }),
  });
}

export function submitFeedback(payload: FeedbackPayload): Promise<FeedbackCreated> {
  return requestJson<FeedbackCreated>('/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
