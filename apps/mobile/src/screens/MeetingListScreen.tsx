import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  PanResponder,
  Pressable,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { bulkDeleteMeetings, deleteMeeting, getMeetingSummary, listMeetings, Meeting, MeetingSummary } from '../api';
import { LucideIcon } from '../components/LucideIcon';
import { groupMeetingsByDate } from '../utils/meetingDateSections';

type Props = {
  mode?: 'home' | 'all';
  activeRecordingMeetingId?: string | null;
  processingRecordingMeeting?: Meeting | null;
  refreshKey?: number;
  miniRecordingVisible?: boolean;
  creatingMeeting?: boolean;
  onCreateMeeting: () => void;
  onImportFile?: () => void;
  onOpenMeeting: (meetingId: string) => void;
  onShowAll?: () => void;
  onMeetingCountChange?: (count: number) => void;
};

type DisplayStatus = 'recording' | 'analyzing' | 'uploaded' | 'completed' | 'pending' | 'failed';

type SummaryByMeeting = Record<string, MeetingSummary | null>;
const HOME_MEETING_LIMIT = 10;
const HISTORY_PAGE_SIZE = 30;

const statusText: Record<DisplayStatus, string> = {
  recording: '录音中',
  analyzing: '分析中',
  uploaded: '已上传',
  completed: '已完成',
  pending: '待录音',
  failed: '失败',
};

const statusDisplayText: Record<DisplayStatus, string> = {
  recording: '处理中',
  analyzing: '处理中',
  uploaded: '未生成摘要',
  completed: '已完成',
  pending: '未生成摘要',
  failed: '分析失败',
};

function normalizeStatus(status: string): DisplayStatus {
  if (status === 'completed') return 'completed';
  if (['processing', 'transcribing', 'transcribed', 'summarizing'].includes(status)) {
    return 'analyzing';
  }
  if (status === 'audio_uploaded' || status === 'uploaded') return 'uploaded';
  if (status === 'recording') return 'recording';
  if (status.includes('failed') || status === 'failed') return 'failed';
  return 'pending';
}

function isAnalyzingMeeting(meeting: Meeting): boolean {
  return normalizeStatus(meeting.status) === 'analyzing';
}

function twoDigits(value: number): string {
  return String(value).padStart(2, '0');
}

function formatRecentMeetingDate(date: Date | null): string {
  if (!date) return '';
  const now = new Date();
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const target = new Date(date);
  target.setHours(0, 0, 0, 0);
  const dayDiff = Math.round((today.getTime() - target.getTime()) / 86400000);
  const time = `${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())}`;
  if (dayDiff === 0) return `今天 ${time}`;
  if (dayDiff === 1) return `昨天 ${time}`;
  return `${twoDigits(date.getMonth() + 1)}-${twoDigits(date.getDate())} ${time}`;
}

function parsedDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function meetingDurationSeconds(meeting: Meeting): number {
  const end = parsedDate(meeting.end_at);
  const start = parsedDate(meeting.start_at) || parsedDate(meeting.created_at);
  if (!start || !end || end <= start) return 0;
  return Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return '未计算';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours && minutes) return `${hours}小时${minutes}分`;
  if (hours) return `${hours}小时`;
  if (minutes && rest) return `${minutes}分${rest}秒`;
  if (minutes) return `${minutes}分`;
  return `${rest}秒`;
}

function meetingDurationText(meeting: Meeting, status: DisplayStatus): string {
  const seconds = meetingDurationSeconds(meeting);
  if (seconds > 0) return formatDuration(seconds);
  if (status === 'pending') return '待录音';
  if (status === 'recording') return '进行中';
  if (status === 'analyzing') return '处理中';
  if (status === 'uploaded') return '待处理';
  if (status === 'failed') return '未完成';
  return '未计算';
}

function analysisRemainingText(meeting: Meeting): string {
  const analysisStartedAt = parsedDate(meeting.updated_at) || parsedDate(meeting.created_at);
  if (!analysisStartedAt) return '2-5 分钟';

  const estimatedTotalSeconds = 5 * 60;
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - analysisStartedAt.getTime()) / 1000));
  const remainingSeconds = Math.max(0, estimatedTotalSeconds - elapsedSeconds);

  if (remainingSeconds <= 0) return '即将完成';
  if (remainingSeconds < 60) return '1 分钟内';
  return `${Math.ceil(remainingSeconds / 60)} 分钟`;
}

function itemCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function textFromSummaryItem(item: unknown): string {
  if (typeof item === 'string') return item.trim();
  if (!item || typeof item !== 'object') return '';
  const record = item as Record<string, unknown>;
  const candidates = [
    record.item,
    record.title,
    record.summary,
    record.content,
    record.topic,
    record.text,
    record.conclusion,
    record.decision,
    record.task,
    record.issue,
    record.risk,
    record.source_text,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
  }
  return '';
}

