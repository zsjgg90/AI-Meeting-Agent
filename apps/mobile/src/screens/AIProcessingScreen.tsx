import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  analyzeMeeting,
  getMeeting,
  getMeetingSummary,
  getMeetingTranscript,
  Meeting,
  MeetingDetail,
  MeetingSummary,
  processMeeting,
  TranscriptionTask,
  updateMeeting,
  uploadAudio,
} from '../api';

type Props = {
  meeting: Pick<Meeting, 'id' | 'title' | 'status'>;
  recordingUri: string;
  endedAt: string;
  realtimeTranscriptReady?: boolean;
  onBackHome: () => void;
  onOpenDetail: (meetingId: string) => void;
};

type StepStatus = 'pending' | 'running' | 'completed' | 'failed';
type StageKey = 'upload' | 'audio' | 'transcript' | 'speaker' | 'summary';

type ProcessingStage = {
  key: StageKey;
  label: string;
  status: StepStatus;
};

type StructuredTaskError = {
  error_code?: string;
  error_stage?: string;
  error_message?: string;
};

const failedStatuses = new Set(['failed', 'transcription_failed', 'summary_failed']);

function statusRank(status: StepStatus): number {
  if (status === 'completed') return 1;
  if (status === 'running') return 0.5;
  return 0;
}

function isMeetingFailed(meeting: MeetingDetail | null): boolean {
  return Boolean(meeting && failedStatuses.has(meeting.status));
}

