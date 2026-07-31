import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  StatusBar,
  Text,
  TextInput,
  TextInputSubmitEditingEventData,
  NativeSyntheticEvent,
  View,
} from 'react-native';

import { listTasks, TaskListItem, updateTaskStatus } from '../api';
import { LucideIcon } from '../components/LucideIcon';

type Props = {
  onBack: () => void;
  onOpenMeeting: (meetingId: string, initialTab?: 'actions') => void;
  onOpenTask?: (task: TaskListItem) => void;
  taskOverrides?: Record<string, Partial<TaskListItem>>;
};

const TASK_SEARCH_HISTORY_KEY = 'meetmind.task.search.history.v1';
const TASK_SEARCH_LIMIT = 15;
const MAX_RECENT_SEARCHES = 10;
const completedStatuses = new Set(['completed', 'done', 'closed', 'finished']);

function normalizeText(value: string | null | undefined): string {
  return (value || '').trim();
}

function normalizeStatus(value: string | null | undefined): string {
  return normalizeText(value).toLowerCase();
}

function isCompletedTask(item: TaskListItem): boolean {
  return completedStatuses.has(normalizeStatus(item.status));
}

function taskTitle(item: TaskListItem): string {
  return normalizeText(item.task) || normalizeText(item.source_text) || '未命名任务';
}

function dueValue(item: TaskListItem): string | null {
  return normalizeText(item.due_date) || normalizeText(item.deadline) || null;
}

function parseDueDate(value: string | null | undefined): Date | null {
  const raw = normalizeText(value);
  if (!raw) return null;
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(raw)
    ? `${raw}T23:59:59`
    : raw.replace(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?::\d{2})?$/, '$1T$2');
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function formatClock(value: Date): string {
  return value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDueDate(value: string | null | undefined): string {
  const raw = normalizeText(value);
  if (!raw) return '未设置截止时间';
  const due = parseDueDate(raw);
  if (!due) return raw;

  const hasTime = !/^\d{4}-\d{2}-\d{2}$/.test(raw);
  const monthDay = `${due.getMonth() + 1}-${due.getDate()}`;
  if (hasTime) return `${monthDay} ${formatClock(due)}`;
  return monthDay;
}

function isOverdueTask(item: TaskListItem): boolean {
  if (isCompletedTask(item)) return false;
  const due = parseDueDate(dueValue(item));
  return Boolean(due && due.getTime() < Date.now());
}

function priorityMeta(value: string | null | undefined): {
  label: string;
  tone: 'high' | 'medium' | 'low' | 'unknown';
} {
  const normalized = normalizeStatus(value);
  if (normalized === 'high') return { label: '高优先级', tone: 'high' };
  if (normalized === 'medium') return { label: '中优先级', tone: 'medium' };
  if (normalized === 'low') return { label: '低优先级', tone: 'low' };
  return { label: normalizeText(value) || '未设置', tone: 'unknown' };
}

function uniqueRecentSearches(items: string[]): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const item of items) {
    const keyword = item.trim();
    const key = keyword.toLowerCase();
    if (!keyword || seen.has(key)) continue;
    seen.add(key);
    next.push(keyword);
    if (next.length >= MAX_RECENT_SEARCHES) break;
  }
  return next;
}

