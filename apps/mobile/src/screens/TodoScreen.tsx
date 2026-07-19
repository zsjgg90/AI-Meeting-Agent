import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { getMeetingSummary, listMeetings, listTasks, Meeting, TaskListItem } from '../api';

type TaskStatusFilter = 'all' | 'completed' | 'open';

type TodoTask = {
  id: string;
  meetingId: string;
  meetingTitle: string;
  task: string;
  status: string;
  completedAt?: number;
};

const filters: Array<{ key: TaskStatusFilter; label: string }> = [
  { key: 'all', label: '全部任务' },
  { key: 'completed', label: '已完成任务' },
  { key: 'open', label: '未完成任务' },
];

function actionTaskText(item: TaskListItem): string {
  return item.task || item.source_text || '未命名任务';
}

const TASK_PAGE_SIZE = 15;

function isNotFoundError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes('Not Found') || message.includes('404');
}

export function TodoScreen() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [tasks, setTasks] = useState<TodoTask[]>([]);
  const [completedTaskIds, setCompletedTaskIds] = useState<Record<string, boolean>>({});
  const [visualCompletedTaskIds, setVisualCompletedTaskIds] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState<TaskStatusFilter>('all');
  const [meetingFilterId, setMeetingFilterId] = useState<string>('all');
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meetingPickerOpen, setMeetingPickerOpen] = useState(false);
  const [taskHasMore, setTaskHasMore] = useState(false);
  const [taskTotal, setTaskTotal] = useState(0);
  const [meetingVisibleCount, setMeetingVisibleCount] = useState(10);

  async function loadTasks(mode: 'reset' | 'more' = 'reset') {
    const isMore = mode === 'more';
    if (isMore) {
      if (loadingMore || !taskHasMore) return;
      setLoadingMore(true);
    } else {
      setLoading(true);
    }

    try {
      setError(null);
      if (!isMore) {
        const nextMeetings = await listMeetings();
        setMeetings(nextMeetings);
      }

      const response = await listTasks({
        limit: TASK_PAGE_SIZE,
        offset: isMore ? tasks.length : 0,
        meeting_id: meetingFilterId,
        q: searchText,
      });
      const nextTasks = response.items.map((item): TodoTask => ({
        id: item.id,
        meetingId: item.meeting_id,
        meetingTitle: item.meeting_title,
        task: actionTaskText(item),
        status: item.status,
      }));
      const completedFromServer = response.items.reduce<Record<string, boolean>>((acc, item) => {
        if (item.status === 'completed' || item.status === 'done') {
          acc[item.id] = true;
        }
        return acc;
      }, {});
      setTasks((current) => (isMore ? [...current, ...nextTasks] : nextTasks));
      setCompletedTaskIds((current) => ({ ...completedFromServer, ...current }));
      setVisualCompletedTaskIds((current) => ({ ...completedFromServer, ...current }));
      setTaskHasMore(response.has_more);
      setTaskTotal(response.total);
    } catch (nextError) {
      if (!isMore && isNotFoundError(nextError)) {
        try {
          const nextMeetings = await listMeetings();
          setMeetings(nextMeetings);
          const results = await Promise.allSettled(
            nextMeetings.map(async (meeting) => {
              const summary = await getMeetingSummary(meeting.id);
              const actionItems = Array.isArray(summary.action_items) ? summary.action_items : [];
              return actionItems.map((item, index): TodoTask => ({
                id: item.id || `${meeting.id}-${index}`,
                meetingId: meeting.id,
                meetingTitle: meeting.title,
                task: item.task || item.source_text || '未命名任务',
                status: item.status,
              }));
            }),
          );
          const fallbackTasks = results.flatMap((result) => (result.status === 'fulfilled' ? result.value : []));
          setTasks(fallbackTasks);
          setTaskHasMore(false);
          setTaskTotal(fallbackTasks.length);
          return;
        } catch (fallbackError) {
          setError(fallbackError instanceof Error ? fallbackError.message : '待办任务加载失败。');
          return;
        }
      }
      setError(nextError instanceof Error ? nextError.message : '待办任务加载失败。');
    } finally {
      if (isMore) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  }

  const filteredTasks = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    const nextTasks = tasks.filter((task) => {
      const isCompleted = Boolean(completedTaskIds[task.id]);
      if (statusFilter === 'completed' && !isCompleted) return false;
      if (statusFilter === 'open' && isCompleted) return false;
      if (keyword && !`${task.task} ${task.meetingTitle}`.toLowerCase().includes(keyword)) return false;
      return true;
    });
    if (statusFilter !== 'completed') return nextTasks;
    return [...nextTasks].sort((left, right) => (right.completedAt || 0) - (left.completedAt || 0));
  }, [completedTaskIds, searchText, statusFilter, tasks]);

  const selectedMeetingTitle =
    meetingFilterId === 'all' ? '全部会议' : meetings.find((meeting) => meeting.id === meetingFilterId)?.title || '全部会议';
  const visibleMeetings = useMemo(() => meetings.slice(0, meetingVisibleCount), [meetingVisibleCount, meetings]);

  useEffect(() => {
    loadTasks('reset');
  }, [meetingFilterId, searchText]);

  function toggleTask(taskId: string) {
    const nextCompleted = !Boolean(completedTaskIds[taskId]);
    setVisualCompletedTaskIds((current) => ({ ...current, [taskId]: nextCompleted }));

    setTimeout(() => {
      setCompletedTaskIds((current) => ({ ...current, [taskId]: nextCompleted }));
      if (nextCompleted) {
        setTasks((current) =>
          current.map((task) => (task.id === taskId ? { ...task, completedAt: Date.now() } : task)),
        );
      }
    }, 500);
  }

  function openMeetingPicker() {
    setMeetingVisibleCount(10);
    setMeetingPickerOpen(true);
  }

  function renderHeader() {
    return (
      <View style={styles.headerContent}>
        <Text style={styles.title}>待办任务（{statusFilter === 'all' ? taskTotal : filteredTasks.length}）</Text>

        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput
            value={searchText}
            onChangeText={setSearchText}
            placeholder="请查询任务标题"
            placeholderTextColor="#a7adbb"
            style={styles.searchInput}
          />
        </View>

        <View style={styles.filterTabs}>
          {filters.map((filter) => {
            const isActive = statusFilter === filter.key;
            return (
              <Pressable
                key={filter.key}
                onPress={() => setStatusFilter(filter.key)}
                style={[styles.filterTab, isActive ? styles.filterTabActive : null]}
              >
                <Text style={[styles.filterText, isActive ? styles.filterTextActive : null]}>{filter.label}</Text>
              </Pressable>
            );
          })}
        </View>

        <Pressable onPress={openMeetingPicker} style={styles.meetingSelect}>
          <Text numberOfLines={1} style={styles.meetingSelectText}>
            {selectedMeetingTitle}
          </Text>
          <Text style={styles.meetingSelectArrow}>⌄</Text>
        </Pressable>

        {loading ? <ActivityIndicator color="#6657ff" /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>
    );
  }

  function renderTask({ item: task }: { item: TodoTask }) {
    const isCompleted = Boolean(visualCompletedTaskIds[task.id] ?? completedTaskIds[task.id]);
    return (
      <View style={styles.card}>
        <Pressable
          onPress={() => toggleTask(task.id)}
          hitSlop={8}
          style={[styles.checkbox, isCompleted ? styles.checkboxCompleted : null]}
        >
          {isCompleted ? <Text style={styles.checkboxCheck}>✓</Text> : null}
        </Pressable>
        <View style={styles.body}>
          <Text style={[styles.task, isCompleted ? styles.taskCompleted : null]}>{task.task}</Text>
          <Text numberOfLines={1} style={styles.meetingTitle}>
            所属会议：{task.meetingTitle}
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={filteredTasks}
        keyExtractor={(item) => item.id}
        ListHeaderComponent={renderHeader}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>暂无待办任务</Text>
              <Text style={styles.empty}>完成会议分析后，待办任务会自动汇总到这里。</Text>
            </View>
          ) : null
        }
        contentContainerStyle={styles.listContent}
        renderItem={renderTask}
        onEndReached={() => loadTasks('more')}
        onEndReachedThreshold={0.2}
        ListFooterComponent={loadingMore ? <ActivityIndicator color="#6657ff" /> : null}
      />

      <Modal transparent visible={meetingPickerOpen} animationType="fade" onRequestClose={() => setMeetingPickerOpen(false)}>
        <Pressable style={styles.modalMask} onPress={() => setMeetingPickerOpen(false)}>
          <Pressable style={styles.meetingModalCard}>
            <Text style={styles.meetingModalTitle}>选择会议</Text>
            <FlatList
              data={visibleMeetings}
              keyExtractor={(item) => item.id}
              ListHeaderComponent={
                <Pressable
                  onPress={() => {
                    setMeetingFilterId('all');
                    setMeetingPickerOpen(false);
                  }}
                  style={styles.meetingOption}
                >
                  <Text style={[styles.meetingOptionText, meetingFilterId === 'all' ? styles.meetingOptionActive : null]}>
                    全部会议
                  </Text>
                </Pressable>
              }
              renderItem={({ item: meeting }) => (
                <Pressable
                  onPress={() => {
                    setMeetingFilterId(meeting.id);
                    setMeetingPickerOpen(false);
                  }}
                  style={styles.meetingOption}
                >
                  <Text numberOfLines={1} style={[styles.meetingOptionText, meetingFilterId === meeting.id ? styles.meetingOptionActive : null]}>
                    {meeting.title}
                  </Text>
                </Pressable>
              )}
              onEndReached={() => {
                if (visibleMeetings.length < meetings.length) {
                  setMeetingVisibleCount((value) => value + 10);
                }
              }}
              onEndReachedThreshold={0.2}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  listContent: {
    gap: 14,
    paddingBottom: 96,
    paddingHorizontal: 18,
    paddingTop: 18,
  },
  headerContent: {
    gap: 12,
  },
  title: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
    marginBottom: 10,
    textAlign: 'center',
  },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  searchIcon: {
    color: '#8b95a7',
    fontSize: 24,
    fontWeight: '900',
  },
  searchInput: {
    color: '#111827',
    flex: 1,
    fontSize: 14,
    minHeight: 44,
    padding: 0,
  },
  meetingSelect: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 4,
    justifyContent: 'center',
    alignSelf: 'flex-start',
    height: 38,
    paddingHorizontal: 11,
  },
  meetingSelectText: {
    color: '#111827',
    fontSize: 11,
    fontWeight: '800',
    includeFontPadding: false,
    lineHeight: 14,
  },
  meetingSelectArrow: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '900',
    includeFontPadding: false,
    lineHeight: 13,
    textAlignVertical: 'center',
  },
  modalMask: {
    backgroundColor: 'rgba(17, 24, 39, 0.36)',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 26,
  },
  meetingModalCard: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 22,
    borderWidth: 1,
    maxHeight: 420,
    overflow: 'hidden',
    paddingTop: 14,
  },
  meetingModalTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
    paddingBottom: 10,
    paddingHorizontal: 14,
  },
  meetingOption: {
    borderBottomColor: '#f1f3f8',
    borderBottomWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  meetingOptionText: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '800',
  },
  meetingOptionActive: {
    color: '#6657ff',
  },
  filterTabs: {
    flexDirection: 'row',
    gap: 8,
  },
  filterTab: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 999,
    borderWidth: 1,
    flex: 1,
    minHeight: 42,
    justifyContent: 'center',
  },
  filterTabActive: {
    backgroundColor: '#f0efff',
    borderColor: '#d8d4ff',
  },
  filterText: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '900',
  },
  filterTextActive: {
    color: '#6657ff',
  },
  list: {
    gap: 12,
  },
  card: {
    alignItems: 'flex-start',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 2,
  },
  checkbox: {
    alignItems: 'center',
    borderColor: '#6657ff',
    borderRadius: 5,
    borderWidth: 1,
    height: 18,
    justifyContent: 'center',
    marginTop: 2,
    width: 18,
  },
  checkboxCompleted: {
    backgroundColor: '#6657ff',
  },
  checkboxCheck: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 14,
  },
  body: {
    flex: 1,
    gap: 7,
  },
  task: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '900',
    lineHeight: 20,
  },
  taskCompleted: {
    color: '#9ca3af',
    textDecorationLine: 'line-through',
  },
  meetingTitle: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
  },
  empty: {
    color: '#8b95a7',
    lineHeight: 22,
    textAlign: 'center',
  },
  emptyCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    gap: 8,
    marginTop: 10,
    padding: 28,
  },
  emptyTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  error: {
    color: '#ef4444',
    backgroundColor: '#fff1f2',
    borderColor: '#fecdd3',
    borderRadius: 14,
    borderWidth: 1,
    lineHeight: 18,
    padding: 12,
    textAlign: 'center',
  },
});
