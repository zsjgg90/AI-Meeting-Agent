import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { listTasks, TaskListItem, updateTaskStatus } from '../api';
import { LucideIcon } from '../components/LucideIcon';

type TaskStatusFilter = 'all' | 'completed' | 'overdue';

type Props = {
  onOpenMeeting?: (meetingId: string, initialTab?: 'actions') => void;
  onOpenSearch?: () => void;
  onOpenTask?: (task: TaskListItem) => void;
  taskOverrides?: Record<string, Partial<TaskListItem>>;
};

const TASK_PAGE_SIZE = 15;
const completedStatuses = new Set(['completed', 'done', 'closed', 'finished']);
const priorityRank: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

function taskTitle(item: TaskListItem): string {
  return item.task?.trim() || item.source_text?.trim() || '未命名任务';
}

function normalizeStatus(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase();
}

function isCompletedTask(item: TaskListItem): boolean {
  return completedStatuses.has(normalizeStatus(item.status));
}

function statusLabel(value: string | null | undefined): string {
  const normalized = normalizeStatus(value);
  if (completedStatuses.has(normalized)) return '已完成';
  if (normalized === 'open' || normalized === 'todo' || normalized === 'pending') return '待处理';
  if (normalized === 'in_progress' || normalized === 'running') return '进行中';
  return value?.trim() || '未设置状态';
}

function dueValue(item: TaskListItem): string | null {
  return item.due_date?.trim() || item.deadline?.trim() || null;
}

function parseDueDate(value: string | null | undefined): Date | null {
  const raw = value?.trim();
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
  const raw = value?.trim();
  if (!raw) return '未设置截止时间';
  const due = parseDueDate(raw);
  if (!due) return raw;

  const hasTime = !/^\d{4}-\d{2}-\d{2}$/.test(raw);
  const monthDay = `${due.getMonth() + 1}-${due.getDate()}`;
  if (hasTime) return `${monthDay} ${formatClock(due)}`;
  return monthDay;
}

function isOverdueTask(item: TaskListItem, now = new Date()): boolean {
  if (isCompletedTask(item)) return false;
  const due = parseDueDate(dueValue(item));
  return Boolean(due && due.getTime() < now.getTime());
}

function priorityMeta(value: string | null | undefined): {
  label: string;
  normalized: string;
  tone: 'high' | 'medium' | 'low' | 'unknown';
} {
  const normalized = normalizeStatus(value);
  if (normalized === 'high') return { label: '高优先级', normalized, tone: 'high' };
  if (normalized === 'medium') return { label: '中优先级', normalized, tone: 'medium' };
  if (normalized === 'low') return { label: '低优先级', normalized, tone: 'low' };
  return { label: value?.trim() || '未设置', normalized, tone: 'unknown' };
}

function stableSortedTasks(items: TaskListItem[], pendingCompletedIds: Set<string>): TaskListItem[] {
  const now = new Date();
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const leftCompleted = isCompletedTask(left.item) && !pendingCompletedIds.has(left.item.id);
      const rightCompleted = isCompletedTask(right.item) && !pendingCompletedIds.has(right.item.id);
      if (leftCompleted !== rightCompleted) return leftCompleted ? 1 : -1;

      const leftOverdue = isOverdueTask(left.item, now);
      const rightOverdue = isOverdueTask(right.item, now);
      if (leftOverdue !== rightOverdue) return leftOverdue ? -1 : 1;

      const leftPriority = priorityRank[priorityMeta(left.item.priority).normalized] ?? 3;
      const rightPriority = priorityRank[priorityMeta(right.item.priority).normalized] ?? 3;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;

      const leftDue = parseDueDate(dueValue(left.item))?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightDue = parseDueDate(dueValue(right.item))?.getTime() ?? Number.MAX_SAFE_INTEGER;
      if (leftDue !== rightDue) return leftDue - rightDue;

      return left.index - right.index;
    })
    .map(({ item }) => item);
}

