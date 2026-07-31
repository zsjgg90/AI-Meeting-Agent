import { Audio, AVPlaybackStatus } from 'expo-av';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Linking,
  Modal,
  PanResponder,
  Pressable,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  ActionItem,
  getMeeting,
  getMeetingSummary,
  Meeting,
  meetingAudioUrl,
  meetingExportUrl,
  MeetingDetail,
  MeetingSummary,
  reindexMeetingKnowledge,
  TranscriptSegment,
  updateSpeakerMapping,
} from '../api';
import { LucideIcon } from '../components/LucideIcon';
import { NumberedList } from '../components/NumberedList';
import { chooseMeetingAudioFile } from '../utils/audioFiles';
import { normalizeNumberedListItems } from '../utils/numberedList';

type Props = {
  meetingId: string;
  initialTab?: LegacyDetailTab | DetailTab;
  sourceSegmentId?: string | null;
  startTime?: number | null;
  evidenceText?: string | null;
  onBack: () => void;
  onRecord: (meeting: Meeting) => void;
  onOpenAudioPlayer: (meetingId: string) => void;
  onOpenKnowledgeBase: () => void;
};

type LegacyDetailTab = 'decisions' | 'questions' | 'actions' | 'risks';
type DetailTab = 'transcript' | 'summary' | 'agent';
type ExportFormat = 'md' | 'pdf' | 'docx' | 'txt';
type AudioLoadState = 'idle' | 'loading' | 'ready' | 'missing' | 'failed';

const brandBlue = '#2B6CFF';
const speakerColors = ['#2B6CFF', '#F59E0B', '#10B981', '#8B5CF6', '#EF4444', '#0EA5E9', '#14B8A6', '#F97316'];
const supportedTranscriptExports: ExportFormat[] = ['md', 'pdf', 'docx', 'txt'];
const supportedSummaryExports: ExportFormat[] = ['md', 'pdf', 'docx', 'txt'];

const tabs: Array<{ key: DetailTab; label: string }> = [
  { key: 'transcript', label: '会议原文' },
  { key: 'summary', label: 'AI纪要' },
  { key: 'agent', label: 'Agent工具' },
];

const meetingStatusText: Record<string, string> = {
  created: '待录音',
  uploaded: '已上传',
  audio_uploaded: '已上传',
  processing: '分析中',
  transcribing: '转写中',
  transcribed: '已转写',
  summarizing: '生成纪要中',
  completed: '已完成',
  failed: '失败',
  transcription_failed: '转写失败',
  summary_failed: '纪要失败',
};

function statusText(status: string): string {
  return meetingStatusText[status] || status;
}

function normalizeInitialTab(initialTab: Props['initialTab']): DetailTab {
  if (initialTab === 'summary' || initialTab === 'agent') return initialTab;
  return 'transcript';
}

function resultSourceText(summary: MeetingSummary | null | undefined): string {
  const source = summary?.metadata?.result_source;
  if (source === 'fixture') return '人工校准纪要';
  if (source === 'legacy_qwen_rag') return 'AI 生成纪要';
  if (source === 'semantic_pipeline') return '语义分析纪要';
  return '历史纪要';
}

function hasSummaryContent(
  summary: MeetingSummary | null | undefined,
  fallbackOutput: MeetingDetail['output'] | null | undefined,
): boolean {
  return Boolean(
    summary?.meeting_summary?.trim() ||
      summary?.overview?.trim() ||
      fallbackOutput?.summary?.trim() ||
      summary?.key_conclusions?.length ||
      summary?.action_items?.length,
  );
}

function summaryDisplayStatus(
  meeting: MeetingDetail | null,
  summary: MeetingSummary | null | undefined,
  fallbackOutput: MeetingDetail['output'] | null | undefined,
): string {
  const status = meeting?.status || '';
  if ((status === 'failed' || status === 'summary_failed') && hasSummaryContent(summary, fallbackOutput)) {
    return 'completed';
  }
  return status;
}

function textValue(item: unknown, keys: string[]): string {
  if (typeof item === 'string') return item.trim();
  if (!item || typeof item !== 'object') return '';
  const record = item as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return Object.entries(record)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join('、') : String(value)}`)
    .join('；');
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '未设置';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未设置';
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day} ${hours}:${minutes}`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return '未知';
  const safe = Math.round(seconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const rest = safe % 60;
  if (hours) return `${hours}小时${minutes}分${rest}秒`;
  if (minutes) return `${minutes}分${rest}秒`;
  return `${rest}秒`;
}

function formatTimestamp(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '--:--';
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const rest = safe % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function speakerSortValue(label: string): number {
  const match = label.match(/\d+/);
  return match ? Number(match[0]) : 999;
}

function segmentStart(segment: TranscriptSegment): number {
  return typeof segment.start_time === 'number' && Number.isFinite(segment.start_time) ? segment.start_time : 0;
}

function segmentEnd(segment: TranscriptSegment): number {
  return typeof segment.end_time === 'number' && Number.isFinite(segment.end_time) ? segment.end_time : segmentStart(segment);
}

function meetingDurationSeconds(meeting: MeetingDetail): number | null {
  const lastSegment = meeting.transcript_segments[meeting.transcript_segments.length - 1];
  if (lastSegment && segmentEnd(lastSegment) > 0) return segmentEnd(lastSegment);
  if (meeting.created_at && meeting.end_at) {
    const start = new Date(meeting.created_at).getTime();
    const end = new Date(meeting.end_at).getTime();
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) return (end - start) / 1000;
  }
  return null;
}

function cleanSummaryText(value: string): string {
  return value
    .replace(/\r\n?/g, '\n')
    .replace(/\[[^\]]+\]\s*[^:；]+[:；]\s*/g, '')
    .replace(/[ \t\f\v]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function parseTimeValue(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const numeric = Number(normalized.replace(/s$/, ''));
  if (Number.isFinite(numeric)) return numeric;
  if (!/^\d{1,2}:\d{1,2}(?::\d{1,2})?$/.test(normalized)) return null;
  const parts = normalized.split(':').map(Number);
  if (parts.some((part) => !Number.isFinite(part))) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function objectValue(item: unknown, keys: string[]): string {
  if (!item || typeof item !== 'object') return '';
  const record = item as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return '';
}

function getEvidenceText(item: unknown): string {
  const direct = objectValue(item, ['source_text', 'evidence', 'source']);
  if (direct) return direct;
  if (!item || typeof item !== 'object') return '';
  const evidence = (item as Record<string, unknown>).evidence;
  if (Array.isArray(evidence)) {
    return evidence
      .map((value) => textValue(value, ['source_text', 'text', 'content']))
      .filter(Boolean)
      .join('；');
  }
  return '';
}

function evidenceStartSeconds(item: unknown): number | null {
  if (!item || typeof item !== 'object') return null;
  const record = item as Record<string, unknown>;
  for (const key of ['start_time', 'timestamp']) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      const seconds = parseTimeValue(value);
      if (seconds !== null) return seconds;
    }
  }
  return null;
}

function evidenceSegmentId(item: unknown): string {
  return objectValue(item, ['source_segment_id', 'segment_id']);
}

function statusLabel(value: string | null | undefined): string {
  if (!value) return '未开始';
  const normalized = value.toLowerCase();
  if (['completed', 'done', 'closed', 'finished'].includes(normalized)) return '已完成';
  if (['in_progress', 'running', 'processing'].includes(normalized)) return '进行中';
  if (['blocked', 'review'].includes(normalized)) return '需关注';
  return value;
}

function isCompletedStatus(value: string | null | undefined): boolean {
  return Boolean(value && ['completed', 'done', 'closed', 'finished'].includes(value.toLowerCase()));
}

function compactMetaParts(parts: Array<string | null | undefined>): string[] {
  return parts.map((part) => (part || '').trim()).filter(Boolean);
}

function buildQuickLookSegments(segments: TranscriptSegment[]) {
  if (segments.length < 3) return [];
  const result: TranscriptSegment[] = [];
  let previousSpeaker = '';
  for (const segment of segments) {
    const speaker = segment.speaker_label || segment.speaker_name || '';
    const gap = result.length ? segmentStart(segment) - segmentStart(result[result.length - 1]) : Number.POSITIVE_INFINITY;
    if (!result.length || (speaker && speaker !== previousSpeaker && gap >= 20) || gap >= 90) {
      result.push(segment);
      previousSpeaker = speaker;
    }
    if (result.length >= 6) break;
  }
  return result;
}

