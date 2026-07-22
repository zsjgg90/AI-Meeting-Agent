import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  FlatList,
  PanResponder,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { bulkDeleteMeetings, deleteMeeting, getMeetingSummary, listMeetings, Meeting, MeetingSummary } from '../api';
import { LucideIcon } from '../components/LucideIcon';

type Props = {
  mode?: 'home' | 'all';
  activeRecordingMeetingId?: string | null;
  onCreateMeeting: () => void;
  onOpenMeeting: (meetingId: string) => void;
  onShowAll?: () => void;
};

type DisplayStatus = 'recording' | 'analyzing' | 'uploaded' | 'completed' | 'pending' | 'failed';

type SummaryByMeeting = Record<string, MeetingSummary | null>;
const HOME_MEETING_LIMIT = 10;
const HISTORY_PAGE_SIZE = 30;

type HomeStats = {
  weeklyMeetings: number;
  weeklyHours: string;
  meetingTrend: string;
  hourTrend: string;
  actionCount: number;
  unresolvedCount: number;
  highPriorityActionCount: number;
  riskCount: number;
  staleUnresolvedCount: number;
};

const statusText: Record<DisplayStatus, string> = {
  recording: '录音中',
  analyzing: '分析中',
  uploaded: '已上传',
  completed: '已完成',
  pending: '待录音',
  failed: '失败',
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

function formatRecentMeetingTime(value: string): string {
  const date = parsedDate(value);
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

function weekRange(offsetWeeks = 0): { start: Date; end: Date } {
  const start = new Date();
  const day = start.getDay() || 7;
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - day + 1 + offsetWeeks * 7);
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return { start, end };
}

function isInWeek(value: string | null | undefined, offsetWeeks = 0): boolean {
  const date = parsedDate(value);
  if (!date) return false;
  const { start, end } = weekRange(offsetWeeks);
  return date >= start && date < end;
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

function formatHours(seconds: number): string {
  if (seconds <= 0) return '0';
  const hours = seconds / 3600;
  if (hours < 0.1) return '<0.1';
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
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

function isHighPriority(value: { priority?: string | null }): boolean {
  return value.priority === 'high' || value.priority === '高' || value.priority === '高优先级';
}

function formatTrend(current: number, previous: number): string {
  if (current <= 0 && previous <= 0) return '较上周 0%';
  if (previous <= 0) return '较上周 ↑100%';
  const rate = Math.round(((current - previous) / previous) * 100);
  if (rate > 0) return `较上周 ↑${rate}%`;
  if (rate < 0) return `较上周 ↓${Math.abs(rate)}%`;
  return '较上周 0%';
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

function buildHomeStats(meetings: Meeting[], summaries: SummaryByMeeting): HomeStats {
  const weeklyMeetings = meetings.filter((meeting) => isInWeek(meeting.created_at, 0));
  const previousMeetings = meetings.filter((meeting) => isInWeek(meeting.created_at, -1));
  const weeklySeconds = weeklyMeetings.reduce((total, meeting) => total + meetingDurationSeconds(meeting), 0);
  const previousSeconds = previousMeetings.reduce((total, meeting) => total + meetingDurationSeconds(meeting), 0);
  let actionCount = 0;
  let unresolvedCount = 0;
  let highPriorityActionCount = 0;
  let riskCount = 0;
  let staleUnresolvedCount = 0;
  const sevenDaysAgo = Date.now() - 7 * 86400000;

  for (const meeting of weeklyMeetings) {
    const summary = summaries[meeting.id];
    const actions = Array.isArray(summary?.action_items) ? summary.action_items : [];
    const unresolved = Array.isArray(summary?.unresolved_issues) ? summary.unresolved_issues : [];
    const risks = Array.isArray(summary?.risks_and_focus) ? summary.risks_and_focus : [];

    actionCount += actions.length;
    highPriorityActionCount += actions.filter(isHighPriority).length;
    unresolvedCount += unresolved.length;
    riskCount += risks.length;
  }

  for (const meeting of meetings) {
    const summary = summaries[meeting.id];
    const unresolved = Array.isArray(summary?.unresolved_issues) ? summary.unresolved_issues : [];
    if (unresolved.length && (parsedDate(meeting.created_at)?.getTime() || Date.now()) < sevenDaysAgo) {
      staleUnresolvedCount += unresolved.length;
    }
  }

  return {
    weeklyMeetings: weeklyMeetings.length,
    weeklyHours: formatHours(weeklySeconds),
    meetingTrend: formatTrend(weeklyMeetings.length, previousMeetings.length),
    hourTrend: formatTrend(weeklySeconds, previousSeconds),
    actionCount,
    unresolvedCount,
    highPriorityActionCount,
    riskCount,
    staleUnresolvedCount,
  };
}

function MeetingCard({
  item,
  onPress,
  selectable = false,
  selected = false,
  onToggleSelect,
  summary,
  isActiveRecording = false,
}: {
  item: Meeting;
  onPress: () => void;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
  summary?: MeetingSummary | null;
  isActiveRecording?: boolean;
}) {
  const status = isActiveRecording ? 'recording' : normalizeStatus(item.status);
  const duration = meetingDurationText(item, status);
  const actions = itemCount(summary?.action_items);
  const conclusions = itemCount(summary?.key_conclusions || summary?.decisions);
  const risks = itemCount(summary?.risks_and_focus || summary?.risks);
  const highPriority = Array.isArray(summary?.action_items) ? summary.action_items.filter(isHighPriority).length : 0;
  const people = participantCount(summary);
  const remainingAnalysisTime = analysisRemainingText(item);
  const metaParts = [formatRecentMeetingTime(item.created_at), duration];
  if (people > 0) metaParts.push(`${people}人`);
  const title = item.title?.trim() && item.title.trim().length >= 2 ? item.title.trim() : '未命名会议';
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
            <View style={[styles.statusBadge, styles[`${status}Badge`]]}>
              <Text style={[styles.statusText, styles[`${status}Text`]]}>{statusText[status]}</Text>
            </View>
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

function InsightMetric({
  value,
  unit,
  label,
  tone,
  detail,
  pill,
}: {
  value: string | number;
  unit?: string;
  label: string;
  tone: 'purple' | 'blue' | 'green' | 'orange';
  detail?: string;
  pill?: string;
}) {
  return (
    <View style={[styles.metricTile, styles[`${tone}Metric`]]}>
      <View style={styles.metricValueRow}>
        <Text style={styles.metricValue}>{value}</Text>
        {unit ? <Text style={styles.metricUnit}>{unit}</Text> : null}
      </View>
      <Text style={styles.metricLabel}>{label}</Text>
      {pill ? (
        <View style={[styles.metricPill, styles[`${tone}MetricPill`]]}>
          <Text style={[styles.metricPillText, styles[`${tone}MetricPillText`]]}>{pill}</Text>
        </View>
      ) : (
        <Text style={[styles.metricDetail, tone === 'green' ? styles.positiveDetail : null]}>{detail}</Text>
      )}
    </View>
  );
}

function InsightCard({ stats }: { stats: HomeStats }) {
  return (
    <View style={styles.dashboardCard}>
      <View style={styles.cardSectionHeader}>
        <Text style={styles.dashboardTitle}>本周会议洞察</Text>
      </View>
      <View style={styles.metricsGrid}>
        <InsightMetric value={stats.weeklyMeetings} unit="场" label="会议总数" detail={stats.meetingTrend} tone="purple" />
        <InsightMetric value={stats.weeklyHours} unit="h" label="会议时长" detail={stats.hourTrend} tone="blue" />
        <InsightMetric value={stats.actionCount} unit="项" label="待办事项" pill={`${stats.highPriorityActionCount} 项高优先级`} tone="green" />
        <InsightMetric value={stats.unresolvedCount} unit="项" label="遗留问题" pill={`${stats.staleUnresolvedCount} 项超 7 天`} tone="orange" />
      </View>
    </View>
  );
}

export function MeetingListScreen({
  mode = 'home',
  activeRecordingMeetingId,
  onCreateMeeting,
  onOpenMeeting,
  onShowAll,
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
  }, [loadMeetings]);

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

  const visibleMeetings = useMemo(() => (mode === 'home' ? meetings.slice(0, HOME_MEETING_LIMIT) : meetings), [meetings, mode]);
  const homeStats = useMemo(() => buildHomeStats(meetings, summaryByMeeting), [meetings, summaryByMeeting]);

  useEffect(() => {
    if (mode !== 'home' || meetings.length === 0) {
      setSummaryByMeeting({});
      return;
    }

    let cancelled = false;
    const meetingsForStats = meetings.filter((meeting) => normalizeStatus(meeting.status) === 'completed').slice(0, 8);

    async function loadSummaries() {
      const results = await Promise.allSettled(
        meetingsForStats.map(async (meeting) => [meeting.id, await getMeetingSummary(meeting.id)] as const),
      );
      if (cancelled) return;

      const next: SummaryByMeeting = {};
      for (const result of results) {
        if (result.status === 'fulfilled') {
          next[result.value[0]] = result.value[1];
        }
      }
      setSummaryByMeeting(next);
    }

    loadSummaries().catch(() => {
      if (!cancelled) setSummaryByMeeting({});
    });

    return () => {
      cancelled = true;
    };
  }, [meetings, mode]);

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
      <View style={styles.container}>
        <View style={styles.historyHeader}>
          <Text style={styles.historySub}>共 {meetings.length} 场会议</Text>
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
        <FlatList
          data={visibleMeetings}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.recentListContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor="#6657ff" />}
          ListEmptyComponent={!loading ? <Text style={styles.empty}>暂无历史会议。</Text> : null}
          onEndReached={loadMoreMeetings}
          onEndReachedThreshold={0.3}
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
                selectable={selecting}
                selected={selectedIds.includes(item.id)}
                onToggleSelect={() => toggleSelected(item.id)}
                isActiveRecording={item.id === activeRecordingMeetingId}
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
    <FlatList
      style={styles.container}
      data={visibleMeetings}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.homeListContent}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor="#6657ff" />}
      ListHeaderComponent={
        <>
      <View style={styles.brandRow}>
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

      <View style={styles.heroCard}>
        <View style={styles.heroContent}>
          <View style={styles.heroCopy}>
            <View style={styles.heroTop}>
              <View style={styles.heroIcon}>
                <LucideIcon name="video" color="#ffffff" size={28} strokeWidth={2.2} />
              </View>
              <View style={styles.heroTextBlock}>
                <Text numberOfLines={1} style={styles.heroTitle}>开始你的智能会议</Text>
                <Text numberOfLines={1} style={styles.heroSub}>让AI帮你记录、整理和总结</Text>
              </View>
            </View>
          </View>
          <Pressable onPress={onCreateMeeting} style={styles.createButton}>
            <Text style={styles.createText}>＋ 开始会议</Text>
          </Pressable>
        </View>
      </View>

      <InsightCard stats={homeStats} />

      <View style={styles.recentCard}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>最近会议</Text>
          <Pressable onPress={onShowAll}>
            <Text style={styles.allText}>全部 ›</Text>
          </Pressable>
        </View>

        {loading ? <ActivityIndicator color="#6657ff" /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

      </View>
        </>
      }
      ListEmptyComponent={!loading ? <Text style={styles.empty}>暂无会议，点击上方按钮开始记录。</Text> : null}
      renderItem={({ item }) => (
        <MeetingCard
          item={item}
          summary={summaryByMeeting[item.id]}
          isActiveRecording={item.id === activeRecordingMeetingId}
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
  homeListContent: {
    paddingBottom: 120,
  },
  brandRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 14,
    height: 48,
    justifyContent: 'center',
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.22,
    shadowRadius: 18,
    width: 48,
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
    fontSize: 24,
    fontWeight: '900',
  },
  brandSub: {
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'left',
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
  dashboardCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 20,
    borderWidth: 1,
    marginBottom: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  cardSectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  dashboardTitle: {
    color: '#111827',
    fontSize: 17,
    fontWeight: '900',
  },
  moreInsightText: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '900',
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  metricTile: {
    borderRadius: 14,
    flex: 1,
    minHeight: 92,
    paddingHorizontal: 9,
    paddingVertical: 11,
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
    marginBottom: 6,
  },
  recentCard: {
    marginBottom: 4,
    marginTop: 4,
    paddingHorizontal: 16,
  },
  recentListContent: {
    paddingBottom: 8,
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
    marginBottom: 18,
  },
  historySub: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
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
    color: '#6657ff',
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
    color: '#6657ff',
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
  swipeRow: {
    overflow: 'hidden',
    position: 'relative',
  },
  swipeDelete: {
    alignItems: 'center',
    backgroundColor: '#ef4444',
    borderRadius: 18,
    bottom: 8,
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
    borderRadius: 999,
    marginTop: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
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