export function TaskSearchScreen({ onBack, onOpenMeeting, onOpenTask, taskOverrides = {} }: Props) {
  const inputRef = useRef<TextInput>(null);
  const requestSeqRef = useRef(0);
  const latestKeywordRef = useRef('');
  const [query, setQuery] = useState('');
  const [submittedKeyword, setSubmittedKeyword] = useState('');
  const [results, setResults] = useState<TaskListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [updatingTaskIds, setUpdatingTaskIds] = useState<Set<string>>(() => new Set());

  const keyword = query.trim();
  const displayedResults = useMemo(
    () => results.map((task) => ({ ...task, ...(taskOverrides[task.id] || {}) })),
    [results, taskOverrides],
  );

  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 80);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    let mounted = true;
    async function loadHistory() {
      try {
        const raw = await AsyncStorage.getItem(TASK_SEARCH_HISTORY_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        if (mounted && Array.isArray(parsed)) {
          setRecentSearches(uniqueRecentSearches(parsed.filter((item) => typeof item === 'string')));
        }
      } catch {
        if (mounted) setRecentSearches([]);
      } finally {
        if (mounted) setHistoryLoaded(true);
      }
    }
    loadHistory();
    return () => {
      mounted = false;
    };
  }, []);

  async function persistRecent(next: string[]) {
    setRecentSearches(next);
    try {
      await AsyncStorage.setItem(TASK_SEARCH_HISTORY_KEY, JSON.stringify(next));
    } catch {
      // Search history persistence must not block the search flow.
    }
  }

  async function addRecentSearch(value: string) {
    const normalized = value.trim();
    if (!normalized) return;
    const next = uniqueRecentSearches([normalized, ...recentSearches]);
    await persistRecent(next);
  }

  async function removeRecentSearch(value: string) {
    const target = value.trim().toLowerCase();
    await persistRecent(recentSearches.filter((item) => item.trim().toLowerCase() !== target));
  }

  async function clearRecentSearches() {
    await persistRecent([]);
  }

  function resetSubmittedSearch() {
    requestSeqRef.current += 1;
    latestKeywordRef.current = '';
    setSubmittedKeyword('');
    setResults([]);
    setTotal(0);
    setHasMore(false);
    setLoading(false);
    setLoadingMore(false);
    setError(null);
  }

  function handleQueryChange(value: string) {
    setQuery(value);
    if (value.trim() !== submittedKeyword) {
      resetSubmittedSearch();
    }
  }

  function clearQuery() {
    setQuery('');
    resetSubmittedSearch();
    inputRef.current?.focus();
  }

  async function runSearch(value: string, mode: 'reset' | 'more') {
    const normalized = value.trim();
    if (!normalized) return;

    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    latestKeywordRef.current = normalized;
    setSubmittedKeyword(normalized);
    if (mode === 'more') setLoadingMore(true);
    else {
      setLoading(true);
      setError(null);
      setResults([]);
      setTotal(0);
      setHasMore(false);
    }

    try {
      const response = await listTasks({
        q: normalized,
        limit: TASK_SEARCH_LIMIT,
        offset: mode === 'more' ? results.length : 0,
      });
      if (requestSeqRef.current !== requestId || latestKeywordRef.current !== normalized) return;

      setResults((current) => (mode === 'more' ? [...current, ...response.items] : response.items));
      setTotal(response.total);
      setHasMore(response.has_more);
      setError(null);
      await addRecentSearch(normalized);
    } catch (nextError) {
      if (requestSeqRef.current !== requestId || latestKeywordRef.current !== normalized) return;
      setError(nextError instanceof Error ? nextError.message : '搜索失败，请稍后重试。');
      if (mode !== 'more') {
        setResults([]);
        setTotal(0);
        setHasMore(false);
      }
    } finally {
      if (requestSeqRef.current === requestId) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }

  function submitSearch(value?: string) {
    const submittedValue = (value ?? query).trim();
    if (!submittedValue) {
      clearQuery();
      return;
    }
    setQuery(submittedValue);
    runSearch(submittedValue, 'reset');
  }

  function handleLoadMore() {
    if (!submittedKeyword || loading || loadingMore || !hasMore) return;
    runSearch(submittedKeyword, 'more');
  }

  function handleRecentPress(value: string) {
    setQuery(value);
    runSearch(value, 'reset');
  }

  async function handleStatusPress(task: TaskListItem) {
    if (updatingTaskIds.has(task.id)) return;

    const previousTask = task;
    const nextStatus: 'open' | 'completed' = isCompletedTask(task) ? 'open' : 'completed';
    setUpdatingTaskIds((current) => {
      const next = new Set(current);
      next.add(task.id);
      return next;
    });
    setResults((current) => current.map((item) => (item.id === task.id ? { ...item, status: nextStatus } : item)));

    try {
      const updated = await updateTaskStatus(task.id, nextStatus);
      setResults((current) => current.map((item) => (item.id === task.id ? updated : item)));
    } catch (nextError) {
      setResults((current) => current.map((item) => (item.id === task.id ? previousTask : item)));
      Alert.alert('更新失败', nextError instanceof Error ? nextError.message : '任务状态更新失败，请稍后重试。');
    } finally {
      setUpdatingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  function handleOpenTask(item: TaskListItem) {
    onOpenTask?.(item);
  }

  const showRecent = !keyword && !submittedKeyword;
  const resultSubtitle = useMemo(() => {
    if (!keyword && !submittedKeyword) return '输入关键词后点击输入法自带搜索按钮';
    if (keyword && keyword !== submittedKeyword) return '点击输入法搜索后返回结果';
    if (loading) return '正在搜索';
    return `搜索结果 ${total} 项`;
  }, [keyword, loading, submittedKeyword, total]);

  function renderHeader() {
    return (
      <View style={styles.header}>
        <View style={styles.navHeader}>
          <Pressable onPress={onBack} hitSlop={10} style={styles.backButton}>
            <LucideIcon name="chevron-left" color="#111827" size={25} strokeWidth={2.4} />
          </Pressable>
          <Text style={styles.title}>搜索任务</Text>
          <View style={styles.headerSpacer} />
        </View>

        <View style={styles.searchBox}>
          <LucideIcon name="search" color="#8b95a7" size={19} strokeWidth={2.2} />
          <TextInput
            ref={inputRef}
            autoFocus
            value={query}
            onChangeText={handleQueryChange}
            placeholder="搜索任务标题、会议或负责人"
            placeholderTextColor="#9aa3b2"
            returnKeyType="search"
            enablesReturnKeyAutomatically
            autoCorrect={false}
            autoCapitalize="none"
            blurOnSubmit={false}
            onSubmitEditing={(event: NativeSyntheticEvent<TextInputSubmitEditingEventData>) => submitSearch(event.nativeEvent.text)}
            style={styles.searchInput}
          />
          {query ? (
            <Pressable onPress={clearQuery} hitSlop={8} style={styles.clearIconButton}>
              <Text style={styles.clearIconText}>×</Text>
            </Pressable>
          ) : null}
        </View>

        <Text style={styles.resultSubtitle}>{resultSubtitle}</Text>

        {showRecent ? renderRecentSearches() : null}
      </View>
    );
  }

  function renderRecentSearches() {
    return (
      <View style={styles.recentSection}>
        <View style={styles.recentHeader}>
          <Text style={styles.recentTitle}>最近搜索</Text>
          {recentSearches.length ? (
            <Pressable onPress={clearRecentSearches} hitSlop={8}>
              <Text style={styles.clearAllText}>清空全部</Text>
            </Pressable>
          ) : null}
        </View>

        {!historyLoaded ? (
          <ActivityIndicator color="#2B6CFF" />
        ) : recentSearches.length ? (
          <View style={styles.recentList}>
            {recentSearches.map((item) => (
              <View key={item} style={styles.recentItem}>
                <Pressable onPress={() => handleRecentPress(item)} style={styles.recentKeyword}>
                  <LucideIcon name="clock-3" color="#cbd5e1" size={17} strokeWidth={2.1} />
                  <Text numberOfLines={1} style={styles.recentKeywordText}>{item}</Text>
                </Pressable>
                <Pressable onPress={() => removeRecentSearch(item)} hitSlop={8} style={styles.recentDelete}>
                  <Text style={styles.recentDeleteText}>×</Text>
                </Pressable>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.recentEmpty}>暂无最近搜索</Text>
        )}
      </View>
    );
  }

  function renderTask({ item }: { item: TaskListItem }) {
    const completed = isCompletedTask(item);
    const overdue = isOverdueTask(item);
    const priority = priorityMeta(item.priority);
    const updating = updatingTaskIds.has(item.id);

    return (
      <Pressable onPress={() => handleOpenTask(item)} style={[styles.card, completed ? styles.cardDone : null]}>
        <Pressable
          onPress={(event) => {
            event.stopPropagation();
            handleStatusPress(item);
          }}
          disabled={updating}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel={`任务状态：${completed ? '已完成' : '未完成'}`}
          style={styles.statusButton}
        >
          {completed ? (
            <LucideIcon name="square-check-big" color="#10b981" size={24} strokeWidth={2.4} />
          ) : updating ? (
            <ActivityIndicator color="#2B6CFF" size="small" />
          ) : (
            <View style={[styles.emptySquare, overdue ? styles.emptySquareOverdue : null]} />
          )}
        </Pressable>

        <View style={styles.cardBody}>
          <Text style={[styles.taskTitle, completed ? styles.taskTitleDone : null]}>{taskTitle(item)}</Text>

          <View style={styles.metaItem}>
            <LucideIcon name="calendar-days" color={overdue && !completed ? '#dc2626' : '#8b95a7'} size={14} strokeWidth={2.2} />
            <Text style={[styles.metaText, overdue && !completed ? styles.overdueText : null]}>{formatDueDate(dueValue(item))}</Text>
          </View>

          <View style={[styles.priorityTag, styles[`${priority.tone}PriorityTag`]]}>
            <Text style={[styles.priorityText, styles[`${priority.tone}PriorityText`]]}>{priority.label}</Text>
          </View>
        </View>
      </Pressable>
    );
  }

  function renderEmptyState() {
    if (!submittedKeyword) return null;
    if (loading) {
      return (
        <View style={styles.stateCard}>
          <ActivityIndicator color="#2B6CFF" />
          <Text style={styles.stateTitle}>正在搜索任务</Text>
        </View>
      );
    }
    if (error) {
      return (
        <View style={styles.stateCard}>
          <LucideIcon name="triangle-alert" color="#dc2626" size={26} strokeWidth={2.2} />
          <Text style={styles.stateTitle}>搜索失败</Text>
          <Text style={styles.stateText}>{error}</Text>
          <Pressable onPress={() => runSearch(submittedKeyword, 'reset')} style={styles.retryButton}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      );
    }
    return (
      <View style={styles.stateCard}>
        <LucideIcon name="search" color="#8b95a7" size={27} strokeWidth={2.2} />
        <Text style={styles.stateTitle}>没有找到相关任务</Text>
        <Text style={styles.stateText}>换个关键词试试，搜索范围以当前 /tasks 接口能力为准。</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboardContainer}
      >
        <FlatList
          data={submittedKeyword && !loading && !error ? displayedResults : []}
          keyExtractor={(item) => item.id}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={renderEmptyState}
          renderItem={renderTask}
          contentContainerStyle={styles.listContent}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.25}
          ListFooterComponent={
            <View style={styles.footer}>
              {loadingMore ? <ActivityIndicator color="#2B6CFF" /> : null}
            </View>
          }
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#F5F7FA',
    flex: 1,
    paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight || 0 : 0,
  },
  keyboardContainer: {
    flex: 1,
  },
  listContent: {
    gap: 12,
    paddingBottom: 28,
    paddingHorizontal: 16,
    paddingTop: 6,
  },
  header: {
    gap: 14,
  },
  navHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 52,
    position: 'relative',
  },
  backButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    top: 6,
    width: 40,
    zIndex: 2,
  },
  title: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    paddingHorizontal: 56,
    textAlign: 'center',
    width: '100%',
  },
  headerSpacer: {
    height: 40,
    position: 'absolute',
    right: 0,
    top: 6,
    width: 40,
  },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf2f7',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 52,
    paddingHorizontal: 14,
    shadowColor: '#64748b',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 14,
    elevation: 2,
  },
  searchInput: {
    color: '#111827',
    flex: 1,
    fontSize: 15,
    minHeight: 46,
    minWidth: 0,
    padding: 0,
  },
  clearIconButton: {
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    borderRadius: 13,
    height: 26,
    justifyContent: 'center',
    width: 26,
  },
  clearIconText: {
    color: '#2B6CFF',
    fontSize: 20,
    fontWeight: '800',
    lineHeight: 22,
  },
  resultSubtitle: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
    paddingHorizontal: 4,
  },
  recentSection: {
    gap: 10,
    paddingTop: 8,
  },
  recentHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 28,
  },
  recentTitle: {
    color: '#64748b',
    fontSize: 15,
    fontWeight: '900',
  },
  clearAllText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '900',
  },
  recentList: {
    gap: 2,
  },
  recentItem: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 48,
  },
  recentKeyword: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 48,
  },
  recentKeywordText: {
    color: '#1f2937',
    flex: 1,
    fontSize: 16,
    fontWeight: '900',
  },
  recentDelete: {
    alignItems: 'center',
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  recentDeleteText: {
    color: '#cbd5e1',
    fontSize: 27,
    fontWeight: '800',
    lineHeight: 28,
  },
  recentEmpty: {
    color: '#9aa3b2',
    fontSize: 13,
    fontWeight: '700',
    paddingVertical: 10,
  },
  card: {
    alignItems: 'flex-start',
    backgroundColor: '#ffffff',
    borderColor: '#eef2f7',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 15,
    shadowColor: '#64748b',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.07,
    shadowRadius: 18,
    elevation: 2,
  },
  cardDone: {
    shadowOpacity: 0.03,
  },
  statusButton: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
    width: 28,
  },
  emptySquare: {
    borderColor: '#cbd5e1',
    borderRadius: 6,
    borderWidth: 2,
    height: 22,
    width: 22,
  },
  emptySquareOverdue: {
    borderColor: '#f87171',
  },
  cardBody: {
    flex: 1,
    gap: 10,
  },
  taskTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 21,
  },
  taskTitleDone: {
    color: '#94a3b8',
    textDecorationLine: 'line-through',
  },
  metaItem: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    minHeight: 18,
  },
  metaText: {
    color: '#64748b',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 16,
  },
  overdueText: {
    color: '#dc2626',
  },
  priorityTag: {
    alignSelf: 'flex-start',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  priorityText: {
    fontSize: 11,
    fontWeight: '900',
  },
  highPriorityTag: {
    backgroundColor: '#fee2e2',
  },
  highPriorityText: {
    color: '#dc2626',
  },
  mediumPriorityTag: {
    backgroundColor: '#eaf2ff',
  },
  mediumPriorityText: {
    color: '#2563eb',
  },
  lowPriorityTag: {
    backgroundColor: '#f1f5f9',
  },
  lowPriorityText: {
    color: '#64748b',
  },
  unknownPriorityTag: {
    backgroundColor: '#f8fafc',
  },
  unknownPriorityText: {
    color: '#94a3b8',
  },
  stateCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef2f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 9,
    marginTop: 4,
    padding: 28,
  },
  stateTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  stateText: {
    color: '#8b95a7',
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  retryButton: {
    backgroundColor: '#eef4ff',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  retryText: {
    color: '#2B6CFF',
    fontSize: 13,
    fontWeight: '900',
  },
  footer: {
    minHeight: 28,
    paddingVertical: 8,
  },
});
