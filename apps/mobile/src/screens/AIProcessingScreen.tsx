import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  analyzeMeeting,
  getMeeting,
  getMeetingSummary,
  getMeetingTranscript,
  Meeting,
  MeetingDetail,
  MeetingSummary,
  processMeeting,
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

type StepStatus = 'pending' | 'running' | 'done' | 'failed';

type ProcessingStage = {
  key: string;
  label: string;
  status: StepStatus;
};

function statusRank(status: StepStatus): number {
  if (status === 'done') return 1;
  if (status === 'running') return 0.5;
  return 0;
}

function isMeetingFailed(meeting: MeetingDetail | null): boolean {
  return meeting?.status === 'failed' || meeting?.status === 'transcription_failed' || meeting?.status === 'summary_failed';
}

function hasSummaryContent(summary: MeetingSummary | null | undefined): boolean {
  return Boolean(summary?.meeting_summary?.trim() || summary?.overview?.trim() || (summary as any)?.summary?.trim());
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
  const startedRef = useRef(false);

  const refreshMeeting = useCallback(async () => {
    const nextMeeting = await getMeeting(meeting.id);
    setMeetingDetail(nextMeeting);
  }, [meeting.id]);

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
          setUploadStatus('done');
          setProcessStatus('done');
          return;
        }

        setUploadStatus('running');
        try {
          await updateMeeting(meeting.id, { end_at: endedAt });
        } catch {
          // Ending time is useful metadata, but it must not block audio upload and AI processing.
        }
        if (!realtimeTranscriptReady && currentMeeting.audio_files.length === 0) {
          await uploadAudio(meeting.id, recordingUri, endedAt);
        }
        if (cancelled) return;
        setUploadStatus('done');

        setProcessStatus('running');
        const initialTranscript = await getMeetingTranscript(meeting.id);
        let hasTranscriptSegments = initialTranscript.segments.length > 0;

        if (!hasTranscriptSegments) {
          await processMeeting(meeting.id);
          const startedAt = Date.now();
          while (!cancelled && Date.now() - startedAt < 120000) {
            await wait(3000);
            const nextTranscript = await getMeetingTranscript(meeting.id);
            hasTranscriptSegments = nextTranscript.segments.length > 0;
            refreshMeeting().catch(() => undefined);
            if (hasTranscriptSegments) break;
          }
        }

        if (cancelled) return;
        if (!hasTranscriptSegments) {
          throw new Error('转写未完成，请稍后重试');
        }

        await refreshMeeting();
        await analyzeMeeting(meeting.id);
        await refreshMeeting();
      } catch (nextError) {
        if (cancelled) return;
        setUploadStatus((current) => (current === 'done' ? current : 'failed'));
        setProcessStatus('failed');
        setError(nextError instanceof Error ? nextError.message : 'AI 处理启动失败。');
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [endedAt, meeting.id, realtimeTranscriptReady, recordingUri, refreshMeeting]);

  useEffect(() => {
    if (hasSummaryContent(summaryResult) || hasSummaryContent(meetingDetail?.summary) || isMeetingFailed(meetingDetail)) {
      return undefined;
    }
    if (processStatus === 'failed') return undefined;
    if (processStatus !== 'running') return undefined;
    const timer = setInterval(() => {
      getMeetingSummary(meeting.id)
        .then((nextSummary) => {
          setSummaryResult(nextSummary);
          if (hasSummaryContent(nextSummary)) {
            setProcessStatus('done');
          }
        })
        .catch((nextError) => {
          setError(nextError instanceof Error ? nextError.message : '会议纪要刷新失败。');
        });
      refreshMeeting().catch(() => undefined);
    }, 3000);
    return () => clearInterval(timer);
  }, [meeting.id, meetingDetail, processStatus, refreshMeeting, summaryResult]);

  useEffect(() => {
    if (!meetingDetail) return;
    if (isMeetingFailed(meetingDetail)) {
      setProcessStatus('failed');
      setError('AI 处理失败，请稍后在历史会议中重试或查看错误信息。');
    }
  }, [meetingDetail]);

  const stages = useMemo<ProcessingStage[]>(() => {
    const hasAudio = uploadStatus === 'done' || Boolean(meetingDetail?.audio_files.length);
    const hasTranscript = Boolean(meetingDetail?.transcript_segments.length);
    const hasSpeaker = hasTranscript;
    const hasSummary = hasSummaryContent(summaryResult) || hasSummaryContent(meetingDetail?.summary) || meetingDetail?.status === 'completed';
    const failed = processStatus === 'failed' || isMeetingFailed(meetingDetail);

    return [
      {
        key: 'upload',
        label: '音频上传完成',
        status: failed && !hasAudio ? 'failed' : hasAudio ? 'done' : uploadStatus,
      },
      {
        key: 'audio',
        label: hasAudio ? '音频处理中' : '等待音频上传',
        status: failed && !hasTranscript ? 'failed' : hasTranscript ? 'done' : hasAudio ? 'running' : 'pending',
      },
      {
        key: 'transcript',
        label: '正在转写',
        status: failed && !hasTranscript ? 'failed' : hasTranscript ? 'done' : hasAudio ? 'running' : 'pending',
      },
      {
        key: 'speaker',
        label: '正在识别说话人',
        status: failed && !hasSpeaker ? 'failed' : hasSpeaker ? 'done' : hasTranscript ? 'running' : 'pending',
      },
      {
        key: 'summary',
        label: '正在生成会议纪要...',
        status: failed && !hasSummary ? 'failed' : hasSummary ? 'done' : hasTranscript ? 'running' : 'pending',
      },
    ];
  }, [meetingDetail, processStatus, uploadStatus]);

  const progress = Math.round((stages.reduce((sum, stage) => sum + statusRank(stage.status), 0) / stages.length) * 100);
  const finished = stages.every((stage) => stage.status === 'done');
  const failed = stages.some((stage) => stage.status === 'failed');

  return (
    <View style={styles.container}>
      <View style={styles.titleBlock}>
        <Text numberOfLines={1} style={styles.meetingTitle}>
          {meeting.title}
        </Text>
        <Text style={styles.people}>AI 分析中</Text>
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
                stage.status === 'done' ? styles.stageIconDone : null,
                stage.status === 'failed' ? styles.stageIconFailed : null,
              ]}
            >
              {stage.status === 'running' ? (
                <ActivityIndicator color="#6657ff" size="small" />
              ) : (
                <Text style={styles.stageIconText}>{stage.status === 'failed' ? '!' : '✓'}</Text>
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
  stageIconText: {
    color: '#16a34a',
    fontSize: 12,
    fontWeight: '900',
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
    gap: 5,
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
});