function firstSummaryText(primary: unknown, legacy?: unknown): string {
  const primaryItems = Array.isArray(primary) ? primary : [];
  const legacyItems = Array.isArray(legacy) ? legacy : [];
  for (const item of [...primaryItems, ...legacyItems]) {
    const text = textFromSummaryItem(item);
    if (text) return text;
  }
  return '';
}

function summaryPreviewText(summary: MeetingSummary | null | undefined): string {
  const candidates = [summary?.meeting_summary, summary?.overview];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim();
  }
  return '';
}

function isHighPriority(value: { priority?: string | null }): boolean {
  return value.priority === 'high' || value.priority === '高' || value.priority === '高优先级';
}

function participantCount(summary: MeetingSummary | null | undefined): number {
  if (Array.isArray(summary?.speaker_summaries) && summary.speaker_summaries.length > 0) {
    return summary.speaker_summaries.length;
  }
  const metadataParticipants = summary?.metadata?.participants;
  if (Array.isArray(metadataParticipants)) return metadataParticipants.length;
  if (typeof metadataParticipants === 'number') return metadataParticipants;
  return 0;
}

function aiSummaryText(status: DisplayStatus, summary: MeetingSummary | null | undefined): string {
  if (status === 'completed') return summary ? 'AI摘要已生成' : 'AI摘要待同步';
  if (status === 'analyzing') return 'AI摘要生成中';
  if (status === 'uploaded') return 'AI摘要待生成';
  if (status === 'failed') return 'AI摘要生成失败';
  if (status === 'recording') return '录音完成后生成摘要';
  return '开始录音后生成摘要';
}

function StatusBadge({ status, label }: { status: DisplayStatus; label: string }) {
  const processing = status === 'analyzing' || status === 'recording';
  return (
    <View style={[styles.statusBadge, styles[`${status}Badge`]]}>
      {processing ? <ActivityIndicator color="#6657ff" size="small" style={styles.statusSpinner} /> : null}
      <Text style={[styles.statusText, styles[`${status}Text`]]}>{label}</Text>
    </View>
  );
}