function emptyTitle(filter: TaskStatusFilter): string {
  if (filter === 'completed') return '暂无已完成待办';
  if (filter === 'overdue') return '暂无超期待办';
  return '暂无待办任务';
}

function emptyDescription(filter: TaskStatusFilter): string {
  if (filter === 'completed') return '已完成状态来自真实任务数据。';
  if (filter === 'overdue') return '只有未完成、可解析截止时间且已过期的任务会显示在这里。';
  return '全部任务包含进行中、已完成和超期待办。';
}

export function TodoScreen({ onOpenMeeting, onOpenSearch, onOpenTask, taskOverrides = {} }: Props) {
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<TaskStatusFilter>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [taskHasMore, setTaskHasMore] = useState(false);
  const [taskTotal, setTaskTotal] = useState(0);
  const [updatingTaskIds, setUpdatingTaskIds] = useState<Set<string>>(() => new Set());
  const [pendingCompletedTaskIds, setPendingCompletedTaskIds] = useState<Set<string>>(() => new Set());

  async function loadTasks(mode: 'reset' | 'more' | 'refresh' = 'reset') {
    const isMore = mode === 'more';
    const offset = isMore ? tasks.length : 0;
    if (isMore) {
      if (loadingMore || !taskHasMore) return;
      setLoadingMore(true);
    } else if (mode === 'refresh') {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      if (!isMore) setError(null);
      setLoadMoreError(null);
      const response = await listTasks({
        limit: TASK_PAGE_SIZE,
        offset,
      });
      setTasks((current) => (isMore ? [...current, ...response.items] : response.items));
      setTaskHasMore(response.has_more);
      setTaskTotal(response.total);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : '待办任务加载失败，请稍后重试。';
      if (isMore) {
        setLoadMoreError(message);
      } else {
        setError(message);
      }
    } finally {
      if (isMore) setLoadingMore(false);
      else if (mode === 'refresh') setRefreshing(false);
      else setLoading(false);
    }
  }

  useEffect(() => {
    loadTasks('reset');
  }, []);

  const displayedTasks = useMemo(
    () => tasks.map((task) => ({ ...task, ...(taskOverrides[task.id] || {}) })),
    [taskOverrides, tasks],
  );

  const stats = useMemo(() => {
    const now = new Date();
    return displayedTasks.reduce(
      (acc, task) => {
        const completed = isCompletedTask(task) && !pendingCompletedTaskIds.has(task.id);
        const overdue = isOverdueTask(task, now);
        acc.all += 1;
        if (completed) acc.completed += 1;
        else if (overdue) acc.overdue += 1;
        return acc;
      },
      { all: 0, completed: 0, overdue: 0 },
    );
  }, [displayedTasks, pendingCompletedTaskIds]);

  const filteredTasks = useMemo(() => {
    const now = new Date();
    const filtered = displayedTasks.filter((task) => {
      const completed = isCompletedTask(task);
      const overdue = isOverdueTask(task, now);
      if (statusFilter === 'completed') return completed && !pendingCompletedTaskIds.has(task.id);
      if (statusFilter === 'overdue') return !completed && overdue;
      return true;
    });
    return stableSortedTasks(filtered, pendingCompletedTaskIds);
  }, [displayedTasks, pendingCompletedTaskIds, statusFilter]);

  function openSearch() {
    onOpenSearch?.();
  }

  function openTask(item: TaskListItem) {
    onOpenTask?.(item);
  }

  async function handleStatusPress(task: TaskListItem) {
    if (updatingTaskIds.has(task.id)) return;

    const previousTask = task;
    const nextStatus: 'open' | 'completed' = isCompletedTask(task) ? 'open' : 'completed';
    const completing = nextStatus === 'completed';
    setUpdatingTaskIds((current) => {
      const next = new Set(current);
      next.add(task.id);
      return next;
    });
    if (completing) {
      setPendingCompletedTaskIds((current) => {
        const next = new Set(current);
        next.add(task.id);
        return next;
      });
    }
    setTasks((current) => current.map((item) => (item.id === task.id ? { ...item, status: nextStatus } : item)));

    try {
      const updated = await updateTaskStatus(task.id, nextStatus);
      setTasks((current) => current.map((item) => (item.id === task.id ? updated : item)));
      if (completing) {
        setTimeout(() => {
          setPendingCompletedTaskIds((current) => {
            const next = new Set(current);
            next.delete(task.id);
            return next;
          });
        }, 300);
      }
    } catch (nextError) {
      setTasks((current) => current.map((item) => (item.id === task.id ? previousTask : item)));
      setPendingCompletedTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
      Alert.alert('更新失败', nextError instanceof Error ? nextError.message : '任务状态更新失败，请稍后重试。');
    } finally {
      setUpdatingTaskIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  function renderStats() {
    const items = [
      { key: 'all' as const, label: '全部任务', value: stats.all, color: '#2563eb' },
      { key: 'completed' as const, label: '已完成', value: stats.completed, color: '#059669' },
      { key: 'overdue' as const, label: '超期', value: stats.overdue, color: '#dc2626' },
    ];

    return (
      <View style={styles.statsGrid}>
        {items.map((item) => {
          const active = statusFilter === item.key;
          return (
            <Pressable
              key={item.key}
              onPress={() => setStatusFilter(active ? 'all' : item.key)}
              style={[styles.statCard, active ? styles.statCardActive : null]}
            >
              <Text style={[styles.statLabel, active ? styles.statLabelActive : null]}>{item.label}</Text>
              <Text style={[styles.statValue, { color: item.color }]}>{item.value}</Text>
            </Pressable>
          );
        })}
      </View>
    );
  }

  function renderHeader() {
    return (
      <View style={styles.headerContent}>
        <View style={styles.topBar}>
          <View>
            <Text style={styles.screenTitle}>我的待办</Text>
            <Text style={styles.screenSubtitle}>共 {taskTotal} 项真实待办</Text>
          </View>
          <Pressable onPress={openSearch} hitSlop={8} style={styles.iconButton}>
            <LucideIcon name="search" color="#2B6CFF" size={20} strokeWidth={2.3} />
          </Pressable>
        </View>

        {renderStats()}

        {error ? (
          <View style={styles.errorCard}>
            <LucideIcon name="triangle-alert" color="#dc2626" size={18} strokeWidth={2.3} />
            <View style={styles.errorBody}>
              <Text style={styles.errorTitle}>待办加载失败</Text>
              <Text style={styles.errorText}>{error}</Text>
            </View>
            <Pressable onPress={() => loadTasks('reset')} style={styles.retryButton}>
              <Text style={styles.retryText}>重试</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
    );
  }

  function renderTask({ item }: { item: TaskListItem }) {
    const completed = isCompletedTask(item);
    const overdue = isOverdueTask(item);
    const priority = priorityMeta(item.priority);
    const updating = updatingTaskIds.has(item.id);

    return (
      <Pressable onPress={() => openTask(item)} style={[styles.card, completed ? styles.cardDone : null]}>
        <Pressable
          onPress={(event) => {
            event.stopPropagation();
            handleStatusPress(item);
          }}
          disabled={updating}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel={`任务状态：${statusLabel(item.status)}`}
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

          <View style={styles.metaGrid}>
            <View style={styles.metaItem}>
              <LucideIcon name="calendar-days" color={overdue && !completed ? '#dc2626' : '#8b95a7'} size={14} strokeWidth={2.2} />
              <Text style={[styles.metaText, overdue && !completed ? styles.overdueText : null]}>{formatDueDate(dueValue(item))}</Text>
            </View>
          </View>

          <View style={styles.tagRow}>
            <View style={[styles.priorityTag, styles[`${priority.tone}PriorityTag`]]}>
              <Text style={[styles.priorityText, styles[`${priority.tone}PriorityText`]]}>{priority.label}</Text>
            </View>
          </View>
        </View>
      </Pressable>
    );
  }

  return (
    <View style={styles.container}>
      {loading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator color="#2B6CFF" />
          <Text style={styles.loadingText}>正在加载待办任务</Text>
        </View>
      ) : (
        <FlatList
          data={filteredTasks}
          keyExtractor={(item) => item.id}
          ListHeaderComponent={renderHeader}
          ListEmptyComponent={
            !error ? (
              <View style={styles.emptyCard}>
                <LucideIcon name="square-check-big" color="#8b95a7" size={28} strokeWidth={2.2} />
                <Text style={styles.emptyTitle}>{emptyTitle(statusFilter)}</Text>
                <Text style={styles.emptyText}>{emptyDescription(statusFilter)}</Text>
              </View>
            ) : null
          }
          contentContainerStyle={styles.listContent}
          renderItem={renderTask}
          onEndReached={() => loadTasks('more')}
          onEndReachedThreshold={0.25}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => loadTasks('refresh')} tintColor="#2B6CFF" />
          }
          ListFooterComponent={
            <View style={styles.footer}>
              {loadingMore ? <ActivityIndicator color="#2B6CFF" /> : null}
              {loadMoreError ? (
                <Pressable onPress={() => loadTasks('more')} style={styles.loadMoreError}>
                  <Text style={styles.loadMoreErrorText}>加载更多失败，点此重试</Text>
                </Pressable>
              ) : null}
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#F5F7FA',
    flex: 1,
  },
  listContent: {
    gap: 12,
    paddingBottom: 108,
    paddingHorizontal: 16,
    paddingTop: 18,
  },
  loadingWrap: {
    alignItems: 'center',
    flex: 1,
    gap: 10,
    justifyContent: 'center',
  },
  loadingText: {
    color: '#64748b',
    fontSize: 13,
    fontWeight: '700',
  },
  headerContent: {
    gap: 14,
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  screenTitle: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 0,
  },
  screenSubtitle: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
  },
  iconButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#e8eef7',
    borderRadius: 18,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    width: 40,
    elevation: 2,
  },
  statsGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  statCard: {
    backgroundColor: '#ffffff',
    borderColor: '#edf2f8',
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    minHeight: 78,
    paddingHorizontal: 12,
    paddingVertical: 13,
  },
  statCardActive: {
    borderColor: '#b9d2ff',
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.1,
    shadowRadius: 18,
    elevation: 2,
  },
  statLabel: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
  },
  statLabelActive: {
    color: '#2B6CFF',
  },
  statValue: {
    fontSize: 25,
    fontWeight: '900',
    marginTop: 8,
  },
  errorCard: {
    alignItems: 'flex-start',
    backgroundColor: '#fff1f2',
    borderColor: '#fecdd3',
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    padding: 12,
  },
  errorBody: {
    flex: 1,
    gap: 3,
  },
  errorTitle: {
    color: '#991b1b',
    fontSize: 13,
    fontWeight: '900',
  },
  errorText: {
    color: '#be123c',
    fontSize: 12,
    lineHeight: 18,
  },
  retryButton: {
    backgroundColor: '#ffffff',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  retryText: {
    color: '#be123c',
    fontSize: 12,
    fontWeight: '900',
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
  metaGrid: {
    gap: 7,
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
  tagRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  priorityTag: {
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
  emptyCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef2f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 9,
    marginTop: 4,
    padding: 28,
  },
  emptyTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  emptyText: {
    color: '#8b95a7',
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  footer: {
    minHeight: 28,
    paddingVertical: 8,
  },
  loadMoreError: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  loadMoreErrorText: {
    color: '#dc2626',
    fontSize: 12,
    fontWeight: '800',
  },
});
