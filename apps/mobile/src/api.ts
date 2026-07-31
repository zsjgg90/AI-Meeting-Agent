import { apiBaseUrl, apiDebugInfo } from './config';

export type Meeting = {
  id: string;
  title: string;
  title_source?: 'fallback' | 'ai_generated' | 'user_edited' | string;
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
  description?: string | null;
  due_date: string | null;
  deadline: string | null;
  priority: string | null;
  reminder_offset_minutes?: number | null;
  reminder_channel?: string | null;
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
  content?: string | null;
  details?: string | null;
  assignee?: string | null;
  responsible_person?: string | null;
  attachments?: Array<{
    id?: string;
    filename?: string | null;
    name?: string | null;
    content_type?: string | null;
    file_type?: string | null;
    file_size_bytes?: number | null;
    size?: number | null;
    task_id?: string;
    url?: string | null;
    download_url?: string | null;
    uploaded_at?: string;
  }>;
};

export type TaskListResponse = {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type KnowledgeOverview = {
  meeting_count: number;
  decision_count: number;
  unresolved_issue_count: number;
  risk_count: number;
  all_count: number;
  sync_status: Record<string, number>;
};

export type KnowledgeSync = {
  meeting_id: string;
  status: string;
  source_version: string;
  item_count: number;
  sync_error: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
};

export type KnowledgeContentType =
  | 'all'
  | 'meeting_summary'
  | 'meeting_agenda'
  | 'key_decision'
  | 'action_item'
  | 'unresolved_issue'
  | 'risk'
  | 'transcript';

export type KnowledgeItem = {
  id: string;
  content_type: Exclude<KnowledgeContentType, 'all'> | string;
  title: string;
  content: string;
  meeting_id: string;
  meeting_title: string;
  meeting_date: string | null;
  evidence_text: string | null;
  source_segment_id: string | null;
  speaker_label: string | null;
  start_time: number | null;
  end_time: number | null;
  highlight: string | null;
};

export type KnowledgeMeetingItem = {
  meeting_id: string;
  title: string;
  meeting_type: string | null;
  meeting_time: string | null;
  duration: number | null;
  summary_status: string;
  conclusion_count: number;
  action_count: number;
  unresolved_issue_count: number;
  risk_count: number;
};

export type KnowledgeListResponse<T = KnowledgeItem> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type KnowledgeQueryOptions = {
  query?: string;
  content_type?: KnowledgeContentType | string;
  meeting_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
};

export type SpeakerMapping = {
  id: string;
  speaker_label: string;
  display_name: string;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type TranscriptionTask = {
  id: string;
  meeting_id: string;
  status: string;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
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
  tasks: TranscriptionTask[];
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
  title_source?: 'fallback' | 'ai_generated' | 'user_edited' | string;
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

export type AgentProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'conflict' | 'duplicate' | 'ready' | string;

export type AgentActionProposal = {
  id: string;
  action_type: string;
  target_object_type: string;
  target_object_id: string | null;
  expected_object_version: string | null;
  title: string;
  description: string;
  proposed_changes: Record<string, any>;
  evidence: Array<Record<string, any>>;
  confidence: number | null;
  risk_level: string;
  requires_confirmation: boolean;
  status: AgentProposalStatus;
  reason: string;
  metadata: Record<string, any>;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentConfirmation = {
  id: string;
  proposal_id: string;
  decision: string;
  reviewer: string;
  reviewed_at: string;
  comment: string;
  expected_object_version: string | null;
  permissions: string[];
  metadata: Record<string, any>;
};

export type ControlledWriteCommand = {
  id: string;
  proposal_id: string;
  target_object_type: string;
  target_object_id: string;
  operation: string;
  expected_version: string | null;
  changes: Record<string, any>;
  idempotency_key: string;
  confirmation_id: string;
  audit_context: Record<string, any>;
  rollback_plan: Record<string, any>;
  status: string;
  created_at: string;
};

export type AgentAuditRecord = {
  id: string;
  proposal_id: string;
  confirmation_id: string | null;
  command_id: string | null;
  target_object_type: string;
  target_object_id: string;
  operation: string;
  reviewer: string;
  decision: string;
  result: string;
  reasons: string[];
  authoritative_source: string;
  authoritative_version: string | null;
  audit_context: Record<string, any>;
  created_at: string;
};

export type AgentProposalDecision = {
  proposal: AgentActionProposal;
  confirmation: AgentConfirmation;
  command: ControlledWriteCommand | null;
  audit: AgentAuditRecord | null;
  status: string;
  rejection_reasons: string[];
};

export type AgentCommandDryRunResult = {
  command: ControlledWriteCommand;
  audit: AgentAuditRecord;
  status: string;
  rejection_reasons: string[];
  authoritative_state: Record<string, any> | null;
  expected_changes: Record<string, any>;
  rollback_preview: Record<string, any>;
  writes_performed: boolean;
};

export type AgentCommandExecutionResult = {
  command: ControlledWriteCommand;
  audit: AgentAuditRecord;
  status: string;
  rejection_reasons: string[];
  before_state: Record<string, any> | null;
  after_state: Record<string, any> | null;
  writes_performed: boolean;
};

export type AgentReviewChange = {
  field: string;
  label: string;
  before: string | null;
  after: string | null;
};

export type AgentReviewEvidence = {
  source_text: string;
  speaker: string | null;
  source_meeting_id: string | null;
  source_meeting_title: string | null;
  source_meeting_time: string | null;
  source_segment_id: string | null;
};

export type AgentReviewProposalCard = {
  id: string;
  action_type: string;
  action_label: string;
  target_object_type: string;
  target_object_id: string | null;
  target_title: string;
  source_meeting_title: string | null;
  source_meeting_time: string | null;
  risk_level: string;
  risk_label: string;
  status: string;
  status_label: string;
  changes: AgentReviewChange[];
  evidence: AgentReviewEvidence | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};

export type AgentReviewRecord = {
  id: string;
  proposal_id: string;
  command_id: string | null;
  action_type: string;
  action_label: string;
  target_object_type: string;
  target_object_id: string | null;
  target_title: string;
  change_summary: string;
  handled_at: string;
  status: string;
  status_label: string;
  reason_preview: string | null;
};

export type AgentReviewOverview = {
  pending_count: number;
  pending_proposals: AgentReviewProposalCard[];
  recent_records: AgentReviewRecord[];
};

export type AgentReviewRecordsResponse = {
  items: AgentReviewRecord[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
};

export type AgentReviewAuditTimelineItem = {
  id: string;
  result: string;
  result_label: string;
  decision: string;
  reviewer: string;
  operation: string;
  reasons: string[];
  writes_performed: boolean;
  created_at: string;
};

export type AgentReviewCommand = {
  id: string;
  proposal_id: string;
  target_object_type: string;
  target_object_id: string;
  operation: string;
  expected_version: string | null;
  changes: Record<string, any>;
  status: string;
  created_at: string;
};

export type AgentReviewRecordDetail = {
  id: string;
  proposal: AgentReviewProposalCard;
  confirmation: AgentConfirmation | null;
  command: AgentReviewCommand | null;
  before_after: AgentReviewChange[];
  evidence: AgentReviewEvidence | null;
  reviewer: string | null;
  executor: string | null;
  audit_timeline: AgentReviewAuditTimelineItem[];
  reject_reason: string | null;
  rollback_reason: string | null;
  writes_performed: boolean;
  object_version_before: string | null;
  object_version_after: string | null;
};

export type AgentSession = {
  token: string;
  token_type: string;
  expires_at: string;
  user_id: string;
  display_name: string;
  tenant_id: string;
  project_scope: string[];
  permissions: string[];
};

export type AgentSessionInfo = Omit<AgentSession, 'token' | 'token_type' | 'expires_at'> & {
  authentication_source: string;
};

export class ApiRequestError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string, message: string) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.body = body;
  }
}

export class AgentStorageError extends Error {
  code = 'storage_unavailable';

  constructor(message = '本地登录存储不可用，请重启应用') {
    super(message);
    this.name = 'AgentStorageError';
  }
}

const jsonHeaders = { 'Content-Type': 'application/json' };
const DEFAULT_REQUEST_TIMEOUT_MS = 15000;
const AGENT_SESSION_STORAGE_KEY = 'meetmind.agent.session.v1';
let agentSession: AgentSession | null = null;
let agentAuthToken: string | null = null;

type AsyncStorageLike = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
  removeItem: (key: string) => Promise<void>;
};

async function getAsyncStorage(): Promise<AsyncStorageLike> {
  try {
    const imported = await import('@react-native-async-storage/async-storage');
    const storage = imported.default;
    if (!storage?.getItem || !storage?.setItem || !storage?.removeItem) {
      throw new AgentStorageError();
    }
    return storage;
  } catch (error) {
    if (error instanceof AgentStorageError) throw error;
    throw new AgentStorageError();
  }
}

export function isApiRequestError(error: unknown, status?: number): error is ApiRequestError {
  return error instanceof ApiRequestError && (status === undefined || error.status === status);
}

export function isAgentStorageError(error: unknown): error is AgentStorageError {
  return error instanceof AgentStorageError || (typeof error === 'object' && error !== null && (error as { code?: string }).code === 'storage_unavailable');
}

export async function loadStoredAgentSession(): Promise<AgentSession | null> {
  try {
    const storage = await getAsyncStorage();
    const raw = await storage.getItem(AGENT_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AgentSession;
    if (!parsed.token || !parsed.expires_at || new Date(parsed.expires_at).getTime() <= Date.now()) {
      await clearAgentSession();
      return null;
    }
    agentSession = parsed;
    agentAuthToken = parsed.token;
    return parsed;
  } catch (error) {
    if (isAgentStorageError(error)) throw error;
    await clearAgentSession({ suppressStorageError: true });
    return null;
  }
}

export function useAgentSessionInMemory(session: AgentSession): void {
  agentSession = session;
  agentAuthToken = session.token;
}

export function clearAgentSessionInMemory(): void {
  agentSession = null;
  agentAuthToken = null;
}

export async function saveAgentSession(session: AgentSession): Promise<void> {
  useAgentSessionInMemory(session);
  try {
    const storage = await getAsyncStorage();
    await storage.setItem(AGENT_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch (error) {
    if (isAgentStorageError(error)) throw error;
    throw new AgentStorageError();
  }
}

export async function clearAgentSession(options?: { suppressStorageError?: boolean }): Promise<void> {
  clearAgentSessionInMemory();
  try {
    const storage = await getAsyncStorage();
    await storage.removeItem(AGENT_SESSION_STORAGE_KEY);
  } catch {
    if (!options?.suppressStorageError) {
      throw new AgentStorageError();
    }
  }
}

export function getAgentAuthToken(): string | null {
  return agentAuthToken;
}

export function getCachedAgentSession(): AgentSession | null {
  return agentSession;
}

async function fetchWithTimeout(url: string, options?: RequestInit): Promise<Response> {
  const controller = typeof AbortController !== 'undefined' && !options?.signal ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS) : null;
  try {
    return await fetch(url, {
      ...options,
      signal: options?.signal || controller?.signal,
    });
  } catch (error) {
    throw buildNetworkError(error, url);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = typeof AbortController !== 'undefined' && !options?.signal ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT_MS) : null;
  const headers = new Headers(options?.headers || undefined);
  if (path.startsWith('/agent/') && agentAuthToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${agentAuthToken}`);
  }
  const url = `${apiBaseUrl.replace(/\/+$/, '')}${path}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: options?.signal || controller?.signal,
    });
    if (!response.ok) {
      const body = await response.text();
      if (path.startsWith('/agent/') && response.status === 401) {
        await clearAgentSession({ suppressStorageError: true });
      }
      throw new ApiRequestError(response.status, body, friendlyApiError(response.status, body));
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }
    throw buildNetworkError(error, url);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function buildNetworkError(error: unknown, url: string): Error {
  const isTimeout = error instanceof Error && error.name === 'AbortError';
  const original = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  const message = [
    isTimeout ? '网络请求超时，请稍后重试' : 'Network request failed',
    `url=${url}`,
    `apiBaseUrl=${apiDebugInfo.apiBaseUrl}`,
    `devHostUri=${apiDebugInfo.devHostUri || 'null'}`,
    `devScriptUrl=${apiDebugInfo.devScriptUrl || 'null'}`,
    `envApiBaseUrl=${apiDebugInfo.envApiBaseUrl || 'null'}`,
    `error=${original}`,
  ].join('\n');
  return new Error(message);
}

function friendlyApiError(status: number, body: string): string {
  const text = body || '';
  if (status === 401) return '登录已失效，请重新登录后再试';
  if (status === 403) return '你没有权限处理这条建议';
  if (status === 404) return '记录不存在或已被删除';
  if (status === 409) {
    if (text.includes('version_conflict')) return '数据已更新，请刷新后再处理';
    if (text.includes('confirmation_expired')) return '这条建议已过期';
    if (text.includes('already')) return '这条建议已被其他人处理';
    return '提交冲突，请刷新后再试';
  }
  if (status >= 500) return '服务暂时不可用，请稍后重试';
  return '网络请求失败，请稍后重试';
}

export function listMeetings(options?: { limit?: number; offset?: number }): Promise<Meeting[]> {
  const params = new URLSearchParams();
  params.set('limit', String(options?.limit ?? 50));
  params.set('offset', String(options?.offset ?? 0));
  return requestJson<Meeting[]>(`/meetings?${params.toString()}`);
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

export function updateTaskStatus(taskId: string, status: 'open' | 'completed'): Promise<TaskListItem> {
  return requestJson<TaskListItem>(`/tasks/${encodeURIComponent(taskId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

export function updateTask(
  taskId: string,
  payload: {
    task?: string | null;
    description?: string | null;
    owner?: string | null;
    due_date?: string | null;
    priority?: 'high' | 'medium' | 'low' | null;
    reminder_offset_minutes?: 60 | 180 | 300 | null;
    reminder_channel?: 'sms' | null;
  },
): Promise<TaskListItem> {
  return requestJson<TaskListItem>(`/tasks/${encodeURIComponent(taskId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function uploadTaskAttachment(
  taskId: string,
  file: { uri: string; name: string; type?: string | null },
): Promise<NonNullable<TaskListItem['attachments']>[number]> {
  const form = new FormData();
  form.append('file', {
    uri: file.uri,
    name: file.name,
    type: file.type || 'application/octet-stream',
  } as any);

  const response = await fetchWithTimeout(`${apiBaseUrl.replace(/\/+$/, '')}/tasks/${encodeURIComponent(taskId)}/attachments`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(friendlyApiError(response.status, body));
  }
  return response.json() as Promise<NonNullable<TaskListItem['attachments']>[number]>;
}

export function taskAttachmentUrl(taskId: string, attachmentId: string): string {
  return `${apiBaseUrl.replace(/\/+$/, '')}/tasks/${encodeURIComponent(taskId)}/attachments/${encodeURIComponent(attachmentId)}`;
}

function knowledgeParams(options?: KnowledgeQueryOptions): string {
  const params = new URLSearchParams();
  params.set('limit', String(options?.limit ?? 20));
  params.set('offset', String(options?.offset ?? 0));
  if (options?.query?.trim()) params.set('query', options.query.trim());
  if (options?.content_type && options.content_type !== 'all') params.set('content_type', options.content_type);
  if (options?.meeting_type && options.meeting_type !== 'all') params.set('meeting_type', options.meeting_type);
  if (options?.date_from) params.set('date_from', options.date_from);
  if (options?.date_to) params.set('date_to', options.date_to);
  return params.toString();
}

export function getKnowledgeOverview(): Promise<KnowledgeOverview> {
  return requestJson<KnowledgeOverview>('/knowledge/overview');
}

export function listKnowledgeMeetings(options?: KnowledgeQueryOptions): Promise<KnowledgeListResponse<KnowledgeMeetingItem>> {
  return requestJson<KnowledgeListResponse<KnowledgeMeetingItem>>(`/knowledge/meetings?${knowledgeParams(options)}`);
}

export function listKnowledgeDecisions(options?: KnowledgeQueryOptions): Promise<KnowledgeListResponse> {
  return requestJson<KnowledgeListResponse>(`/knowledge/decisions?${knowledgeParams(options)}`);
}

export function listKnowledgeIssues(options?: KnowledgeQueryOptions): Promise<KnowledgeListResponse> {
  return requestJson<KnowledgeListResponse>(`/knowledge/issues?${knowledgeParams(options)}`);
}

export function listKnowledgeRisks(options?: KnowledgeQueryOptions): Promise<KnowledgeListResponse> {
  return requestJson<KnowledgeListResponse>(`/knowledge/risks?${knowledgeParams(options)}`);
}

export function searchKnowledge(options?: KnowledgeQueryOptions): Promise<KnowledgeListResponse> {
  return requestJson<KnowledgeListResponse>(`/knowledge/search?${knowledgeParams(options)}`);
}

export function createMeeting(
  title: string,
  options?: { start_at?: string; end_at?: string; location?: string; title_source?: 'fallback' | 'ai_generated' | 'user_edited' },
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

export function reindexMeetingKnowledge(meetingId: string): Promise<KnowledgeSync> {
  return requestJson<KnowledgeSync>(`/meetings/${meetingId}/knowledge/reindex`, {
    method: 'POST',
  });
}

export async function deleteMeeting(meetingId: string): Promise<void> {
  const response = await fetchWithTimeout(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(friendlyApiError(response.status, body));
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
  options: { title?: string; start_at?: string; end_at?: string; location?: string | null },
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

function friendlyUploadError(status: number, body: string): string {
  if (status === 400) {
    if (body.includes('Unsupported audio')) return '录音文件格式暂不支持，请重新录制后上传';
    if (body.includes('empty')) return '录音文件为空，请重新录制';
    return '录音文件无法上传，请重新录制后再试';
  }
  if (status === 404) return '会议不存在，请返回重新创建会议';
  if (status >= 500) return '录音上传服务暂时不可用，请稍后重试';
  return '录音上传失败，请稍后重试';
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

  const response = await fetchWithTimeout(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/audio`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(friendlyUploadError(response.status, body));
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

  const response = await fetchWithTimeout(`${apiBaseUrl.replace(/\/+$/, '')}/meetings/${meetingId}/audio-chunks`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(friendlyUploadError(response.status, body));
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

export async function loginAgentSession(displayName = '本地验收用户'): Promise<AgentSession> {
  const session = await requestJson<AgentSession>('/agent/auth/login', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ display_name: displayName }),
  });
  await saveAgentSession(session);
  return session;
}

export function getAgentSessionInfo(): Promise<AgentSessionInfo> {
  return requestJson<AgentSessionInfo>('/agent/auth/session');
}

export async function logoutAgentSession(): Promise<void> {
  try {
    await requestJson<{ status: string; revoked: boolean }>('/agent/auth/logout', {
      method: 'POST',
    });
  } finally {
    await clearAgentSession();
  }
}

export function listAgentProposals(status: AgentProposalStatus = 'pending'): Promise<AgentActionProposal[]> {
  return requestJson<AgentActionProposal[]>(`/agent/action-proposals?status=${encodeURIComponent(status)}`);
}

export function getAgentProposal(proposalId: string): Promise<AgentActionProposal> {
  return requestJson<AgentActionProposal>(`/agent/action-proposals/${encodeURIComponent(proposalId)}`);
}

export function approveAgentProposal(proposalId: string, comment = ''): Promise<AgentProposalDecision> {
  return requestJson<AgentProposalDecision>(`/agent/action-proposals/${encodeURIComponent(proposalId)}/approve`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ comment }),
  });
}

export function rejectAgentProposal(proposalId: string, comment = ''): Promise<AgentProposalDecision> {
  return requestJson<AgentProposalDecision>(`/agent/action-proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ comment }),
  });
}

export function listAgentCommands(status = 'ready'): Promise<ControlledWriteCommand[]> {
  return requestJson<ControlledWriteCommand[]>(`/agent/commands?status=${encodeURIComponent(status)}`);
}

export function dryRunAgentCommand(commandId: string): Promise<AgentCommandDryRunResult> {
  return requestJson<AgentCommandDryRunResult>(`/agent/commands/${encodeURIComponent(commandId)}/dry-run`, {
    method: 'POST',
  });
}

export function executeAgentCommand(commandId: string, comment = ''): Promise<AgentCommandExecutionResult> {
  return requestJson<AgentCommandExecutionResult>(`/agent/commands/${encodeURIComponent(commandId)}/execute`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ comment }),
  });
}

export function rollbackExecuteAgentCommand(commandId: string, comment = ''): Promise<AgentCommandExecutionResult> {
  return requestJson<AgentCommandExecutionResult>(`/agent/commands/${encodeURIComponent(commandId)}/rollback/execute`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ comment }),
  });
}

export function listAgentCommandAudits(commandId: string): Promise<AgentAuditRecord[]> {
  return requestJson<AgentAuditRecord[]>(`/agent/commands/${encodeURIComponent(commandId)}/audits`);
}

export function getAgentReviewOverview(): Promise<AgentReviewOverview> {
  return requestJson<AgentReviewOverview>('/agent/review/overview');
}

export function listAgentReviewRecords(options?: {
  status?: string;
  sort?: 'latest' | 'oldest';
  page?: number;
  page_size?: number;
}): Promise<AgentReviewRecordsResponse> {
  const params = new URLSearchParams();
  params.set('status', options?.status || 'all');
  params.set('sort', options?.sort || 'latest');
  params.set('page', String(options?.page || 1));
  params.set('page_size', String(options?.page_size || 20));
  return requestJson<AgentReviewRecordsResponse>(`/agent/review/records?${params.toString()}`);
}

export function getAgentReviewRecord(recordId: string): Promise<AgentReviewRecordDetail> {
  return requestJson<AgentReviewRecordDetail>(`/agent/review/records/${encodeURIComponent(recordId)}`);
}