export function MeetingDetailScreen({
  meetingId,
  initialTab = 'transcript',
  sourceSegmentId,
  startTime,
  evidenceText,
  onBack,
  onRecord,
  onOpenKnowledgeBase,
}: Props) {
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [summaryOverride, setSummaryOverride] = useState<MeetingSummary | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>(normalizeInitialTab(initialTab));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [audioState, setAudioState] = useState<AudioLoadState>('idle');
  const [, setSound] = useState<Audio.Sound | null>(null);
  const soundRef = useRef<Audio.Sound | null>(null);
  const soundLoadingPromiseRef = useRef<Promise<Audio.Sound | null> | null>(null);
  const audioBusyRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const pendingPlayIntentRef = useRef(false);
  const [positionMillis, setPositionMillis] = useState(0);
  const [durationMillis, setDurationMillis] = useState(0);
  const [segmentPlaybackId, setSegmentPlaybackId] = useState<string | null>(null);
  const [speakerNameDrafts, setSpeakerNameDrafts] = useState<Record<string, string>>({});
  const [speakerNoteDrafts, setSpeakerNoteDrafts] = useState<Record<string, string>>({});
  const [savingSpeaker, setSavingSpeaker] = useState<string | null>(null);
  const [editingSpeakerLabel, setEditingSpeakerLabel] = useState<string | null>(null);
  const [exportingSummaryFormat, setExportingSummaryFormat] = useState<ExportFormat | null>(null);
  const [exportingTranscriptFormat, setExportingTranscriptFormat] = useState<ExportFormat | null>(null);
  const [runningAgentTool, setRunningAgentTool] = useState<string | null>(null);
  const checkingAgentTools = false;
  const progressWidthRef = useRef(1);
  const listRef = useRef<FlatList<TranscriptSegment>>(null);
  const segmentPlaybackRef = useRef<{ id: string; endMillis: number } | null>(null);
  const loadedAudioKeyRef = useRef<string | null>(null);
  const pendingSeekMillisRef = useRef<number | null>(null);
  const isScrubbingRef = useRef(false);

  const selectedAudio = useMemo(() => chooseMeetingAudioFile(meeting?.audio_files || []), [meeting?.audio_files]);
  const selectedAudioKey = meeting && selectedAudio ? `${meeting.id}:${selectedAudio.id}` : null;
  const transcriptSegments = meeting?.transcript_segments || [];
  const summary = summaryOverride || meeting?.summary;
  const fallbackOutput = meeting?.output;
  const progress = durationMillis > 0 ? Math.min(1, positionMillis / durationMillis) : 0;
  const currentSeconds = positionMillis / 1000;
  const isMainPlaybackActive = isPlaying && !segmentPlaybackId;

  const speakerDisplayNames = useMemo(
    () =>
      meeting?.speaker_mappings.reduce<Record<string, string>>((acc, mapping) => {
        acc[mapping.speaker_label] = mapping.display_name;
        return acc;
      }, {}) || {},
    [meeting],
  );

  const speakerLabels = useMemo(
    () =>
      Array.from(
        new Set(transcriptSegments.map((segment) => segment.speaker_label || segment.speaker_name).filter(Boolean) as string[]),
      ).sort((left, right) => speakerSortValue(left) - speakerSortValue(right)),
    [transcriptSegments],
  );

  const currentSegmentId = useMemo(() => {
    if (!isPlaying && positionMillis === 0) return null;
    return (
      transcriptSegments.find((segment) => segmentStart(segment) <= currentSeconds && segmentEnd(segment) >= currentSeconds)?.id || null
    );
  }, [currentSeconds, isPlaying, positionMillis, transcriptSegments]);

  const quickLookSegments = useMemo(() => buildQuickLookSegments(transcriptSegments), [transcriptSegments]);

  const loadMeeting = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const nextMeeting = await getMeeting(meetingId);
      setMeeting(nextMeeting);
      setAudioState(chooseMeetingAudioFile(nextMeeting.audio_files) ? 'idle' : 'missing');
      try {
        setSummaryOverride(await getMeetingSummary(meetingId));
      } catch {
        setSummaryOverride(nextMeeting.summary);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '会议详情加载失败。');
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    loadMeeting();
  }, [loadMeeting]);

  useEffect(() => {
    const activeSound = soundRef.current;
    soundRef.current = null;
    soundLoadingPromiseRef.current = null;
    loadedAudioKeyRef.current = null;
    segmentPlaybackRef.current = null;
    audioBusyRef.current = false;
    pendingPlayIntentRef.current = false;
    setSound(null);
    setIsPlaying(false);
    setPositionMillis(0);
    setDurationMillis(0);
    setSegmentPlaybackId(null);
    setAudioState('idle');
    activeSound?.unloadAsync().catch(() => undefined);
  }, [meetingId]);

  useEffect(() => {
    setActiveTab(normalizeInitialTab(initialTab));
  }, [initialTab, meetingId]);

  useEffect(() => {
    return () => {
      soundRef.current?.unloadAsync().catch(() => undefined);
      soundRef.current = null;
      soundLoadingPromiseRef.current = null;
      loadedAudioKeyRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (loadedAudioKeyRef.current === null || loadedAudioKeyRef.current === selectedAudioKey) return;
    const activeSound = soundRef.current;
    soundRef.current = null;
    soundLoadingPromiseRef.current = null;
    loadedAudioKeyRef.current = null;
    segmentPlaybackRef.current = null;
    audioBusyRef.current = false;
    pendingPlayIntentRef.current = false;
    setSound(null);
    setIsPlaying(false);
    setPositionMillis(0);
    setDurationMillis(0);
    setSegmentPlaybackId(null);
    setAudioState(selectedAudioKey ? 'idle' : 'missing');
    activeSound?.unloadAsync().catch(() => undefined);
  }, [selectedAudioKey]);

  useEffect(() => {
    if (!meeting || !selectedAudio || !selectedAudioKey) return;
    if (soundRef.current && loadedAudioKeyRef.current === selectedAudioKey) return;
    if (soundLoadingPromiseRef.current) return;

    let cancelled = false;
    ensureSound().catch(() => {
      if (!cancelled) {
        pendingPlayIntentRef.current = false;
        setIsPlaying(false);
        setAudioState('failed');
      }
    });

    return () => {
      cancelled = true;
    };
  }, [meeting, selectedAudio, selectedAudioKey]);

  useEffect(() => {
    if (!meeting || !['processing', 'transcribing', 'transcribed', 'summarizing'].includes(meeting.status)) {
      return undefined;
    }
    const timer = setInterval(loadMeeting, 3000);
    return () => clearInterval(timer);
  }, [loadMeeting, meeting]);

  useEffect(() => {
    if (!meeting) return;
    const names: Record<string, string> = {};
    const notes: Record<string, string> = {};
    for (const segment of transcriptSegments) {
      const speakerLabel = segment.speaker_label || segment.speaker_name;
      if (speakerLabel) {
        names[speakerLabel] = '';
        notes[speakerLabel] = '';
      }
    }
    for (const mapping of meeting.speaker_mappings) {
      names[mapping.speaker_label] = mapping.display_name;
      notes[mapping.speaker_label] = mapping.note || '';
    }
    setSpeakerNameDrafts((current) => ({ ...names, ...current }));
    setSpeakerNoteDrafts((current) => ({ ...notes, ...current }));
  }, [meeting, transcriptSegments]);

  useEffect(() => {
    if (!meeting || activeTab !== 'transcript') return;
    let targetIndex = -1;
    if (sourceSegmentId) {
      targetIndex = transcriptSegments.findIndex((item) => item.id === sourceSegmentId);
    } else if (typeof startTime === 'number') {
      targetIndex = transcriptSegments.findIndex((item) => segmentStart(item) <= startTime && segmentEnd(item) >= startTime);
    } else if (evidenceText?.trim()) {
      targetIndex = transcriptSegments.findIndex((item) => item.text.includes(evidenceText.trim()));
    }
    if (targetIndex >= 0) {
      setTimeout(() => listRef.current?.scrollToIndex({ index: targetIndex, animated: true, viewPosition: 0.25 }), 250);
    }
  }, [activeTab, evidenceText, meeting, sourceSegmentId, startTime, transcriptSegments]);

  function displaySpeaker(speakerLabel: string | null): string {
    if (!speakerLabel) return '说话人';
    if (speakerDisplayNames[speakerLabel]) return speakerDisplayNames[speakerLabel];
    const index = speakerLabels.indexOf(speakerLabel);
    return index >= 0 ? `说话人${index + 1}` : '说话人';
  }

  function speakerColor(speakerLabel: string | null): string {
    if (!speakerLabel) return brandBlue;
    const index = Math.max(0, speakerLabels.indexOf(speakerLabel));
    return speakerColors[index % speakerColors.length];
  }

  function replaceSpeakerLabels(value: string | null | undefined): string {
    if (!value) return '';
    let result = value;
    for (const speakerLabel of speakerLabels) {
      const displayName = displaySpeaker(speakerLabel);
      result = result.replace(new RegExp(escapeRegExp(speakerLabel), 'g'), displayName);
      result = result.replace(new RegExp(escapeRegExp(speakerLabel.replace('_', '')), 'g'), displayName);
    }
    return result;
  }

  function updatePlaybackStatus(status: AVPlaybackStatus) {
    if (!status.isLoaded) {
      pendingPlayIntentRef.current = false;
      setAudioState('failed');
      return;
    }
    setAudioState('ready');
    setIsPlaying(status.isPlaying || pendingPlayIntentRef.current);
    if (!isScrubbingRef.current) setPositionMillis(status.positionMillis);
    setDurationMillis(status.durationMillis || 0);
    const segmentPlayback = segmentPlaybackRef.current;
    if (segmentPlayback && status.isPlaying && status.positionMillis >= segmentPlayback.endMillis) {
      soundRef.current?.pauseAsync().catch(() => undefined);
      soundRef.current?.setPositionAsync(segmentPlayback.endMillis).catch(() => undefined);
      segmentPlaybackRef.current = null;
      pendingPlayIntentRef.current = false;
      setSegmentPlaybackId(null);
      setIsPlaying(false);
      setPositionMillis(segmentPlayback.endMillis);
      return;
    }
    if (status.didJustFinish) {
      segmentPlaybackRef.current = null;
      pendingPlayIntentRef.current = false;
      setSegmentPlaybackId(null);
      setIsPlaying(false);
      setPositionMillis(status.durationMillis || status.positionMillis || 0);
    }
  }

  async function ensureSound(): Promise<Audio.Sound | null> {
    if (!meeting || !selectedAudio || !selectedAudioKey) {
      setAudioState('missing');
      return null;
    }
    if (soundRef.current && loadedAudioKeyRef.current === selectedAudioKey) return soundRef.current;
    if (soundLoadingPromiseRef.current) return soundLoadingPromiseRef.current;

    const loadingPromise = (async () => {
      if (soundRef.current) {
        const staleSound = soundRef.current;
        soundRef.current = null;
        loadedAudioKeyRef.current = null;
        segmentPlaybackRef.current = null;
        setSound(null);
        setIsPlaying(false);
        setSegmentPlaybackId(null);
        await staleSound.unloadAsync().catch(() => undefined);
      }

      setAudioState('loading');
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
        shouldDuckAndroid: true,
        playThroughEarpieceAndroid: false,
      });

      const nextSound = new Audio.Sound();
      nextSound.setOnPlaybackStatusUpdate(updatePlaybackStatus);
      await nextSound.loadAsync({ uri: meetingAudioUrl(meeting.id, selectedAudio.id) }, { shouldPlay: false });
      soundRef.current = nextSound;
      loadedAudioKeyRef.current = selectedAudioKey;
      setSound(nextSound);
      updatePlaybackStatus(await nextSound.getStatusAsync());
      return nextSound;
    })();

    soundLoadingPromiseRef.current = loadingPromise;
    try {
      return await loadingPromise;
    } finally {
      if (soundLoadingPromiseRef.current === loadingPromise) {
        soundLoadingPromiseRef.current = null;
      }
    }
  }

  async function runAudioAction(action: (activeSound: Audio.Sound) => Promise<void>) {
    if (audioBusyRef.current) return;
    audioBusyRef.current = true;
    try {
      const activeSound = await ensureSound();
      if (!activeSound) return;
      await action(activeSound);
      updatePlaybackStatus(await activeSound.getStatusAsync());
    } catch (nextError) {
      pendingPlayIntentRef.current = false;
      setIsPlaying(false);
      setAudioState('failed');
    } finally {
      audioBusyRef.current = false;
    }
  }

  async function togglePlayback() {
    if (audioState === 'missing') return;
    if (audioBusyRef.current) {
      if (pendingPlayIntentRef.current) {
        pendingPlayIntentRef.current = false;
        setIsPlaying(false);
      }
      return;
    }
    const expectsPlay = !isPlaying;
    if (expectsPlay) {
      pendingPlayIntentRef.current = true;
      setIsPlaying(true);
    }
    await runAudioAction(async (activeSound) => {
      const status = await activeSound.getStatusAsync();
      if (!status.isLoaded) {
        pendingPlayIntentRef.current = false;
        setIsPlaying(false);
        return;
      }
      if (status.isPlaying) {
        pendingPlayIntentRef.current = false;
        setIsPlaying(false);
        await activeSound.pauseAsync();
        segmentPlaybackRef.current = null;
        setSegmentPlaybackId(null);
      } else {
        if (expectsPlay && !pendingPlayIntentRef.current) return;
        segmentPlaybackRef.current = null;
        setSegmentPlaybackId(null);
        const nextPosition = status.didJustFinish || (status.durationMillis && status.positionMillis >= status.durationMillis) ? 0 : status.positionMillis;
        await activeSound.setPositionAsync(nextPosition);
        await activeSound.playAsync();
        pendingPlayIntentRef.current = false;
      }
    });
  }

  async function seekToSeconds(seconds: number, shouldPlay?: boolean) {
    await runAudioAction(async (activeSound) => {
      segmentPlaybackRef.current = null;
      setSegmentPlaybackId(null);
      const status = await activeSound.getStatusAsync();
      const duration = status.isLoaded ? status.durationMillis || durationMillis || 0 : durationMillis;
      const nextPosition = Math.max(0, Math.min(duration || Number.MAX_SAFE_INTEGER, seconds * 1000));
      await activeSound.setPositionAsync(nextPosition);
      if (shouldPlay) await activeSound.playAsync();
    });
  }

  async function seekBy(offsetMillis: number) {
    await runAudioAction(async (activeSound) => {
      const status = await activeSound.getStatusAsync();
      if (!status.isLoaded) return;
      const duration = status.durationMillis || durationMillis || 0;
      const nextPosition = Math.max(0, Math.min(duration || Number.MAX_SAFE_INTEGER, status.positionMillis + offsetMillis));
      segmentPlaybackRef.current = null;
      setSegmentPlaybackId(null);
      await activeSound.setPositionAsync(nextPosition);
    });
  }

  function previewProgressSeek(x: number) {
    const nextProgress = Math.max(0, Math.min(1, x / progressWidthRef.current));
    if (!durationMillis) return;
    const nextMillis = nextProgress * durationMillis;
    pendingSeekMillisRef.current = nextMillis;
    isScrubbingRef.current = true;
    segmentPlaybackRef.current = null;
    setSegmentPlaybackId(null);
    setPositionMillis(nextMillis);
  }

  function commitProgressSeek() {
    const nextMillis = pendingSeekMillisRef.current;
    pendingSeekMillisRef.current = null;
    isScrubbingRef.current = false;
    if (nextMillis === null) return;
    void seekToSeconds(nextMillis / 1000);
  }

  const progressPanResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: () => durationMillis > 0,
        onPanResponderGrant: (event) => previewProgressSeek(event.nativeEvent.locationX),
        onPanResponderMove: (event) => previewProgressSeek(event.nativeEvent.locationX),
        onPanResponderRelease: commitProgressSeek,
        onPanResponderTerminate: commitProgressSeek,
        onStartShouldSetPanResponder: () => durationMillis > 0,
      }),
    [durationMillis],
  );

  async function jumpToSegment(segment: TranscriptSegment, shouldPlay?: boolean) {
    const wasTranscriptTab = activeTab === 'transcript';
    setActiveTab('transcript');
    const index = transcriptSegments.findIndex((item) => item.id === segment.id);
    if (index >= 0) {
      const scrollToSegment = () => listRef.current?.scrollToIndex({ index, animated: true, viewPosition: 0.25 });
      if (wasTranscriptTab) {
        scrollToSegment();
      } else {
        setTimeout(scrollToSegment, 250);
      }
    }
    await seekToSeconds(segmentStart(segment), shouldPlay);
  }

  async function toggleSegmentPlayback(segment: TranscriptSegment) {
    await runAudioAction(async (activeSound) => {
      const status = await activeSound.getStatusAsync();
      if (!status.isLoaded) return;
      if (segmentPlaybackRef.current?.id === segment.id && status.isPlaying) {
        await activeSound.pauseAsync();
        segmentPlaybackRef.current = null;
        setSegmentPlaybackId(null);
        return;
      }
      const duration = status.isLoaded ? status.durationMillis || durationMillis || 0 : durationMillis;
      const rawStartMillis = segmentStart(segment) * 1000;
      const rawEndMillis = Math.max(rawStartMillis, segmentEnd(segment) * 1000);
      const startMillis = Math.max(0, Math.min(duration || Number.MAX_SAFE_INTEGER, rawStartMillis));
      const endMillis = Math.max(startMillis, Math.min(duration || rawEndMillis, rawEndMillis));
      segmentPlaybackRef.current = { id: segment.id, endMillis };
      setSegmentPlaybackId(segment.id);
      await activeSound.setPositionAsync(startMillis);
      await activeSound.playAsync();
    });
  }

  async function openExport(kind: 'transcript' | 'summary', format: ExportFormat) {
    if (kind === 'summary' && exportingSummaryFormat) return;
    if (kind === 'transcript' && exportingTranscriptFormat) return;
    try {
      setError(null);
      if (kind === 'summary') {
        setExportingSummaryFormat(format);
      } else {
        setExportingTranscriptFormat(format);
      }
      await Linking.openURL(meetingExportUrl(meetingId, kind, format));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '导出失败，请稍后重试。');
    } finally {
      if (kind === 'summary') {
        setExportingSummaryFormat(null);
      } else {
        setExportingTranscriptFormat(null);
      }
    }
  }

  function openSpeakerEditor(speakerLabel: string) {
    setSpeakerNameDrafts((current) => ({
      ...current,
      [speakerLabel]: speakerDisplayNames[speakerLabel] || displaySpeaker(speakerLabel),
    }));
    setEditingSpeakerLabel(speakerLabel);
  }

  async function saveSpeaker(speakerLabel: string) {
    const displayName = (speakerNameDrafts[speakerLabel] || '').trim();
    const note = (speakerNoteDrafts[speakerLabel] || '').trim();
    if (!displayName) {
      setError('说话人名称不能为空。');
      return;
    }
    try {
      setSavingSpeaker(speakerLabel);
      setError(null);
      await updateSpeakerMapping(meetingId, speakerLabel, displayName, note);
      setEditingSpeakerLabel(null);
      await loadMeeting();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '保存说话人信息失败。');
    } finally {
      setSavingSpeaker(null);
    }
  }

  async function shareMeeting() {
    if (!meeting) return;
    try {
      await Share.share({ message: `${meeting.title}\n${formatDateTime(meeting.created_at)}` });
    } catch {
      Alert.alert('分享失败', '当前设备暂时无法打开系统分享。');
    }
  }

  function showMore() {
    Alert.alert('更多', '本阶段仅保留入口，更多会议操作将在后续版本接入。');
  }

  function renderAudioPlayer() {
    const durationText = durationMillis ? formatTimestamp(durationMillis / 1000) : formatTimestamp(meeting ? meetingDurationSeconds(meeting) : null);

    return (
      <View style={styles.playerCard}>
        <View style={styles.timeRow}>
          <Text style={styles.timeTextStrong}>{formatTimestamp(positionMillis / 1000)}</Text>
          <View
            onLayout={(event) => {
              progressWidthRef.current = Math.max(1, event.nativeEvent.layout.width);
            }}
            {...progressPanResponder.panHandlers}
            style={styles.progressTrack}
          >
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
            <View style={[styles.progressThumb, { left: `${progress * 100}%` }]} />
          </View>
          <Text style={styles.timeTextMuted}>{durationText}</Text>
        </View>
        <View style={styles.controlsRow}>
          <Pressable disabled={audioState === 'missing'} onPress={() => seekBy(-15000)} style={styles.skipButton}>
            <Text style={styles.skipButtonText}>-15</Text>
          </Pressable>
          <Pressable disabled={audioState === 'missing'} onPress={togglePlayback} style={styles.playButton}>
            <LucideIcon name={isMainPlaybackActive ? 'pause' : 'play'} color="#ffffff" size={24} strokeWidth={2.6} />
          </Pressable>
          <Pressable disabled={audioState === 'missing'} onPress={() => seekBy(15000)} style={styles.skipButton}>
            <Text style={styles.skipButtonText}>+15</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  function renderTabs() {
    return (
      <View style={styles.tabs}>
        {tabs.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <Pressable key={tab.key} onPress={() => setActiveTab(tab.key)} style={[styles.tabButton, active ? styles.tabButtonActive : null]}>
              <Text style={[styles.tabText, active ? styles.tabTextActive : null]}>{tab.label}</Text>
            </Pressable>
          );
        })}
      </View>
    );
  }

  function renderQuickLook() {
    return (
      <View style={styles.section}>
        <SectionTitle title="会议速览" />
        {quickLookSegments.length ? (
          quickLookSegments.map((segment) => {
            const speaker = displaySpeaker(segment.speaker_label || segment.speaker_name);
            const title = segment.text.trim() || `${speaker}发言`;
            return (
              <Pressable key={segment.id} onPress={() => jumpToSegment(segment, isPlaying)} style={styles.quickRow}>
                <View style={styles.quickDot} />
                <Text style={styles.quickTime}>{formatTimestamp(segmentStart(segment))}</Text>
                <Text numberOfLines={1} style={styles.quickTitle}>
                  {title}
                </Text>
                <LucideIcon name="chevron-down" color="#9ca3af" size={16} />
              </Pressable>
            );
          })
        ) : (
          <Text style={styles.empty}>暂无可靠的章节数据。转写分段不足时不生成会议速览。</Text>
        )}
      </View>
    );
  }

  function renderExportButtons() {
    return (
      <View style={styles.exportSection}>
        <Text style={styles.exportTitle}>导出文稿</Text>
        <View style={styles.exportRow}>
          {(['md', 'pdf', 'docx', 'txt'] as ExportFormat[]).map((format) => {
            const enabled = supportedTranscriptExports.includes(format);
            const busy = exportingTranscriptFormat === format;
            return (
              <Pressable
                key={format}
                disabled={!enabled || Boolean(exportingTranscriptFormat)}
                onPress={() => openExport('transcript', format)}
                style={[styles.exportButton, !enabled ? styles.exportButtonDisabled : null]}
              >
                <Text style={[styles.exportText, !enabled ? styles.exportTextDisabled : null]}>{busy ? '导出中' : format.toUpperCase()}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    );
  }

  function jumpToEvidence(item: unknown) {
    const segmentId = evidenceSegmentId(item);
    const seconds = evidenceStartSeconds(item);
    const segment =
      (segmentId ? transcriptSegments.find((candidate) => candidate.id === segmentId) : null) ||
      (typeof seconds === 'number'
        ? transcriptSegments.find((candidate) => segmentStart(candidate) <= seconds && segmentEnd(candidate) >= seconds)
        : null);
    if (segment) {
      void jumpToSegment(segment, false);
    } else if (typeof seconds === 'number') {
      setActiveTab('transcript');
      void seekToSeconds(seconds);
    } else if (segmentId) {
      setActiveTab('transcript');
      setError('未找到对应原文片段，已切换到会议原文。');
    }
  }

  function renderSummaryExportButtons() {
    return (
      <View style={styles.summaryExportBlock}>
        <Text style={styles.summaryExportTitle}>导出AI文稿</Text>
        <View style={styles.exportRow}>
          {(['md', 'pdf', 'docx', 'txt'] as ExportFormat[]).map((format) => {
            const enabled = supportedSummaryExports.includes(format);
            const busy = exportingSummaryFormat === format;
            return (
              <Pressable
                key={format}
                disabled={!enabled || Boolean(exportingSummaryFormat)}
                onPress={() => openExport('summary', format)}
                style={[styles.summaryExportButton, !enabled || exportingSummaryFormat ? styles.summaryExportButtonDisabled : null]}
              >
                <Text style={[styles.summaryExportText, !enabled ? styles.exportTextDisabled : null]}>{busy ? '导出中' : format.toUpperCase()}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    );
  }

  function renderEvidence(item: unknown) {
    const text = replaceSpeakerLabels(getEvidenceText(item));
    const seconds = evidenceStartSeconds(item);
    const segmentId = evidenceSegmentId(item);
    if (!text && typeof seconds !== 'number' && !segmentId) return null;
    return (
      <View style={styles.evidenceBox}>
        <View style={styles.evidenceHeader}>
          <Text style={styles.evidenceLabel}>证据</Text>
          {typeof seconds === 'number' || segmentId ? (
            <Pressable onPress={() => jumpToEvidence(item)} style={styles.evidenceTimeButton}>
              <Text style={styles.evidenceTimeText}>{typeof seconds === 'number' ? formatTimestamp(seconds) : '定位原文'}</Text>
            </Pressable>
          ) : null}
        </View>
        {text ? <Text style={styles.evidenceText}>{text}</Text> : null}
      </View>
    );
  }

  function renderBulletSection(title: string, rows: unknown[], keys: string[], emptyText: string) {
    const normalizedRows = rows
      .map((item) => ({ item, text: replaceSpeakerLabels(textValue(item, keys)) }))
      .filter((row) => row.text.trim());
    return (
      <View style={styles.summarySection}>
        <Text style={styles.summarySectionTitle}>{title}</Text>
        {normalizedRows.length ? (
          <View style={styles.bulletList}>
            {normalizedRows.map((row, index) => (
              <View key={`${title}-${index}-${row.text}`} style={styles.bulletItem}>
                <View style={styles.bulletDot} />
                <View style={styles.bulletBody}>
                  <Text style={styles.bulletText}>{row.text}</Text>
                  {renderEvidence(row.item)}
                </View>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.empty}>{emptyText}</Text>
        )}
      </View>
    );
  }

  function renderAgendaSection(rows: unknown[]) {
    const values = rows.map((item) => replaceSpeakerLabels(textValue(item, ['item', 'summary', 'title', 'status']))).filter(Boolean);
    return (
      <View style={styles.summarySection}>
        <Text style={styles.summarySectionTitle}>会议议程</Text>
        <NumberedList items={normalizeNumberedListItems(values)} emptyText="暂无会议议程。" />
      </View>
    );
  }

  function renderActionSection(rows: Array<ActionItem | Record<string, unknown>>) {
    const normalizedRows = rows
      .map((item, index) => {
        const task = replaceSpeakerLabels(textValue(item, ['task', 'content', 'action', 'title', 'summary', 'source_text', 'source']));
        if (!task) return null;
        const record = item as Record<string, unknown>;
        const status = typeof record.status === 'string' ? record.status : '';
        const completed = isCompletedStatus(status);
        const owner = replaceSpeakerLabels(objectValue(item, ['owner_name', 'owner']));
        const deadline = objectValue(item, ['deadline', 'due_date']);
        const priority = objectValue(item, ['priority']);
        const meta = compactMetaParts([
          owner ? `负责人：${owner}` : null,
          deadline ? `截止：${deadline}` : null,
          priority ? `优先级：${priority}` : null,
          `状态：${statusLabel(status)}`,
        ]);
        return { completed, index, item, meta, task };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));

    return (
      <View style={styles.summarySection}>
        <Text style={styles.summarySectionTitle}>待办与后续安排</Text>
        {normalizedRows.length ? (
          <View style={styles.actionList}>
            {normalizedRows.map(({ completed, index, item, meta, task }) => {
              return (
                <View key={`action-${index}-${task}`} style={styles.actionItem}>
                  <View style={[styles.readonlyCheckbox, completed ? styles.readonlyCheckboxDone : null]}>
                    {completed ? <LucideIcon name="circle-check-big" color="#2B6CFF" size={14} strokeWidth={2.5} /> : null}
                  </View>
                  <View style={styles.actionBody}>
                    <Text style={[styles.actionText, completed ? styles.actionTextDone : null]}>{task}</Text>
                    {meta.length ? <Text style={styles.actionMeta}>{meta.join('  ')}</Text> : null}
                    {renderEvidence(item)}
                  </View>
                </View>
              );
            })}
          </View>
        ) : (
          <Text style={styles.empty}>暂无待办与后续安排。</Text>
        )}
      </View>
    );
  }

  function renderSummaryTab() {
    if (!meeting) return null;
    const displayStatus = summaryDisplayStatus(meeting, summary, fallbackOutput);
    const processing = ['processing', 'transcribing', 'transcribed', 'summarizing'].includes(displayStatus);
    const failed = ['failed', 'summary_failed', 'transcription_failed'].includes(displayStatus) && !hasSummaryContent(summary, fallbackOutput);
    const agendaRows = summary?.meeting_agenda?.length ? summary.meeting_agenda : summary?.agenda || [];
    const decisionRows = summary?.key_conclusions?.length ? summary.key_conclusions : summary?.decisions || [];
    const actionRows = (summary?.action_items?.length ? summary.action_items : meeting.action_items || []) as Array<ActionItem | Record<string, unknown>>;
    const issueRows = summary?.unresolved_issues?.length ? summary.unresolved_issues : summary?.open_questions || [];
    const riskRows = summary?.risks_and_focus?.length ? summary.risks_and_focus : summary?.risks || [];
    const overview = replaceSpeakerLabels(cleanSummaryText(summary?.meeting_summary || summary?.overview || fallbackOutput?.summary || ''));
    const participants = speakerLabels.map(displaySpeaker);
    const hasAgendaContent = normalizeNumberedListItems(
      agendaRows.map((item) => replaceSpeakerLabels(textValue(item, ['item', 'summary', 'title', 'status']))),
    ).length > 0;
    const hasDecisionContent = decisionRows.some((item) => textValue(item, ['conclusion', 'decision', 'title', 'summary', 'reason']).trim());
    const hasActionContent = actionRows.some((item) => textValue(item, ['task', 'content', 'action', 'title', 'summary', 'source_text', 'source']).trim());
    const hasIssueContent = issueRows.some((item) => textValue(item, ['issue', 'question', 'title', 'reason', 'blocker']).trim());
    const hasRiskContent = riskRows.some((item) => textValue(item, ['risk', 'title', 'summary', 'impact', 'focus_area', 'mitigation']).trim());
    const summaryEmpty = !overview && !hasAgendaContent && !hasDecisionContent && !hasActionContent && !hasIssueContent && !hasRiskContent;
    const basicRows = [
      ['主题', meeting.title],
      ['时间', formatDateTime(meeting.start_at || meeting.created_at)],
      ['地点', meeting.location || '未提供'],
      ['参会人', participants.length ? participants.join('、') : '未提供'],
    ];

    return (
      <View style={styles.summaryContainer}>
        <View style={styles.summaryCoverCard}>
          <View style={styles.summaryCoverTop}>
            <View style={styles.summaryCoverText}>
              <Text style={styles.summaryCoverTitle}>{meeting.title}</Text>
              <Text style={styles.summaryCoverMeta}>
                {formatDateTime(meeting.start_at || meeting.created_at)} · {formatDuration(meetingDurationSeconds(meeting))}
              </Text>
            </View>
            <View style={styles.statusPill}>
              <Text style={styles.statusPillText}>{statusText(displayStatus)}</Text>
            </View>
          </View>
          {renderSummaryExportButtons()}
        </View>
        <View style={styles.summarySection}>
          <Text style={styles.summarySectionTitle}>基本信息</Text>
          <View style={styles.basicInfoList}>
            {basicRows.map(([label, value]) => (
              <View key={label} style={styles.basicInfoRow}>
                <Text style={styles.basicInfoLabel}>{label}</Text>
                <Text style={styles.basicInfoValue}>{value}</Text>
              </View>
            ))}
          </View>
        </View>
        {processing ? (
          <View style={styles.stateCard}>
            <ActivityIndicator color={brandBlue} size="small" />
            <Text style={styles.stateTitle}>AI分析处理中</Text>
            <Text style={styles.stateText}>会议纪要正在生成，页面会自动刷新。</Text>
          </View>
        ) : null}
        {failed ? (
          <View style={styles.stateCardFailed}>
            <Text style={styles.stateTitleFailed}>AI分析失败</Text>
            <Text style={styles.stateText}>请回到处理页或使用现有重试入口重新分析。</Text>
          </View>
        ) : null}
        {!processing && !failed && summaryEmpty ? (
          <View style={styles.stateCard}>
            <Text style={styles.stateTitle}>暂无AI纪要内容</Text>
            <Text style={styles.stateText}>当前会议还没有可展示的六维分析结果。</Text>
          </View>
        ) : null}
        <View style={styles.summarySection}>
          <View style={styles.summaryHeroHeader}>
            <Text style={styles.summarySectionTitle}>会议总结</Text>
            <Text style={styles.sourceHintText}>{resultSourceText(summary)}</Text>
          </View>
          {overview ? <Text style={styles.summaryLead}>{overview}</Text> : <Text style={styles.empty}>暂无会议总结。</Text>}
        </View>
        {renderAgendaSection(agendaRows)}
        {renderBulletSection('核心结论', decisionRows, ['conclusion', 'decision', 'title', 'summary', 'reason'], '暂无核心结论。')}
        {renderBulletSection('遗留问题', issueRows, ['issue', 'question', 'title', 'reason', 'blocker'], '暂无遗留问题。')}
        {renderBulletSection('风险与关注点', riskRows, ['risk', 'title', 'summary', 'impact', 'focus_area', 'mitigation'], '暂无风险与关注点。')}
        {renderActionSection(actionRows)}
      </View>
    );
  }

  const unavailableAgentTools = [
    {
      id: 'email',
      title: '邮箱推送',
      description: 'AI会议报告推送邮箱',
      disabledReason: '当前版本暂未接入邮箱推送',
      icon: 'mail' as const,
    },
    {
      id: 'feishu',
      title: '飞书任务',
      description: '待办任务推送到飞书',
      disabledReason: '当前版本尚未接入飞书任务',
      icon: 'git-branch' as const,
    },
    {
      id: 'mindmap',
      title: '思维导图',
      description: '从纪要生成会议脑图',
      disabledReason: '当前版本暂未接入正式思维导图生成',
      icon: 'clock-3' as const,
    },
  ];

  async function runKnowledgeTool() {
    if (checkingAgentTools || runningAgentTool || !meeting) return;
    try {
      setRunningAgentTool('knowledge');
      const sync = await reindexMeetingKnowledge(meetingId);
      const message = sync.status === 'completed' ? `已同步 ${sync.item_count} 条会议知识。` : '知识库同步已提交，请稍后查看。';
      Alert.alert('知识库', message, [{ text: '进入知识库', onPress: onOpenKnowledgeBase }, { text: '留在当前页' }]);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : '知识库同步失败，请稍后重试。';
      Alert.alert('知识库同步失败', message);
    } finally {
      setRunningAgentTool(null);
    }
  }

  function renderAgentToolsTab() {
    return (
      <View style={styles.summaryContainer}>
        <View style={styles.summaryHero}>
          <Text style={styles.summaryHeroTitle}>Agent工具</Text>
          <Text style={styles.summaryLead}>基于现有会议结果提供可用工具入口，未接入的能力保持关闭。</Text>
        </View>
        <View style={styles.agentToolGrid}>
          {unavailableAgentTools.map((tool) => (
            <Pressable
              key={tool.id}
              onPress={() => Alert.alert(tool.title, tool.disabledReason)}
              style={[styles.agentToolCard, styles.agentToolCardDisabled]}
            >
              <View style={styles.agentToolIcon}>
                <LucideIcon name={tool.icon} color="#64748B" size={22} strokeWidth={2.2} />
              </View>
              <View style={styles.agentToolText}>
                <Text style={styles.agentToolTitle}>{tool.title}</Text>
                <Text style={styles.agentToolSub}>{tool.description}</Text>
                <Text style={styles.agentToolStatus}>{tool.disabledReason}</Text>
              </View>
            </Pressable>
          ))}
          <Pressable
            disabled={checkingAgentTools || Boolean(runningAgentTool)}
            onPress={runKnowledgeTool}
            style={[styles.agentToolCard, checkingAgentTools || runningAgentTool ? styles.agentToolCardDisabled : null]}
          >
            <View style={[styles.agentToolIcon, styles.agentToolIconActive]}>
              <LucideIcon name="book-open" color="#2B6CFF" size={22} strokeWidth={2.2} />
            </View>
            <View style={styles.agentToolText}>
              <Text style={styles.agentToolTitle}>知识库</Text>
              <Text style={styles.agentToolSub}>同步本会议到知识库</Text>
              <Text style={styles.agentToolStatus}>{runningAgentTool === 'knowledge' ? '同步中' : '可用'}</Text>
            </View>
          </Pressable>
        </View>
        <View style={styles.agentEmptyRecord}>
          <Text style={styles.agentEmptyTitle}>暂无工具使用记录</Text>
          <Text style={styles.agentEmptyText}>当前项目尚未提供邮箱、飞书、思维导图或知识库工具执行记录接口。</Text>
        </View>
        <View style={styles.agentMoreBox}>
          <Text style={styles.agentMoreText}>更多功能即将上线</Text>
        </View>
      </View>
    );
  }

  function renderAgentTab() {
    return renderAgentToolsTab();
  }

  function renderHeader() {
    if (!meeting) return null;
    return (
      <View>
        <View style={styles.topNav}>
          <Pressable onPress={onBack} style={styles.iconButton}>
            <LucideIcon name="chevron-left" color="#111827" size={24} strokeWidth={2.4} />
          </Pressable>
          <Text numberOfLines={1} style={styles.navTitle}>
            {meeting.title}
          </Text>
          <View style={styles.navActions}>
            <Pressable onPress={shareMeeting} style={styles.iconButton}>
              <LucideIcon name="share-2" color="#111827" size={20} strokeWidth={2.2} />
            </Pressable>
            <Pressable onPress={showMore} style={styles.iconButton}>
              <LucideIcon name="more-horizontal" color="#111827" size={22} strokeWidth={2.4} />
            </Pressable>
          </View>
        </View>
        <View style={styles.sheet}>
          {renderAudioPlayer()}
          {renderTabs()}
          {activeTab === 'transcript' ? (
            <>
              <View style={styles.quickMeta}>
                <Text style={styles.quickMetaText}>
                  {statusText(meeting.status)} · {formatDateTime(meeting.created_at)} · {formatDuration(meetingDurationSeconds(meeting))}
                </Text>
              </View>
              {renderQuickLook()}
              {renderExportButtons()}
              <SectionTitle title="会议原文" />
              {transcriptSegments.length === 0 && fallbackOutput?.raw_transcript ? (
                <Text style={styles.fallbackTranscript}>{replaceSpeakerLabels(fallbackOutput.raw_transcript)}</Text>
              ) : null}
              {transcriptSegments.length === 0 && !fallbackOutput?.raw_transcript ? (
                <Text style={styles.empty}>
                  {['processing', 'transcribing', 'transcribed', 'summarizing'].includes(meeting.status)
                    ? '转写处理中，请稍后刷新。'
                    : '暂无转写文本。'}
                </Text>
              ) : null}
            </>
          ) : null}
          {activeTab === 'summary' ? renderSummaryTab() : null}
          {activeTab === 'agent' ? renderAgentToolsTab() : null}
        </View>
      </View>
    );
  }

  function renderSegment({ item, index }: { item: TranscriptSegment; index: number }) {
    const speakerLabel = item.speaker_label || item.speaker_name;
    const speaker = displaySpeaker(speakerLabel);
    const color = speakerColor(speakerLabel);
    const active = currentSegmentId === item.id;
    return (
      <View style={[styles.segmentRow, active ? styles.segmentRowActive : null]}>
        <View style={styles.timelineRail}>
          <View style={[styles.avatar, { backgroundColor: color }]}>
            <Text style={styles.avatarText}>{Math.max(1, speakerLabels.indexOf(speakerLabel || '') + 1)}</Text>
          </View>
          {index < transcriptSegments.length - 1 ? <View style={styles.timelineLine} /> : null}
        </View>
        <View style={styles.segmentBody}>
          <View style={styles.segmentMetaRow}>
            <Pressable onPress={() => openSpeakerEditor(speakerLabel || '')} disabled={!speakerLabel}>
              <Text style={[styles.speakerName, { color }]}>{speaker}</Text>
            </Pressable>
            <Pressable onPress={() => jumpToSegment(item, false)} style={styles.timestampButton}>
              <Text style={styles.timestampText}>{formatTimestamp(segmentStart(item))}</Text>
            </Pressable>
            <Pressable
              onPress={() => toggleSegmentPlayback(item)}
              style={[styles.segmentPlayButton, segmentPlaybackId === item.id && isPlaying ? styles.segmentPlayButtonActive : null]}
            >
              <LucideIcon name={segmentPlaybackId === item.id && isPlaying ? 'pause' : 'play'} color="#111827" size={12} strokeWidth={2.6} />
            </Pressable>
          </View>
          <Text style={styles.paragraph}>{replaceSpeakerLabels(item.text)}</Text>
        </View>
      </View>
    );
  }

  if (loading && !meeting) {
    return (
      <View style={styles.centerState}>
        <ActivityIndicator color={brandBlue} />
        <Text style={styles.centerText}>会议加载中...</Text>
      </View>
    );
  }

  if (error && !meeting) {
    return (
      <View style={styles.centerState}>
        <Text style={styles.error}>{error}</Text>
        <Pressable onPress={loadMeeting} style={styles.retryButton}>
          <Text style={styles.retryText}>重试</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <>
      <View style={styles.page}>
        {error ? <Text style={styles.inlineError}>{error}</Text> : null}
        <FlatList
          ref={listRef}
          data={activeTab === 'transcript' ? transcriptSegments : []}
          keyExtractor={(item) => item.id}
          ListHeaderComponent={renderHeader}
          renderItem={renderSegment}
          contentContainerStyle={styles.listContent}
          initialNumToRender={14}
          maxToRenderPerBatch={12}
          updateCellsBatchingPeriod={80}
          windowSize={8}
          removeClippedSubviews
          onScrollToIndexFailed={({ index }) => {
            setTimeout(() => listRef.current?.scrollToIndex({ index, animated: true, viewPosition: 0.25 }), 350);
          }}
          ListFooterComponent={<View style={styles.safeBottom} />}
        />
      </View>
      <Modal transparent visible={!!editingSpeakerLabel} animationType="fade" onRequestClose={() => setEditingSpeakerLabel(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.speakerModal}>
            <Text style={styles.speakerModalTitle}>编辑说话人名称</Text>
            <Text style={styles.speakerModalSub}>{editingSpeakerLabel ? displaySpeaker(editingSpeakerLabel) : ''}</Text>
            <TextInput
              value={editingSpeakerLabel ? speakerNameDrafts[editingSpeakerLabel] || '' : ''}
              onChangeText={(value) => {
                if (!editingSpeakerLabel) return;
                setSpeakerNameDrafts((current) => ({ ...current, [editingSpeakerLabel]: value }));
              }}
              placeholder="请输入说话人名称"
              placeholderTextColor="#aeb6c5"
              style={styles.speakerModalInput}
            />
            <TextInput
              value={editingSpeakerLabel ? speakerNoteDrafts[editingSpeakerLabel] || '' : ''}
              onChangeText={(value) => {
                if (!editingSpeakerLabel) return;
                setSpeakerNoteDrafts((current) => ({ ...current, [editingSpeakerLabel]: value }));
              }}
              placeholder="备注，如部门、角色、项目职责"
              placeholderTextColor="#aeb6c5"
              multiline
              style={[styles.speakerModalInput, styles.speakerNoteInput]}
            />
            <View style={styles.speakerModalActions}>
              <Pressable onPress={() => setEditingSpeakerLabel(null)} style={[styles.speakerModalButton, styles.speakerModalCancel]}>
                <Text style={styles.speakerModalCancelText}>取消</Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  if (editingSpeakerLabel) saveSpeaker(editingSpeakerLabel);
                }}
                style={[styles.speakerModalButton, styles.speakerModalSave]}
              >
                <Text style={styles.speakerModalSaveText}>{savingSpeaker === editingSpeakerLabel ? '保存中' : '保存'}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <View style={styles.sectionTitleRow}>
      <View style={styles.sectionBar} />
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function ListSection({ title, rows }: { title: string; rows: string[] }) {
  return (
    <View style={styles.summarySection}>
      <Text style={styles.summarySectionTitle}>{title}</Text>
      <NumberedList items={normalizeNumberedListItems(rows)} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: '#EEF3FA',
    flex: 1,
  },
  listContent: {
    paddingBottom: 24,
  },
  topNav: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  iconButton: {
    alignItems: 'center',
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  navTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 16,
    fontWeight: '900',
    textAlign: 'center',
  },
  navActions: {
    flexDirection: 'row',
  },
  sheet: {
    backgroundColor: '#ffffff',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  playerCard: {
    backgroundColor: '#F8FAFD',
    borderColor: '#EEF1F6',
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
  },
  timeRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  timeTextStrong: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '800',
    width: 46,
  },
  timeTextMuted: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '800',
    textAlign: 'right',
    width: 50,
  },
  progressTrack: {
    backgroundColor: '#E5EAF1',
    borderRadius: 999,
    flex: 1,
    height: 6,
  },
  progressFill: {
    backgroundColor: brandBlue,
    borderRadius: 999,
    height: 6,
  },
  progressThumb: {
    backgroundColor: brandBlue,
    borderColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 2,
    height: 16,
    marginLeft: -8,
    position: 'absolute',
    top: -5,
    width: 16,
  },
  controlsRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 26,
    justifyContent: 'center',
    marginTop: 14,
  },
  skipButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#E5EAF1',
    borderRadius: 18,
    borderWidth: 1,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  skipButtonText: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '900',
  },
  playButton: {
    alignItems: 'center',
    backgroundColor: '#111827',
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  tabs: {
    borderBottomColor: '#EEF1F6',
    borderBottomWidth: 1,
    flexDirection: 'row',
    marginTop: 12,
  },
  tabButton: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingVertical: 12,
  },
  tabButtonActive: {
    borderBottomColor: brandBlue,
    borderBottomWidth: 2,
  },
  tabText: {
    color: '#94A3B8',
    fontSize: 15,
    fontWeight: '800',
  },
  tabTextActive: {
    color: brandBlue,
  },
  quickMeta: {
    paddingTop: 12,
  },
  quickMetaText: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
  },
  section: {
    paddingTop: 14,
  },
  sectionTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
    marginBottom: 10,
  },
  sectionBar: {
    backgroundColor: brandBlue,
    borderRadius: 2,
    height: 16,
    width: 4,
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  quickRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 9,
    minHeight: 34,
  },
  quickDot: {
    backgroundColor: '#F59E0B',
    borderRadius: 4,
    height: 8,
    width: 8,
  },
  quickTime: {
    color: brandBlue,
    fontSize: 13,
    fontWeight: '900',
    width: 52,
  },
  quickTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
  },
  exportSection: {
    backgroundColor: '#F8FAFD',
    borderTopColor: '#EEF1F6',
    borderTopWidth: 1,
    marginHorizontal: -18,
    marginTop: 12,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  exportTitle: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '900',
    marginBottom: 8,
  },
  exportRow: {
    flexDirection: 'row',
    gap: 8,
  },
  exportButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#DCE4F0',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    paddingVertical: 8,
  },
  exportButtonDisabled: {
    backgroundColor: '#F1F5F9',
  },
  exportText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '900',
  },
  exportTextDisabled: {
    color: '#94A3B8',
  },
  fallbackTranscript: {
    color: '#374151',
    fontSize: 14,
    lineHeight: 24,
    paddingBottom: 16,
  },
  segmentRow: {
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  segmentRowActive: {
    backgroundColor: '#F4F8FF',
  },
  timelineRail: {
    alignItems: 'center',
    width: 28,
  },
  avatar: {
    alignItems: 'center',
    borderRadius: 13,
    height: 26,
    justifyContent: 'center',
    width: 26,
    zIndex: 1,
  },
  avatarText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '900',
  },
  timelineLine: {
    backgroundColor: '#E5EAF1',
    flex: 1,
    marginTop: 4,
    minHeight: 46,
    width: 1,
  },
  segmentBody: {
    flex: 1,
    gap: 6,
  },
  segmentMetaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  speakerName: {
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 20,
  },
  timestampButton: {
    paddingHorizontal: 2,
  },
  timestampText: {
    color: brandBlue,
    fontSize: 12,
    fontWeight: '800',
  },
  segmentPlayButton: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderRadius: 8,
    height: 18,
    justifyContent: 'center',
    width: 18,
  },
  segmentPlayButtonActive: {
    backgroundColor: '#EEF2FF',
  },
  paragraph: {
    color: '#1F2937',
    fontSize: 14,
    lineHeight: 23,
  },
  empty: {
    color: '#64748B',
    fontSize: 13,
    lineHeight: 22,
    paddingBottom: 12,
  },
  summaryContainer: {
    gap: 14,
    paddingTop: 14,
  },
  agentToolGrid: {
    gap: 12,
  },
  agentToolCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#e5e7eb',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 86,
    padding: 14,
  },
  agentToolCardDisabled: {
    opacity: 0.72,
  },
  agentToolIcon: {
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    borderRadius: 22,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  agentToolIconActive: {
    backgroundColor: '#e8f0fe',
  },
  agentToolText: {
    flex: 1,
    gap: 4,
  },
  agentToolTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  agentToolSub: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
  },
  agentToolStatus: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '800',
  },
  agentEmptyRecord: {
    backgroundColor: '#f8fafc',
    borderColor: '#e5e7eb',
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 14,
    padding: 16,
  },
  agentEmptyTitle: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '900',
  },
  agentEmptyText: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 6,
  },
  agentMoreBox: {
    alignItems: 'center',
    borderColor: '#cbd5e1',
    borderRadius: 16,
    borderStyle: 'dashed',
    borderWidth: 1,
    marginTop: 12,
    padding: 16,
  },
  agentMoreText: {
    color: '#64748B',
    fontSize: 13,
    fontWeight: '900',
  },
  summaryCoverCard: {
    backgroundColor: '#ffffff',
    borderColor: '#E8EEF7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 14,
    padding: 16,
    shadowColor: '#8AA0C1',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
  },
  summaryCoverTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
  },
  summaryCoverText: {
    flex: 1,
    gap: 7,
  },
  summaryCoverTitle: {
    color: '#0F172A',
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 26,
  },
  summaryCoverMeta: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 18,
  },
  summaryExportBlock: {
    borderTopColor: '#EEF2F7',
    borderTopWidth: 1,
    gap: 10,
    paddingTop: 12,
  },
  summaryExportTitle: {
    color: '#64748B',
    fontSize: 13,
    fontWeight: '800',
  },
  summaryExportButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#DCE4F0',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    minHeight: 34,
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  summaryExportButtonDisabled: {
    backgroundColor: '#F6F8FB',
  },
  summaryExportText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '900',
  },
  summaryHero: {
    backgroundColor: '#F8FAFD',
    borderColor: '#EEF1F6',
    borderRadius: 16,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  summaryHeroHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  summaryHeroTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  statusPill: {
    backgroundColor: '#ECFDF3',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  statusPillText: {
    color: '#16A34A',
    fontSize: 12,
    fontWeight: '900',
  },
  sourceHintText: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
  },
  summaryLead: {
    color: '#374151',
    fontSize: 14,
    lineHeight: 24,
  },
  summarySection: {
    backgroundColor: '#ffffff',
    borderColor: '#E8EEF7',
    borderRadius: 16,
    borderWidth: 1,
    gap: 12,
    padding: 16,
    shadowColor: '#8AA0C1',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 10,
  },
  summarySectionTitle: {
    color: '#0F172A',
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 22,
  },
  basicInfoList: {
    gap: 10,
  },
  basicInfoRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  basicInfoLabel: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 22,
    width: 48,
  },
  basicInfoValue: {
    color: '#475569',
    flex: 1,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 22,
  },
  stateCard: {
    alignItems: 'center',
    backgroundColor: '#F4F8FF',
    borderColor: '#DCE8FF',
    borderRadius: 16,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  stateCardFailed: {
    backgroundColor: '#FEF2F2',
    borderColor: '#FECACA',
    borderRadius: 16,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  stateTitle: {
    color: '#1D4ED8',
    fontSize: 15,
    fontWeight: '900',
  },
  stateTitleFailed: {
    color: '#DC2626',
    fontSize: 15,
    fontWeight: '900',
  },
  stateText: {
    color: '#64748B',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 21,
    textAlign: 'center',
  },
  bulletList: {
    gap: 12,
  },
  bulletItem: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  bulletDot: {
    backgroundColor: '#94A3B8',
    borderRadius: 4,
    height: 7,
    marginTop: 8,
    width: 7,
  },
  bulletBody: {
    flex: 1,
    gap: 8,
  },
  bulletText: {
    color: '#334155',
    flex: 1,
    fontSize: 14,
    lineHeight: 23,
  },
  evidenceBox: {
    backgroundColor: '#F8FAFD',
    borderColor: '#E8EEF7',
    borderRadius: 12,
    borderWidth: 1,
    gap: 6,
    padding: 10,
  },
  evidenceHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  evidenceLabel: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '900',
  },
  evidenceTimeButton: {
    backgroundColor: '#EAF1FF',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  evidenceTimeText: {
    color: brandBlue,
    fontSize: 11,
    fontWeight: '900',
  },
  evidenceText: {
    color: '#64748B',
    fontSize: 12,
    lineHeight: 20,
  },
  actionList: {
    gap: 14,
  },
  actionItem: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  readonlyCheckbox: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#CBD5E1',
    borderRadius: 6,
    borderWidth: 2,
    height: 22,
    justifyContent: 'center',
    marginTop: 1,
    width: 22,
  },
  readonlyCheckboxDone: {
    backgroundColor: '#EAF1FF',
    borderColor: brandBlue,
  },
  actionBody: {
    flex: 1,
    gap: 6,
  },
  actionText: {
    color: '#334155',
    fontSize: 14,
    fontWeight: '800',
    lineHeight: 23,
  },
  actionTextDone: {
    color: '#94A3B8',
    textDecorationLine: 'line-through',
  },
  actionMeta: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 20,
  },
  inlineError: {
    backgroundColor: '#FEF2F2',
    color: '#DC2626',
    fontSize: 12,
    fontWeight: '800',
    paddingHorizontal: 18,
    paddingVertical: 8,
  },
  centerState: {
    alignItems: 'center',
    backgroundColor: '#EEF3FA',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  centerText: {
    color: '#64748B',
    fontSize: 13,
    fontWeight: '800',
    marginTop: 10,
  },
  retryButton: {
    backgroundColor: brandBlue,
    borderRadius: 12,
    marginTop: 14,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  retryText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '900',
  },
  error: {
    color: '#DC2626',
    fontSize: 13,
    lineHeight: 22,
    textAlign: 'center',
  },
  modalOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.35)',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  speakerModal: {
    backgroundColor: '#ffffff',
    borderRadius: 20,
    padding: 18,
    width: '100%',
  },
  speakerModalTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  speakerModalSub: {
    color: '#64748B',
    fontSize: 12,
    fontWeight: '800',
    marginTop: 6,
  },
  speakerModalInput: {
    backgroundColor: '#F8FAFD',
    borderColor: '#E2E8F0',
    borderRadius: 12,
    borderWidth: 1,
    color: '#111827',
    fontSize: 15,
    fontWeight: '700',
    marginTop: 12,
    minHeight: 46,
    paddingHorizontal: 12,
  },
  speakerNoteInput: {
    minHeight: 72,
    paddingTop: 10,
    textAlignVertical: 'top',
  },
  speakerModalActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  speakerModalButton: {
    alignItems: 'center',
    borderRadius: 12,
    flex: 1,
    justifyContent: 'center',
    minHeight: 44,
  },
  speakerModalCancel: {
    backgroundColor: '#F1F5F9',
  },
  speakerModalSave: {
    backgroundColor: brandBlue,
  },
  speakerModalCancelText: {
    color: '#475569',
    fontSize: 14,
    fontWeight: '900',
  },
  speakerModalSaveText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '900',
  },
  safeBottom: {
    height: 28,
  },
});