function MeetingCard({
  item,
  onPress,
  selectable = false,
  selected = false,
  onToggleSelect,
  summary,
  isActiveRecording = false,
  compactHome = false,
  flushBottom = false,
}: {
  item: Meeting;
  onPress: () => void;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  summary?: MeetingSummary | null;
  isActiveRecording?: boolean;
  compactHome?: boolean;
  flushBottom?: boolean;
}) {
  const status = isActiveRecording ? 'recording' : normalizeStatus(item.status);
  const duration = meetingDurationText(item, status);
  const actions = itemCount(summary?.action_items);
  const conclusions = itemCount(summary?.key_conclusions || summary?.decisions);
  const risks = itemCount(summary?.risks_and_focus || summary?.risks);
  const highPriority = Array.isArray(summary?.action_items) ? summary.action_items.filter(isHighPriority).length : 0;
  const people = participantCount(summary);
  const remainingAnalysisTime = analysisRemainingText(item);
  const metaParts = [formatRecentMeetingDate(parsedDate(item.start_at) || parsedDate(item.created_at)), duration];
  if (people > 0) metaParts.push(`${people}人`);
  const title = item.title?.trim() && item.title.trim().length >= 2 ? item.title.trim() : '未命名会议';
  const summaryText = aiSummaryText(status, summary);
  const meetingSummaryPreview = summaryPreviewText(summary);
  const agendaPreview = firstSummaryText(summary?.meeting_agenda, summary?.agenda);
  const conclusionPreview = firstSummaryText(summary?.key_conclusions, summary?.decisions);
  const actionPreview = firstSummaryText(summary?.action_items, summary?.next_steps);
  const previewRows = [
    { label: '会议总结：', text: meetingSummaryPreview },
    { label: '会议议程：', text: agendaPreview },
    { label: '核心结论：', text: conclusionPreview },
    { label: '待办事项：', text: actionPreview },
  ].filter((row) => row.text.trim().length > 0);
  const hasCompletedPreview = status === 'completed' && previewRows.length > 0;
  const statsRow = (
    <View style={styles.cardStatsRow}>
      <View style={styles.cardStatItem}>
        <Text style={styles.cardStatText}>{conclusions} 项结论</Text>
      </View>
      <Text style={styles.cardStatDivider}>|</Text>
      <View style={styles.cardStatItem}>
        <Text style={styles.cardStatText}>{actions} 项待办{highPriority ? `（${highPriority} 高优）` : ''}</Text>
      </View>
      <Text style={styles.cardStatDivider}>|</Text>
      <View style={styles.cardStatItem}>
        <Text style={styles.cardStatText}>{risks} 项风险</Text>
      </View>
    </View>
  );

  if (compactHome) {
    const showHomeStatusBadge = status !== 'pending';
    return (
      <Pressable onPress={onPress} style={[styles.homeMeetingCard, flushBottom ? styles.cardFlushBottom : null]}>
        <View style={styles.homeMeetingTop}>
          {selectable ? (
            <Pressable onPress={onToggleSelect} hitSlop={8} style={[styles.selectBox, selected ? styles.selectBoxActive : null]}>
              <Text style={[styles.selectCheck, selected ? styles.selectCheckActive : null]}>✓</Text>
            </Pressable>
          ) : null}
          <Text numberOfLines={2} style={styles.homeMeetingTitle}>
            {title}
          </Text>
          {showHomeStatusBadge ? <StatusBadge status={status} label={statusDisplayText[status]} /> : null}
        </View>
        <View style={styles.homeMeetingMetaRow}>
          <LucideIcon name="clock-3" color="#8b95a7" size={14} strokeWidth={2.2} />
          <Text numberOfLines={1} style={styles.homeMeetingMeta}>{metaParts.filter(Boolean).join(' · ')}</Text>
        </View>
        {hasCompletedPreview ? (
          <View style={styles.homePreviewBlock}>
            {previewRows.map((row) => (
              <View key={row.label} style={styles.previewRow}>
                <Text style={styles.previewLabel}>{row.label}</Text>
                <Text numberOfLines={1} style={styles.previewText}>{row.text}</Text>
              </View>
            ))}
          </View>
        ) : status === 'analyzing' || status === 'recording' ? (
          <View style={styles.homeAnalyzingBlock}>
            <Text style={styles.analysisHint}>AI 正在分析会议内容</Text>
            <Text style={styles.stageHint}>提取结论 · 生成待办 · 识别风险 · 预计还需 {remainingAnalysisTime}</Text>
          </View>
        ) : status === 'failed' ? (
          <View style={styles.homeFailedBlock}>
            <Text style={styles.failedHint}>分析失败，可进入会议详情查看或稍后重试。</Text>
          </View>
        ) : status === 'uploaded' || status === 'pending' ? (
          <Text style={styles.homePendingHint}>暂无 AI 摘要，完成录音或上传后可生成。</Text>
        ) : null}
        <View style={styles.homeMeetingFooter}>
          <View style={styles.summaryState}>
            <LucideIcon name="sparkles" color={status === 'failed' ? '#ef4444' : '#2B6CFF'} size={15} strokeWidth={2.2} />
            <Text
              numberOfLines={1}
              style={[styles.summaryStateText, status === 'failed' ? styles.summaryStateTextFailed : null]}
            >
              {summaryText}
            </Text>
            <LucideIcon name="chevron-right" color={status === 'failed' ? '#ef4444' : '#2B6CFF'} size={15} strokeWidth={2.2} />
          </View>
          {status === 'completed' && actions > 0 ? (
            <View style={[styles.actionCountBadge, styles.actionCountBadgeActive]}>
              <Text style={[styles.actionCountText, styles.actionCountTextActive]}>{actions}项待办</Text>
            </View>
          ) : null}
        </View>
      </Pressable>
    );
  }

  return (
    <Pressable onPress={onPress} style={styles.card}>
      {selectable ? (
        <Pressable onPress={onToggleSelect} hitSlop={8} style={[styles.selectBox, selected ? styles.selectBoxActive : null]}>
          <Text style={[styles.selectCheck, selected ? styles.selectCheckActive : null]}>✓</Text>
        </Pressable>
      ) : null}
      <View style={styles.cardBody}>
        <View style={styles.cardTitleRow}>
          <Text numberOfLines={1} style={styles.cardTitle}>
            {title}
          </Text>
          <View style={styles.cardRight}>
            <StatusBadge status={status} label={statusText[status]} />
            <LucideIcon name="chevron-right" color="#9ca3af" size={19} strokeWidth={2.2} />
          </View>
        </View>
        <Text style={styles.cardMeta}>{metaParts.filter(Boolean).join(' · ')}</Text>
        {status === 'analyzing' ? (
          <View style={styles.analyzingBlock}>
            <Text style={styles.analysisHint}>AI 正在分析会议内容</Text>
            <Text style={styles.stageHint}>提取结论 · 生成待办 · 识别风险</Text>
            <View style={styles.progressTip}>
              <View style={styles.progressTipLeft}>
                <LucideIcon name="sparkles" color="#6657ff" size={16} strokeWidth={2.1} />
                <Text style={styles.progressTipText}>AI 已开始分析，预计还需 {remainingAnalysisTime}</Text>
              </View>
              <Text style={styles.progressLink}>查看进度</Text>
              <LucideIcon name="chevron-right" color="#6657ff" size={16} strokeWidth={2.2} />
            </View>
          </View>
        ) : status === 'pending' ? (
          <>
            <Text style={styles.pendingHint}>等待开始录音</Text>
            {statsRow}
          </>
        ) : (
          statsRow
        )}
      </View>
    </Pressable>
  );
}