function hasSummaryContent(summary: MeetingSummary | null | undefined): boolean {
  return Boolean(summary?.meeting_summary?.trim() || summary?.overview?.trim() || (summary as any)?.summary?.trim());
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function latestTask(tasks: TranscriptionTask[] | undefined): TranscriptionTask | null {
  const sorted = [...(tasks || [])].sort((left, right) => {
    const leftTime = new Date(left.created_at).getTime();
    const rightTime = new Date(right.created_at).getTime();
    return rightTime - leftTime;
  });
  return sorted[0] || null;
}

function parseTaskError(task: TranscriptionTask | null): StructuredTaskError | null {
  if (!task?.error_message) return null;
  try {
    const parsed = JSON.parse(task.error_message);
    if (parsed && typeof parsed === 'object') return parsed;
  } catch {
    return { error_message: task.error_message };
  }
  return null;
}

function safeErrorMessage(error: StructuredTaskError | null, fallback = 'AI 处理失败，请稍后重试。'): string {
  const message = error?.error_message?.trim();
  if (!message) return fallback;
  if (message.includes('timeout') || message.includes('timed out')) return 'AI 处理超时，请稍后重新分析。';
  if (message.includes('Connection') || message.includes('connect')) return 'AI 服务暂时不可用，请稍后重新分析。';
  if (message.includes('Transcript') || message.includes('transcript')) return '转写结果不完整，请稍后重新处理。';
  if (message.length > 120) return `${message.slice(0, 120)}...`;
  return message;
}

function failureStage(meeting: MeetingDetail | null, taskError: StructuredTaskError | null): StageKey | null {
  const rawStage = taskError?.error_stage;
  if (rawStage === 'summary' || rawStage === 'rag_retrieval' || rawStage === 'model_inference' || rawStage === 'validation') {
    return 'summary';
  }
  if (rawStage === 'diarization') return 'speaker';
  if (rawStage === 'transcription') return 'transcript';
  if (rawStage === 'process') {
    return meeting?.transcript_segments.length ? 'summary' : 'transcript';
  }
  if (meeting?.status === 'summary_failed') return 'summary';
  if (meeting?.status === 'transcription_failed') return 'transcript';
  if (meeting?.status === 'failed') return meeting.audio_files.length ? 'transcript' : 'upload';
  return null;
}

function stageLabel(key: StageKey, status: StepStatus): string {
  const completedLabels: Record<StageKey, string> = {
    upload: '音频上传完成',
    audio: '音频处理完成',
    transcript: '转写完成',
    speaker: '说话人识别完成',
    summary: '会议纪要生成完成',
  };
  const runningLabels: Record<StageKey, string> = {
    upload: '正在上传音频',
    audio: '正在处理音频',
    transcript: '正在转写',
    speaker: '正在识别说话人',
    summary: '正在生成会议纪要',
  };
  const pendingLabels: Record<StageKey, string> = {
    upload: '等待音频上传',
    audio: '等待音频处理',
    transcript: '等待转写',
    speaker: '等待识别说话人',
    summary: '等待生成会议纪要',
  };
  const failedLabels: Record<StageKey, string> = {
    upload: '音频上传失败',
    audio: '音频处理失败',
    transcript: '转写失败',
    speaker: '说话人识别失败',
    summary: '会议纪要生成失败',
  };
  if (status === 'completed') return completedLabels[key];
  if (status === 'running') return runningLabels[key];
  if (status === 'failed') return failedLabels[key];
  return pendingLabels[key];
}

export function AIProcessingScreen({
  meeting,
  recordingUri,
  endedAt,
  realtimeTranscriptReady = false,
  onBackHome,
  onOpenDetail,
}: Props) {
  const [uploadStatus, setUploadStatus] = useState<StepStatus>('pending');
  const [processStatus, setProcessStatus] = useState<StepStatus>('pending');
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetail | null>(null);
  const [summaryResult, setSummaryResult] = useState<MeetingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [showErrorDetail, setShowErrorDetail] = useState(false);
  const startedRef = useRef(false);

  const refreshMeeting = useCallback(async () => {
    const nextMeeting = await getMeeting(meeting.id);
    setMeetingDetail(nextMeeting);
    return nextMeeting;
  }, [meeting.id]);

  const latest = useMemo(() => latestTask(meetingDetail?.tasks), [meetingDetail?.tasks]);
  const taskError = useMemo(() => parseTaskError(latest), [latest]);

  const waitForTranscript = useCallback(
    async (cancelled: () => boolean): Promise<boolean> => {
      const startedAt = Date.now();
      while (!cancelled() && Date.now() - startedAt < 120000) {
        await wait(3000);
        const nextTranscript = await getMeetingTranscript(meeting.id);
        const nextMeeting = await refreshMeeting();
        if (nextTranscript.segments.length > 0 || nextMeeting.transcript_segments.length > 0) return true;
        if (isMeetingFailed(nextMeeting)) return false;
      }
      return false;
    },
    [meeting.id, refreshMeeting],
  );

  const waitForSummary = useCallback(
    async (cancelled: () => boolean): Promise<void> => {
      const startedAt = Date.now();
      while (!cancelled() && Date.now() - startedAt < 600000) {
        await wait(3000);
        const nextSummary = await getMeetingSummary(meeting.id);
        setSummaryResult(nextSummary);
        const nextMeeting = await refreshMeeting();
        if (hasSummaryContent(nextSummary) || hasSummaryContent(nextMeeting.summary) || nextMeeting.status === 'completed') {
          setProcessStatus('completed');
          return;
        }
        if (isMeetingFailed(nextMeeting)) {
          setProcessStatus('failed');
          setError(safeErrorMessage(parseTaskError(latestTask(nextMeeting.tasks)), '会议纪要生成失败，请重新分析。'));
          return;
        }
      }
      throw new Error('会议纪要生成超时，请稍后重新分析。');
    },
    [meeting.id, refreshMeeting],
  );

  const startAnalysisOnly = useCallback(async () => {
    setRetrying(true);
    setError(null);
    setProcessStatus('running');
    try {
      await analyzeMeeting(meeting.id);
      await waitForSummary(() => false);
    } catch (nextError) {
      const nextMeeting = await refreshMeeting().catch(() => null);
      const structured = parseTaskError(latestTask(nextMeeting?.tasks));
      setProcessStatus('failed');
      setError(safeErrorMessage(structured, nextError instanceof Error ? nextError.message : '会议纪要生成失败，请重新分析。'));
    } finally {
      setRetrying(false);
    }
  }, [meeting.id, refreshMeeting, waitForSummary]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;

    async function run() {
      try {
        const currentMeeting = await getMeeting(meeting.id);
        if (cancelled) return;
        setMeetingDetail(currentMeeting);
        if (hasSummaryContent(currentMeeting.summary)) {
          setSummaryResult(currentMeeting.summary);
          setUploadStatus('completed');
          setProcessStatus('completed');
          return;
        }

        setUploadStatus(currentMeeting.audio_files.length ? 'completed' : 'running');
        try {
          await updateMeeting(meeting.id, { end_at: endedAt });
        } catch {
          // Ending time is useful metadata, but it must not block audio upload and AI processing.
        }
        if (!realtimeTranscriptReady && currentMeeting.audio_files.length === 0) {
          await uploadAudio(meeting.id, recordingUri, endedAt);
        }
        if (cancelled) return;
        setUploadStatus('completed');

        setProcessStatus('running');
        const initialTranscript = await getMeetingTranscript(meeting.id);
        let hasTranscriptSegments = initialTranscript.segments.length > 0 || currentMeeting.transcript_segments.length > 0;

        if (!hasTranscriptSegments) {
          await processMeeting(meeting.id);
          hasTranscriptSegments = await waitForTranscript(() => cancelled);
        }

        if (cancelled) return;
        if (!hasTranscriptSegments) {
          throw new Error('转写未完成，请稍后重试。');
        }

        await refreshMeeting();
        await analyzeMeeting(meeting.id);
        await waitForSummary(() => cancelled);
      } catch (nextError) {
        if (cancelled) return;
        const nextMeeting = await refreshMeeting().catch(() => null);
        const structured = parseTaskError(latestTask(nextMeeting?.tasks));
        setUploadStatus((current) => (current === 'completed' ? current : 'failed'));
        setProcessStatus('failed');
        setError(safeErrorMessage(structured, nextError instanceof Error ? nextError.message : 'AI 处理启动失败。'));
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [endedAt, meeting.id, realtimeTranscriptReady, recordingUri, refreshMeeting, waitForSummary, waitForTranscript]);

  useEffect(() => {
    if (!meetingDetail) return;
    if (isMeetingFailed(meetingDetail)) {
      setProcessStatus('failed');
      setError(safeErrorMessage(taskError, 'AI 处理失败，请稍后在历史会议中重新分析。'));
    }
  }, [meetingDetail, taskError]);

  const stages = useMemo<ProcessingStage[]>(() => {
    const hasAudio = uploadStatus === 'completed' || Boolean(meetingDetail?.audio_files.length);
    const hasTranscript = Boolean(meetingDetail?.transcript_segments.length);
    const hasSpeaker = Boolean(
      meetingDetail?.transcript_segments.some((segment) => segment.speaker_label || segment.speaker_name),
    );
    const hasSummary =
      hasSummaryContent(summaryResult) || hasSummaryContent(meetingDetail?.summary) || meetingDetail?.status === 'completed';
    const failedStage = processStatus === 'failed' || isMeetingFailed(meetingDetail) ? failureStage(meetingDetail, taskError) : null;

    const statuses: Record<StageKey, StepStatus> = {
      upload: hasAudio ? 'completed' : uploadStatus,
      audio: hasTranscript ? 'completed' : hasAudio ? 'running' : 'pending',
      transcript: hasTranscript ? 'completed' : hasAudio ? 'running' : 'pending',
      speaker: hasSpeaker ? 'completed' : hasTranscript ? 'running' : 'pending',
      summary: hasSummary ? 'completed' : hasTranscript ? processStatus : 'pending',
    };
    if (failedStage) {
      const order: StageKey[] = ['upload', 'audio', 'transcript', 'speaker', 'summary'];
      const failedIndex = order.indexOf(failedStage);
      for (let index = 0; index < order.length; index += 1) {
        const key = order[index];
        if (index < failedIndex && statuses[key] !== 'completed') statuses[key] = 'completed';
        if (index === failedIndex) statuses[key] = 'failed';
        if (index > failedIndex) statuses[key] = 'pending';
      }
    }

    return (['upload', 'audio', 'transcript', 'speaker', 'summary'] as StageKey[]).map((key) => ({
      key,
      label: stageLabel(key, statuses[key]),
      status: statuses[key],
    }));
  }, [meetingDetail, processStatus, summaryResult, taskError, uploadStatus]);

  const progress = Math.round((stages.reduce((sum, stage) => sum + statusRank(stage.status), 0) / stages.length) * 100);
  const finished = stages.every((stage) => stage.status === 'completed');
  const failed = stages.some((stage) => stage.status === 'failed');
  const displayedTitle = meetingDetail?.title || meeting.title;
  const errorDetail = taskError
    ? `错误阶段：${taskError.error_stage || '未知'}\n错误代码：${taskError.error_code || 'unknown'}\n错误说明：${safeErrorMessage(taskError)}`
    : error || '暂无更多错误详情。';

  return (
    <View style={styles.container}>
      <View style={styles.titleBlock}>
        <Text numberOfLines={1} style={styles.meetingTitle}>
          {displayedTitle}
        </Text>
        <Text style={styles.people}>{failed ? 'AI 分析失败' : finished ? 'AI 分析完成' : 'AI 分析中'}</Text>
      </View>

      <View style={[styles.progressRing, failed ? styles.progressRingFailed : null]}>
        <Text style={[styles.progressText, failed ? styles.progressTextFailed : null]}>{progress}%</Text>
      </View>

      <Text style={styles.processingText}>{failed ? '处理遇到问题' : finished ? 'AI 分析完成' : 'AI 分析中...'}</Text>

      <View style={styles.statusCard}>
        <Text style={styles.statusCardTitle}>处理进度</Text>
        {stages.map((stage) => (
          <View key={stage.key} style={styles.stageRow}>
            <View
              style={[
                styles.stageIcon,
                stage.status === 'completed' ? styles.stageIconDone : null,
                stage.status === 'failed' ? styles.stageIconFailed : null,
                stage.status === 'pending' ? styles.stageIconPending : null,
              ]}
            >
              {stage.status === 'running' ? (
                <ActivityIndicator color="#6657ff" size="small" />
              ) : (
                <Text style={[styles.stageIconText, stage.status === 'failed' ? styles.stageIconTextFailed : null]}>
                  {stage.status === 'failed' ? '!' : stage.status === 'completed' ? '✓' : ''}
                </Text>
              )}
            </View>
            <Text style={styles.stageLabel}>{stage.label}</Text>
          </View>
        ))}
      </View>

      {error ? (
        <View style={styles.errorCard}>
          <Text style={styles.errorTitle}>处理失败</Text>
          <Text style={styles.error}>{error}</Text>
          <View style={styles.errorActions}>
            <Pressable disabled={retrying} onPress={startAnalysisOnly} style={styles.retryButton}>
              {retrying ? <ActivityIndicator color="#ffffff" size="small" /> : <Text style={styles.retryText}>重新分析</Text>}
            </Pressable>
            <Pressable onPress={() => setShowErrorDetail(true)} style={styles.detailButton}>
              <Text style={styles.detailText}>查看错误详情</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={styles.tipCard}>
        <Text style={styles.tipText}>你可以返回首页，稍后在历史会议中查看结果</Text>
      </View>

      <View style={styles.actions}>
        <Pressable onPress={onBackHome} style={styles.secondaryButton}>
          <Text style={styles.secondaryText}>返回首页</Text>
        </Pressable>
        <Pressable onPress={() => onOpenDetail(meeting.id)} style={styles.primaryButton}>
          <Text style={styles.primaryText}>{finished ? '查看纪要' : '查看历史会议'}</Text>
        </Pressable>
      </View>

      <Modal transparent visible={showErrorDetail} animationType="fade" onRequestClose={() => setShowErrorDetail(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>错误详情</Text>
            <Text style={styles.modalText}>{errorDetail}</Text>
            <Pressable onPress={() => setShowErrorDetail(false)} style={styles.modalButton}>
              <Text style={styles.modalButtonText}>知道了</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 28,
    paddingTop: 20,
  },
  titleBlock: {
    alignItems: 'center',
    gap: 4,
  },
  meetingTitle: {
    color: '#111827',
    fontSize: 17,
    fontWeight: '900',
  },
  people: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
  },
  progressRing: {
    alignItems: 'center',
    alignSelf: 'center',
    borderColor: '#6657ff',
    backgroundColor: '#ffffff',
    borderRadius: 64,
    borderWidth: 9,
    height: 128,
    justifyContent: 'center',
    marginTop: 48,
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.14,
    shadowRadius: 24,
    width: 128,
    elevation: 5,
  },
  progressRingFailed: {
    borderColor: '#ef4444',
  },
  progressText: {
    color: '#6657ff',
    fontSize: 28,
    fontWeight: '900',
  },
  progressTextFailed: {
    color: '#ef4444',
  },
  processingText: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
    marginTop: 22,
    textAlign: 'center',
  },
  statusCard: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 22,
    borderWidth: 1,
    gap: 14,
    marginTop: 22,
    padding: 18,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  statusCardTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
    marginBottom: 2,
  },
  stageRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
  },
  stageIcon: {
    alignItems: 'center',
    borderColor: '#d8d7ff',
    borderRadius: 12,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  stageIconDone: {
    backgroundColor: '#dcfce7',
    borderColor: '#dcfce7',
  },
  stageIconFailed: {
    backgroundColor: '#fee2e2',
    borderColor: '#fee2e2',
  },
  stageIconPending: {
    backgroundColor: '#f3f4f6',
    borderColor: '#e5e7eb',
  },
  stageIconText: {
    color: '#16a34a',
    fontSize: 12,
    fontWeight: '900',
  },
  stageIconTextFailed: {
    color: '#ef4444',
  },
  stageLabel: {
    color: '#374151',
    fontSize: 14,
    fontWeight: '800',
  },
  errorCard: {
    backgroundColor: '#fff1f2',
    borderColor: '#fecdd3',
    borderRadius: 16,
    borderWidth: 1,
    gap: 9,
    marginTop: 14,
    padding: 13,
  },
  errorTitle: {
    color: '#ef4444',
    fontSize: 13,
    fontWeight: '900',
  },
  error: {
    color: '#ef4444',
    fontSize: 12,
    lineHeight: 18,
  },
  errorActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 2,
  },
  retryButton: {
    alignItems: 'center',
    backgroundColor: '#ef4444',
    borderRadius: 12,
    flex: 1,
    minHeight: 38,
    justifyContent: 'center',
  },
  retryText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '900',
  },
  detailButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#fecdd3',
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    minHeight: 38,
    justifyContent: 'center',
  },
  detailText: {
    color: '#ef4444',
    fontSize: 12,
    fontWeight: '900',
  },
  tipCard: {
    alignItems: 'center',
    backgroundColor: '#f5f6ff',
    borderRadius: 18,
    gap: 6,
    marginTop: 30,
    padding: 18,
  },
  tipText: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 20,
    textAlign: 'center',
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 'auto',
    paddingBottom: 28,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 16,
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
  },
  primaryText: {
    color: '#ffffff',
    fontWeight: '900',
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
  },
  secondaryText: {
    color: '#6b7280',
    fontWeight: '900',
  },
  modalBackdrop: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.42)',
    flex: 1,
    justifyContent: 'center',
    padding: 24,
  },
  modalCard: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    gap: 12,
    padding: 18,
    width: '100%',
  },
  modalTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  modalText: {
    color: '#4b5563',
    fontSize: 13,
    lineHeight: 20,
  },
  modalButton: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 12,
    minHeight: 42,
    justifyContent: 'center',
  },
  modalButtonText: {
    color: '#ffffff',
    fontWeight: '900',
  },
});