function SwipeableMeetingCard({ children, onDelete }: { children: ReactNode; onDelete: () => void }) {
  const translateX = useRef(new Animated.Value(0)).current;
  const offsetX = useRef(0);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 8 && Math.abs(gesture.dx) > Math.abs(gesture.dy),
      onPanResponderGrant: () => {
        translateX.setOffset(offsetX.current);
        translateX.setValue(0);
      },
      onPanResponderMove: (_, gesture) => {
        translateX.setValue(Math.max(-88, Math.min(0, gesture.dx)));
      },
      onPanResponderRelease: (_, gesture) => {
        translateX.flattenOffset();
        const nextOffset = offsetX.current + gesture.dx < -44 ? -88 : 0;
        offsetX.current = nextOffset;
        Animated.spring(translateX, {
          toValue: nextOffset,
          useNativeDriver: true,
          bounciness: 0,
          speed: 18,
        }).start();
      },
    }),
  ).current;

  return (
    <View style={styles.swipeRow}>
      <Pressable onPress={onDelete} style={styles.swipeDelete}>
        <Text style={styles.swipeDeleteText}>删除</Text>
      </Pressable>
      <Animated.View {...panResponder.panHandlers} style={{ transform: [{ translateX }] }}>
        {children}
      </Animated.View>
    </View>
  );
}

export function MeetingListScreen({
  mode = 'home',
  activeRecordingMeetingId,
  processingRecordingMeeting,
  refreshKey = 0,
  miniRecordingVisible = false,
  creatingMeeting = false,
  onCreateMeeting,
  onImportFile,
  onOpenMeeting,
  onShowAll,
  onMeetingCountChange,
}: Props) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [summaryByMeeting, setSummaryByMeeting] = useState<SummaryByMeeting>({});
  const [hasMoreMeetings, setHasMoreMeetings] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sectionClock, setSectionClock] = useState(() => new Date());

  const loadMeetings = useCallback(async (append = false, offset = 0) => {
    try {
      setError(null);
      const limit = mode === 'home' ? HOME_MEETING_LIMIT : HISTORY_PAGE_SIZE;
      const data = await listMeetings({ limit, offset });
      setMeetings((current) => (append ? [...current, ...data] : data));
      setHasMoreMeetings(mode === 'all' && data.length === limit);
      if (!append) {
        setSelectedIds((current) => current.filter((id) => data.some((meeting) => meeting.id === id)));
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '会议列表加载失败。');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [mode]);

  useEffect(() => {
    setLoading(true);
    setMeetings([]);
    setHasMoreMeetings(false);
    setSelectedIds([]);
    loadMeetings(false);
  }, [loadMeetings, refreshKey]);

  useEffect(() => {
    if (mode === 'all') {
      onMeetingCountChange?.(meetings.length);
    }
  }, [meetings.length, mode, onMeetingCountChange]);

  useEffect(() => {
    const now = new Date();
    const nextMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
    const timer = setTimeout(() => setSectionClock(new Date()), Math.max(1000, nextMidnight.getTime() - now.getTime()));
    return () => clearTimeout(timer);
  }, [sectionClock]);

  function refresh() {
    setRefreshing(true);
    loadMeetings(false);
  }

  function loadMoreMeetings() {
    if (mode !== 'all' || loading || loadingMore || !hasMoreMeetings) return;
    setLoadingMore(true);
    loadMeetings(true, meetings.length);
  }

  function handleOpenMeeting(meeting: Meeting) {
    if (isAnalyzingMeeting(meeting)) {
      Alert.alert('提示', 'AI正在分析中，请稍等');
      return;
    }

    onOpenMeeting(meeting.id);
  }

  const visibleMeetings = useMemo(() => {
    const mergedMeetings = processingRecordingMeeting
      ? meetings.map((meeting) =>
          meeting.id === processingRecordingMeeting.id ? { ...meeting, ...processingRecordingMeeting, status: 'processing' } : meeting,
        )
      : meetings;
    const hasProcessingMeeting =
      Boolean(processingRecordingMeeting) && mergedMeetings.some((meeting) => meeting.id === processingRecordingMeeting?.id);
    const nextMeetings =
      processingRecordingMeeting && !hasProcessingMeeting
        ? [{ ...processingRecordingMeeting, status: 'processing' }, ...mergedMeetings]
        : mergedMeetings;
    return mode === 'home' ? nextMeetings.slice(0, HOME_MEETING_LIMIT) : nextMeetings;
  }, [meetings, mode, processingRecordingMeeting]);
  const meetingSections = useMemo(() => groupMeetingsByDate(visibleMeetings, sectionClock), [sectionClock, visibleMeetings]);
  useEffect(() => {
    if (visibleMeetings.length === 0) {
      return;
    }

    let cancelled = false;
    const meetingsForStats = visibleMeetings
      .filter((meeting) => normalizeStatus(meeting.status) === 'completed')
      .slice(0, mode === 'home' ? HOME_MEETING_LIMIT : HISTORY_PAGE_SIZE)
      .filter((meeting) => !(meeting.id in summaryByMeeting));

    if (meetingsForStats.length === 0) {
      return;
    }

    async function loadSummaries() {
      const results = await Promise.allSettled(
        meetingsForStats.map(async (meeting) => [meeting.id, await getMeetingSummary(meeting.id)] as const),
      );
      if (cancelled) return;

      const next: SummaryByMeeting = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          next[result.value[0]] = result.value[1];
        } else {
          next[meetingsForStats[index].id] = null;
        }
      });
      setSummaryByMeeting((current) => ({ ...current, ...next }));
    }

    loadSummaries().catch(() => {
      if (!cancelled) {
        const failed: SummaryByMeeting = {};
        meetingsForStats.forEach((meeting) => {
          failed[meeting.id] = null;
        });
        setSummaryByMeeting((current) => ({ ...current, ...failed }));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [mode, summaryByMeeting, visibleMeetings]);

  function handleImportFile() {
    if (onImportFile) {
      onImportFile();
      return;
    }
    Alert.alert('提示', '文件导入功能暂不可用');
  }

  function toggleSelected(meetingId: string) {
    setSelectedIds((current) =>
      current.includes(meetingId) ? current.filter((id) => id !== meetingId) : [...current, meetingId],
    );
  }

  function toggleSelectAll() {
    if (selectedIds.length === visibleMeetings.length) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(visibleMeetings.map((meeting) => meeting.id));
  }

  function confirmDeleteSelected() {
    if (!selectedIds.length) {
      setError('请选择要删除的会议。');
      return;
    }
    Alert.alert('批量删除会议？', `确定删除选中的 ${selectedIds.length} 场会议吗？删除后无法恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            setError(null);
            await bulkDeleteMeetings(selectedIds);
            setSelectedIds([]);
            setSelecting(false);
            await loadMeetings();
          } catch (nextError) {
            setError(nextError instanceof Error ? nextError.message : '批量删除会议失败。');
          }
        },
      },
    ]);
  }

  function confirmDeleteMeeting(meetingId: string) {
    Alert.alert('删除会议？', '确定删除这场会议吗？删除后无法恢复。', [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            setError(null);
            await deleteMeeting(meetingId);
            await loadMeetings();
          } catch (nextError) {
            setError(nextError instanceof Error ? nextError.message : '删除会议失败。');
          }
        },
      },
    ]);
  }

  if (mode === 'all') {
    return (
      <View style={[styles.container, styles.historyContainer]}>
        <View style={styles.historyHeader}>
          <View />
          <Pressable
            onPress={() => {
              setSelecting((value) => !value);
              setSelectedIds([]);
            }}
            style={styles.selectToggle}
          >
            <Text style={styles.selectToggleText}>{selecting ? '取消' : '选择'}</Text>
          </Pressable>
        </View>
        {selecting ? (
          <View style={styles.batchBar}>
            <Pressable onPress={toggleSelectAll} style={styles.batchButton}>
              <Text style={styles.batchText}>{selectedIds.length === visibleMeetings.length ? '取消全选' : '全选'}</Text>
            </Pressable>
            <Pressable onPress={confirmDeleteSelected} style={[styles.batchButton, styles.batchDeleteButton]}>
              <Text style={styles.batchDeleteText}>删除所选（{selectedIds.length}）</Text>
            </Pressable>
          </View>
        ) : null}
        {loading ? <ActivityIndicator color="#6657ff" /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <SectionList
          sections={meetingSections}
          keyExtractor={(item) => item.id}
          contentContainerStyle={[styles.historyListContent, miniRecordingVisible ? styles.recentListContentWithMiniRecording : null]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor="#6657ff" />}
          ListEmptyComponent={!loading ? <Text style={styles.empty}>暂无历史会议。</Text> : null}
          onEndReached={loadMoreMeetings}
          onEndReachedThreshold={0.3}
          renderSectionHeader={({ section }) => <Text style={[styles.meetingDateHeader, styles.historyDateHeader]}>{section.title}</Text>}
          ListFooterComponent={
            hasMoreMeetings ? (
              <Pressable onPress={loadMoreMeetings} disabled={loadingMore} style={styles.loadMoreButton}>
                {loadingMore ? <ActivityIndicator color="#6657ff" /> : <Text style={styles.loadMoreText}>加载更多</Text>}
              </Pressable>
            ) : null
          }
          renderItem={({ item }) => {
            const card = (
              <MeetingCard
                item={item}
                summary={summaryByMeeting[item.id]}
                selectable={selecting}
                selected={selectedIds.includes(item.id)}
                onToggleSelect={() => toggleSelected(item.id)}
                isActiveRecording={item.id === activeRecordingMeetingId}
                compactHome={true}
                flushBottom={!selecting}
                onPress={() => (selecting ? toggleSelected(item.id) : handleOpenMeeting(item))}
              />
            );

            if (selecting) return card;
            return <SwipeableMeetingCard onDelete={() => confirmDeleteMeeting(item.id)}>{card}</SwipeableMeetingCard>;
          }}
        />
      </View>
    );
  }

  return (
    <SectionList
      style={styles.container}
      sections={meetingSections}
      keyExtractor={(item) => item.id}
      contentContainerStyle={[styles.homeListContent, miniRecordingVisible ? styles.homeListContentWithMiniRecording : null]}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor="#6657ff" />}
      ListHeaderComponent={
        <>
          <View style={styles.brandRow}>
            <View style={styles.brandLeft}>
              <View style={styles.logo}>
                <View style={styles.logoWave}>
                  {[12, 22, 30, 22, 12].map((height, index) => (
                    <View key={index} style={[styles.logoBar, { height }]} />
                  ))}
                </View>
              </View>
              <View style={styles.brandText}>
                <Text style={styles.brandTitle}>MeetMind AI</Text>
                <Text style={styles.brandSub}>AI会议记录助手</Text>
              </View>
            </View>
            <Pressable onPress={onShowAll} style={styles.searchButton}>
              <LucideIcon name="search" color="#4b5563" size={20} strokeWidth={2.2} />
            </Pressable>
          </View>

          <View style={styles.actionGrid}>
            <Pressable disabled={creatingMeeting} onPress={onCreateMeeting} style={[styles.actionCard, styles.recordActionCard, creatingMeeting ? styles.actionCardDisabled : null]}>
              <View style={styles.actionTitleRow}>
                {creatingMeeting ? <ActivityIndicator color="#ffffff" size="small" /> : <LucideIcon name="mic" color="#ffffff" size={21} strokeWidth={2.3} />}
                <Text style={styles.recordActionTitle}>{creatingMeeting ? '创建中' : '实时录音'}</Text>
              </View>
              <Text style={styles.recordActionSub}>点击开始记录会议</Text>
            </Pressable>
            <Pressable onPress={handleImportFile} style={[styles.actionCard, styles.importActionCard]}>
              <View style={styles.actionTitleRow}>
                <LucideIcon name="file-text" color="#2B6CFF" size={21} strokeWidth={2.3} />
                <Text style={styles.importActionTitle}>导入音频</Text>
              </View>
              <Text style={styles.importActionSub}>支持音频上传</Text>
            </Pressable>
          </View>

          <View style={styles.recentHeader}>
            <View>
              <Text style={styles.sectionTitle}>全部会议</Text>
            </View>
            <Pressable onPress={onShowAll}>
              <Text style={styles.allText}>更多</Text>
            </Pressable>
          </View>

          {loading ? <ActivityIndicator color="#6657ff" /> : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}
        </>
      }
      ListEmptyComponent={!loading ? <Text style={styles.empty}>暂无会议，点击上方按钮开始记录。</Text> : null}
      renderSectionHeader={({ section }) => <Text style={styles.meetingDateHeader}>{section.title}</Text>}
      renderItem={({ item }) => (
        <MeetingCard
          item={item}
          summary={summaryByMeeting[item.id]}
          isActiveRecording={item.id === activeRecordingMeetingId}
          compactHome={true}
          onPress={() => handleOpenMeeting(item)}
        />
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  historyContainer: {
    paddingTop: 0,
  },
  homeListContent: {
    paddingBottom: 132,
  },
  homeListContentWithMiniRecording: {
    paddingBottom: 220,
  },
  brandRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 22,
    marginTop: 6,
  },
  brandLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 12,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: '#2B6CFF',
    borderRadius: 22,
    height: 44,
    justifyContent: 'center',
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.22,
    shadowRadius: 18,
    width: 44,
    elevation: 5,
  },
  logoText: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '900',
  },
  logoWave: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 3,
  },
  logoBar: {
    backgroundColor: '#ffffff',
    borderRadius: 999,
    width: 3,
  },
  brandText: {
    flex: 1,
    gap: 3,
  },
  brandTitle: {
    color: '#111827',
    fontSize: 19,
    fontWeight: '900',
  },
  brandSub: {
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'left',
  },
  searchButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 18,
    borderWidth: 1,
    height: 38,
    justifyContent: 'center',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    width: 38,
    elevation: 2,
  },
  actionGrid: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 14,
  },
  actionCard: {
    alignItems: 'center',
    borderRadius: 18,
    flex: 1,
    height: 66,
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  actionCardDisabled: {
    opacity: 0.72,
  },
  recordActionCard: {
    backgroundColor: '#2B6CFF',
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 4,
  },
  importActionCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderWidth: 1,
    position: 'relative',
  },
  actionTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginBottom: 3,
  },
  recordActionTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
  },
  recordActionSub: {
    color: 'rgba(255,255,255,0.78)',
    fontSize: 10.5,
    fontWeight: '800',
  },
  importActionTitle: {
    color: '#2B6CFF',
    fontSize: 14,
    fontWeight: '900',
  },
  importActionSub: {
    color: '#9ca3af',
    fontSize: 10.5,
    fontWeight: '800',
  },
  heroCard: {
    backgroundColor: '#6657ff',
    borderRadius: 22,
    elevation: 5,
    height: 142,
    marginBottom: 14,
    overflow: 'hidden',
    padding: 14,
    position: 'relative',
    shadowOffset: { width: 0, height: 8 },
    shadowColor: '#6657ff',
    shadowOpacity: 0.2,
    shadowRadius: 22,
  },
  heroContent: {
    height: '100%',
    position: 'relative',
  },
  heroCopy: {
    height: '100%',
    justifyContent: 'flex-start',
    width: '68%',
    zIndex: 2,
  },
  heroTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
  },
  heroIcon: {
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.16)',
    borderRadius: 26,
    borderColor: 'rgba(255, 255, 255, 0.24)',
    borderWidth: 1,
    height: 52,
    justifyContent: 'center',
    width: 52,
  },
  heroTextBlock: {
    flex: 1,
  },
  heroTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '900',
  },
  heroSub: {
    color: '#dcd8ff',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
    textAlign: 'left',
  },
  createButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 16,
    bottom: 0,
    elevation: 6,
    left: 0,
    minHeight: 47,
    justifyContent: 'center',
    position: 'absolute',
    right: 0,
    zIndex: 10,
  },
  createText: {
    color: '#6657ff',
    fontSize: 17,
    fontWeight: '900',
  },
  insightSection: {
    marginBottom: 12,
    marginTop: 1,
  },
  dashboardTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  moreInsightText: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '900',
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  metricTile: {
    backgroundColor: '#ffffff',
    borderColor: '#f2f3f7',
    borderWidth: 1,
    borderRadius: 14,
    minHeight: 98,
    paddingHorizontal: 12,
    paddingVertical: 12,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    width: '48%',
    elevation: 2,
  },
  purpleMetric: {
    backgroundColor: '#f4f2ff',
  },
  blueMetric: {
    backgroundColor: '#eef8ff',
  },
  greenMetric: {
    backgroundColor: '#edfbf3',
  },
  orangeMetric: {
    backgroundColor: '#fff4e8',
  },
  metricValueRow: {
    alignItems: 'flex-end',
    flexDirection: 'row',
    gap: 3,
  },
  metricValue: {
    color: '#111827',
    fontSize: 23,
    fontWeight: '900',
  },
  metricUnit: {
    color: '#111827',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 4,
  },
  metricLabel: {
    color: '#6b7280',
    fontSize: 11.5,
    fontWeight: '800',
    marginTop: 5,
  },
  metricDetail: {
    color: '#7b8496',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 16,
    marginTop: 10,
  },
  positiveDetail: {
    color: '#16a34a',
  },
  metricPill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    marginTop: 10,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  greenMetricPill: {
    backgroundColor: '#dff8ea',
  },
  orangeMetricPill: {
    backgroundColor: '#ffdfbd',
  },
  purpleMetricPill: {
    backgroundColor: '#ebe7ff',
  },
  blueMetricPill: {
    backgroundColor: '#dff2ff',
  },
  metricPillText: {
    fontSize: 10.5,
    fontWeight: '900',
  },
  greenMetricPillText: {
    color: '#16a34a',
  },
  orangeMetricPillText: {
    color: '#f97316',
  },
  purpleMetricPillText: {
    color: '#6657ff',
  },
  blueMetricPillText: {
    color: '#0284c7',
  },
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  recentHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
    marginTop: 2,
  },
  recentListContent: {
    paddingBottom: 8,
  },
  historyListContent: {
    paddingBottom: 8,
    paddingTop: 0,
  },
  recentListContentWithMiniRecording: {
    paddingBottom: 160,
  },
  meetingDateHeader: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 8,
    marginTop: 5,
  },
  historyDateHeader: {
    marginBottom: 6,
    marginTop: 0,
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 17,
    fontWeight: '900',
  },
  allText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '900',
  },
  historyHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  selectToggle: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  selectToggleText: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
  },
  batchBar: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 12,
  },
  batchButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 10,
    borderWidth: 1,
    flex: 1,
    minHeight: 42,
    justifyContent: 'center',
  },
  batchDeleteButton: {
    backgroundColor: '#fee2e2',
    borderColor: '#fecaca',
  },
  batchText: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
  },
  batchDeleteText: {
    color: '#ef4444',
    fontSize: 13,
    fontWeight: '900',
  },
  card: {
    alignItems: 'flex-start',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
    minHeight: 106,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  homeMeetingCard: {
    backgroundColor: '#ffffff',
    borderColor: '#f2f3f7',
    borderRadius: 18,
    borderWidth: 1,
    marginBottom: 12,
    paddingHorizontal: 16,
    paddingVertical: 15,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    elevation: 2,
  },
  homeMeetingTop: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  homeMeetingTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 15.5,
    fontWeight: '900',
    lineHeight: 21,
  },
  homeMeetingMetaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 5,
    marginTop: 8,
  },
  homeMeetingMeta: {
    color: '#8b95a7',
    flex: 1,
    fontSize: 11.5,
    fontWeight: '800',
    lineHeight: 16,
  },
  homeAnalyzingBlock: {
    backgroundColor: '#f3f0ff',
    borderRadius: 12,
    gap: 3,
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  homePreviewBlock: {
    gap: 6,
    marginTop: 10,
  },
  previewRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
  previewLabel: {
    color: '#111827',
    flexShrink: 0,
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 18,
  },
  previewText: {
    color: '#111827',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
  },
  homeFailedBlock: {
    backgroundColor: '#fff1f2',
    borderRadius: 12,
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  failedHint: {
    color: '#ef4444',
    fontSize: 11.5,
    fontWeight: '800',
    lineHeight: 17,
  },
  homePendingHint: {
    color: '#8b95a7',
    fontSize: 11.5,
    fontWeight: '800',
    lineHeight: 17,
    marginTop: 10,
  },
  homeMeetingFooter: {
    alignItems: 'center',
    borderTopColor: '#f1f2f6',
    borderTopWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 12,
    paddingTop: 12,
  },
  summaryState: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 4,
  },
  summaryStateText: {
    color: '#2B6CFF',
    flexShrink: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  summaryStateTextFailed: {
    color: '#ef4444',
  },
  actionCountBadge: {
    backgroundColor: '#f3f4f6',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  actionCountBadgeActive: {
    backgroundColor: '#fff4e8',
  },
  actionCountText: {
    color: '#8b95a7',
    fontSize: 10.5,
    fontWeight: '900',
  },
  actionCountTextActive: {
    color: '#f97316',
  },
  swipeRow: {
    marginBottom: 12,
    overflow: 'hidden',
    position: 'relative',
  },
  swipeDelete: {
    alignItems: 'center',
    backgroundColor: '#ef4444',
    borderRadius: 18,
    bottom: 0,
    justifyContent: 'center',
    position: 'absolute',
    right: 0,
    top: 0,
    width: 76,
  },
  swipeDeleteText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '900',
  },
  selectBox: {
    alignItems: 'center',
    borderColor: '#d8dbe6',
    borderRadius: 9,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  selectBoxActive: {
    backgroundColor: '#6657ff',
    borderColor: '#6657ff',
  },
  selectCheck: {
    color: 'transparent',
    fontSize: 13,
    fontWeight: '900',
  },
  selectCheckActive: {
    color: '#ffffff',
  },
  cardBody: {
    flex: 1,
    gap: 6,
  },
  cardTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  cardTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 20,
  },
  cardRight: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 5,
  },
  cardMeta: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 16,
  },
  cardStatsRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 1,
  },
  cardStatItem: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  cardStatText: {
    color: '#374151',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
  },
  cardStatDivider: {
    color: '#d1d5db',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
  },
  analyzingBlock: {
    gap: 8,
    marginTop: 2,
  },
  analysisHint: {
    color: '#6657ff',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 17,
  },
  stageHint: {
    color: '#9ca3af',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 16,
  },
  progressTip: {
    alignItems: 'center',
    backgroundColor: '#f3f0ff',
    borderRadius: 12,
    flexDirection: 'row',
    gap: 4,
    minHeight: 38,
    paddingHorizontal: 10,
  },
  progressTipLeft: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 7,
  },
  progressTipText: {
    color: '#6657ff',
    flex: 1,
    fontSize: 11,
    fontWeight: '800',
  },
  progressLink: {
    color: '#6657ff',
    fontSize: 11,
    fontWeight: '900',
  },
  pendingHint: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 17,
    marginTop: 1,
  },
  statusBadge: {
    alignItems: 'center',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 4,
    marginTop: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  cardFlushBottom: {
    marginBottom: 0,
  },
  statusSpinner: {
    height: 11,
    transform: [{ scale: 0.68 }],
    width: 11,
  },
  statusText: {
    fontSize: 11,
    fontWeight: '900',
  },
  recordingBadge: {
    backgroundColor: '#f0efff',
  },
  recordingText: {
    color: '#6657ff',
  },
  analyzingBadge: {
    backgroundColor: '#f0efff',
  },
  analyzingText: {
    color: '#6657ff',
  },
  uploadedBadge: {
    backgroundColor: '#eef8ff',
  },
  uploadedText: {
    color: '#0284c7',
  },
  completedBadge: {
    backgroundColor: '#dcfce7',
  },
  completedText: {
    color: '#16a34a',
  },
  pendingBadge: {
    backgroundColor: '#f3f4f6',
  },
  pendingText: {
    color: '#6b7280',
  },
  failedBadge: {
    backgroundColor: '#fee2e2',
  },
  failedText: {
    color: '#ef4444',
  },
  empty: {
    color: '#8b95a7',
    lineHeight: 22,
    paddingHorizontal: 22,
    paddingTop: 28,
    textAlign: 'center',
  },
  loadMoreButton: {
    alignItems: 'center',
    alignSelf: 'center',
    borderColor: '#d9ddf0',
    borderRadius: 18,
    borderWidth: 1,
    justifyContent: 'center',
    marginTop: 12,
    minHeight: 44,
    minWidth: 132,
    paddingHorizontal: 18,
  },
  loadMoreText: {
    color: '#6657ff',
    fontSize: 14,
    fontWeight: '800',
  },
  error: {
    color: '#ef4444',
    marginBottom: 10,
  },
});
