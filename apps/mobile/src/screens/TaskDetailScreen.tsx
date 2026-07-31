import * as DocumentPicker from 'expo-document-picker';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Linking,
  Modal,
  Platform,
  Pressable,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { getMeeting, listTasks, taskAttachmentUrl, TaskListItem, updateTask, updateTaskStatus, uploadTaskAttachment } from '../api';
import { LucideIcon, LucideIconName } from '../components/LucideIcon';

type Props = {
  initialTask: TaskListItem | null;
  onBack: () => void;
  onTaskChange?: (task: TaskListItem) => void;
  onOpenMeeting: (options: {
    meetingId: string;
    initialTab?: 'actions';
    sourceSegmentId?: string | null;
    evidenceText?: string | null;
  }) => void;
};

type Attachment = NonNullable<TaskListItem['attachments']>[number];
type PriorityValue = 'high' | 'medium' | 'low';
type ReminderOffset = 60 | 180 | 300;

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

function taskDescriptionValue(item: TaskListItem): string {
  return normalizeText(item.description) || normalizeText(item.content) || normalizeText(item.details);
}

function ownerValue(item: TaskListItem): string {
  return (
    normalizeText(item.owner) ||
    normalizeText(item.owner_name) ||
    normalizeText(item.assignee) ||
    normalizeText(item.responsible_person)
  );
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

function formatDateTimeForInput(value: Date): string {
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  const h = String(value.getHours()).padStart(2, '0');
  const minute = String(value.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${minute}`;
}

function normalizeDueDraft(value: string): string {
  const raw = normalizeText(value);
  const shortDateTime = raw.match(/^(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$/);
  if (shortDateTime) {
    const [, month, day, hour, minute] = shortDateTime;
    const year = new Date().getFullYear();
    return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')} ${hour.padStart(2, '0')}:${minute}`;
  }
  return raw;
}

function isOverdueTask(item: TaskListItem): boolean {
  if (isCompletedTask(item)) return false;
  const due = parseDueDate(dueValue(item));
  return Boolean(due && due.getTime() < Date.now());
}

function priorityMeta(value: string | null | undefined): {
  label: string;
  tone: PriorityValue | 'unknown';
} {
  const normalized = normalizeStatus(value);
  if (normalized === 'high') return { label: '高优先级', tone: 'high' };
  if (normalized === 'medium') return { label: '中优先级', tone: 'medium' };
  if (normalized === 'low') return { label: '低优先级', tone: 'low' };
  return { label: '未设置', tone: 'unknown' };
}

function formatFileSize(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '大小未知';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function attachmentName(item: Attachment): string {
  const remote = item as Attachment;
  return normalizeText(remote.filename) || normalizeText(item.name) || '未命名附件';
}

function attachmentType(item: Attachment): string {
  const remote = item as Attachment;
  return normalizeText(item.content_type) || normalizeText(remote.file_type) || '未知类型';
}

function attachmentSize(item: Attachment): string {
  const remote = item as Attachment;
  return formatFileSize(item.file_size_bytes ?? remote.size);
}

function attachmentUrl(taskId: string, item: Attachment): string {
  const url = normalizeText(item.download_url) || normalizeText(item.url);
  if (url.startsWith('/')) return taskAttachmentUrl(taskId, item.id || '');
  if (url) return url;
  return item.id ? taskAttachmentUrl(taskId, item.id) : '';
}

function reminderLabel(value: number | null | undefined): string {
  if (value === 60) return '截止前 1 小时';
  if (value === 180) return '截止前 3 小时';
  if (value === 300) return '截止前 5 小时';
  return '未设置提醒';
}

export function TaskDetailScreen({ initialTask, onBack, onTaskChange }: Props) {
  const [task, setTask] = useState<TaskListItem | null>(initialTask);
  const [loading, setLoading] = useState(!initialTask);
  const [refreshing, setRefreshing] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [savingField, setSavingField] = useState<string | null>(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceMeetingTitle, setSourceMeetingTitle] = useState<string | null>(initialTask?.meeting_title || null);
  const [duePickerOpen, setDuePickerOpen] = useState(false);
  const [dueDraft, setDueDraft] = useState('');
  const [priorityPickerOpen, setPriorityPickerOpen] = useState(false);
  const [reminderPickerOpen, setReminderPickerOpen] = useState(false);

  async function refreshTask(seed: TaskListItem | null) {
    if (!seed) {
      setLoading(false);
      setError('任务数据不可用，请返回列表后重试。');
      return;
    }

    const query = taskTitle(seed);
    setRefreshing(true);
    try {
      const response = await listTasks({
        meeting_id: seed.meeting_id,
        q: query,
        limit: 15,
        offset: 0,
      });
      const latest = response.items.find((item) => item.id === seed.id);
      if (latest) {
        setTask((current) => ({ ...current, ...latest }));
        setError(null);
      } else {
        setError('未能刷新到最新任务详情，当前显示入口传入的数据。');
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '任务详情刷新失败，请稍后重试。');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function loadSourceMeeting(seed: TaskListItem | null) {
    const meetingId = normalizeText(seed?.meeting_id);
    if (!meetingId) {
      setSourceMeetingTitle(null);
      return;
    }
    try {
      const meeting = await getMeeting(meetingId);
      setSourceMeetingTitle(meeting.title);
    } catch {
      setSourceMeetingTitle(null);
    }
  }

  useEffect(() => {
    setTask(initialTask);
    setSourceMeetingTitle(initialTask?.meeting_title || null);
    setLoading(!initialTask);
    setError(null);
    refreshTask(initialTask);
    loadSourceMeeting(initialTask);
  }, [initialTask?.id]);

  const attachments = useMemo(
    () => (Array.isArray(task?.attachments) ? task.attachments : []),
    [task?.attachments],
  );

  function applyTaskPatch(patch: Partial<TaskListItem>, options?: { sync?: boolean }) {
    setTask((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      if (options?.sync) onTaskChange?.(next);
      return next;
    });
  }

  async function persistTaskPatch(patch: Parameters<typeof updateTask>[1], field: string) {
    if (!task) return;
    const previousTask = task;
    const { task: patchTask, ...restPatch } = patch;
    const optimisticPatch: Partial<TaskListItem> = { ...restPatch };
    if ('task' in patch) optimisticPatch.task = patchTask || previousTask.task;
    const optimistic = { ...task, ...optimisticPatch };
    setTask(optimistic);
    onTaskChange?.(optimistic);
    setSavingField(field);
    try {
      const updated = await updateTask(task.id, patch);
      setTask(updated);
      onTaskChange?.(updated);
      setError(null);
    } catch (nextError) {
      setTask(previousTask);
      onTaskChange?.(previousTask);
      Alert.alert('保存失败', nextError instanceof Error ? nextError.message : '任务更新失败，请稍后重试。');
    } finally {
      setSavingField(null);
    }
  }

  async function handleStatusPress() {
    if (!task || updatingStatus) return;
    const previousTask = task;
    const nextStatus: 'open' | 'completed' = isCompletedTask(task) ? 'open' : 'completed';
    const optimistic = { ...task, status: nextStatus };
    setUpdatingStatus(true);
    setTask(optimistic);
    onTaskChange?.(optimistic);
    try {
      const updated = await updateTaskStatus(task.id, nextStatus);
      const next = { ...updated, ...optimistic, status: updated.status };
      setTask(next);
      onTaskChange?.(next);
    } catch (nextError) {
      setTask(previousTask);
      onTaskChange?.(previousTask);
      Alert.alert('更新失败', nextError instanceof Error ? nextError.message : '任务状态更新失败，请稍后重试。');
    } finally {
      setUpdatingStatus(false);
    }
  }

  async function handlePickAttachment() {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        copyToCacheDirectory: true,
        multiple: true,
        type: [
          'application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'image/*',
          'text/markdown',
          'text/plain',
        ],
      });
      if (result.canceled) return;
      if (!task) return;
      setUploadingAttachment(true);
      const uploadedAttachments = [];
      for (const asset of result.assets) {
        const uploaded = await uploadTaskAttachment(task.id, {
          uri: asset.uri,
          name: asset.name,
          type: asset.mimeType || null,
        });
        uploadedAttachments.push(uploaded);
      }
      applyTaskPatch({ attachments: [...attachments, ...uploadedAttachments] }, { sync: true });
    } catch (nextError) {
      Alert.alert('附件上传失败', nextError instanceof Error ? nextError.message : '无法上传选择的文件，请稍后重试。');
    } finally {
      setUploadingAttachment(false);
    }
  }

  async function handleOpenAttachment(item: Attachment) {
    const url = task ? attachmentUrl(task.id, item) : '';
    if (!url) {
      Alert.alert('附件不可打开', '当前附件没有可用的打开地址。');
      return;
    }
    try {
      const supported = await Linking.canOpenURL(url);
      if (!supported) throw new Error('unsupported_url');
      await Linking.openURL(url);
    } catch {
      Alert.alert('附件加载失败', '无法打开该附件，请稍后重试。');
    }
  }

  function openDuePicker() {
    const parsed = task ? parseDueDate(dueValue(task)) : null;
    setDueDraft(parsed ? formatDateTimeForInput(parsed) : '');
    setDuePickerOpen(true);
  }

  function applyDueDraft(value = dueDraft) {
    const normalized = normalizeDueDraft(value);
    persistTaskPatch({ due_date: normalized || null }, 'due_date');
    setDuePickerOpen(false);
  }

  function applyPriority(value: PriorityValue) {
    persistTaskPatch({ priority: value }, 'priority');
    setPriorityPickerOpen(false);
  }

  function applyReminder(value: ReminderOffset) {
    persistTaskPatch({ reminder_offset_minutes: value, reminder_channel: 'sms' }, 'reminder');
    setReminderPickerOpen(false);
  }

  function renderSectionHeader(icon: LucideIconName, title: string) {
    return (
      <View style={styles.sectionHeader}>
        <LucideIcon name={icon} color="#0F172A" size={16} strokeWidth={2.2} />
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
    );
  }

  function renderInfoRow(label: string, content: React.ReactNode, onPress?: () => void) {
    const body = (
      <>
        <Text style={styles.rowLabel}>{label}</Text>
        <View style={styles.rowValueWrap}>{content}</View>
        {onPress ? <LucideIcon name="chevron-right" color="#CBD5E1" size={17} strokeWidth={2.2} /> : null}
      </>
    );
    if (!onPress) return <View style={styles.infoRow}>{body}</View>;
    return (
      <Pressable onPress={onPress} style={styles.infoRow}>
        {body}
      </Pressable>
    );
  }

  function renderAttachment(item: Attachment, index: number) {
    return (
      <Pressable key={item.id || `${attachmentName(item)}-${index}`} onPress={() => handleOpenAttachment(item)} style={styles.attachmentCard}>
        <View style={styles.attachmentIcon}>
          <LucideIcon name="file-text" color="#2B6CFF" size={18} strokeWidth={2.2} />
        </View>
        <View style={styles.attachmentBody}>
          <Text numberOfLines={1} style={styles.attachmentName}>{attachmentName(item)}</Text>
          <Text style={styles.attachmentMeta}>{attachmentType(item)} | {attachmentSize(item)}</Text>
        </View>
        <LucideIcon name="chevron-right" color="#CBD5E1" size={17} strokeWidth={2.2} />
      </Pressable>
    );
  }

  function renderContent() {
    if (loading) {
      return (
        <View style={styles.stateCard}>
          <ActivityIndicator color="#2B6CFF" />
          <Text style={styles.stateTitle}>正在加载任务详情</Text>
        </View>
      );
    }

    if (!task) {
      return (
        <View style={styles.stateCard}>
          <LucideIcon name="triangle-alert" color="#DC2626" size={28} strokeWidth={2.2} />
          <Text style={styles.stateTitle}>任务详情不可用</Text>
          <Text style={styles.stateText}>{error || '没有可展示的任务数据。'}</Text>
          <Pressable onPress={() => refreshTask(initialTask)} style={styles.retryButton}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      );
    }

    const completed = isCompletedTask(task);
    const overdue = isOverdueTask(task);
    const priority = priorityMeta(task.priority);
    const sourceText = normalizeText(task.source_text) || normalizeText(task.source);

    return (
      <View style={styles.pageBody}>
        <View style={styles.taskCard}>
          <Text style={styles.currentLabel}>当前任务</Text>
          <View style={styles.taskTitleRow}>
            <Pressable onPress={handleStatusPress} disabled={updatingStatus} hitSlop={10} style={styles.statusButton}>
              {updatingStatus ? (
                <ActivityIndicator color="#2B6CFF" size="small" />
              ) : completed ? (
                <LucideIcon name="square-check-big" color="#10B981" size={25} strokeWidth={2.4} />
              ) : (
                <View style={[styles.emptySquare, overdue ? styles.emptySquareOverdue : null]} />
              )}
            </Pressable>
            <TextInput
              value={taskTitle(task)}
              onChangeText={(value) => applyTaskPatch({ task: value }, { sync: true })}
              onBlur={() => persistTaskPatch({ task: taskTitle(task) }, 'task')}
              onSubmitEditing={() => persistTaskPatch({ task: taskTitle(task) }, 'task')}
              placeholder="输入任务标题"
              placeholderTextColor="#94A3B8"
              multiline
              style={[styles.titleInput, completed ? styles.taskTitleDone : null]}
            />
          </View>
          <TextInput
            value={taskDescriptionValue(task)}
            onChangeText={(value) => applyTaskPatch({ description: value })}
            onBlur={() => persistTaskPatch({ description: taskDescriptionValue(task) || null }, 'description')}
            placeholder="暂无任务描述"
            placeholderTextColor="#8B95A7"
            multiline
            style={styles.descriptionInput}
          />
          {refreshing ? (
            <View style={styles.refreshRow}>
              <ActivityIndicator color="#94A3B8" size="small" />
              <Text style={styles.refreshText}>同步最新任务数据</Text>
            </View>
          ) : null}
          {savingField ? (
            <View style={styles.refreshRow}>
              <ActivityIndicator color="#94A3B8" size="small" />
              <Text style={styles.refreshText}>正在保存</Text>
            </View>
          ) : null}
          {error ? (
            <View style={styles.inlineNotice}>
              <LucideIcon name="info" color="#B45309" size={16} strokeWidth={2.2} />
              <Text style={styles.inlineNoticeText}>{error}</Text>
            </View>
          ) : null}
        </View>

        {renderSectionHeader('settings', '基本信息')}
        <View style={styles.groupCard}>
          {renderInfoRow(
            '负责人',
            <TextInput
              value={ownerValue(task)}
              onChangeText={(value) => applyTaskPatch({ owner: value || null, owner_name: null }, { sync: true })}
              onBlur={() => persistTaskPatch({ owner: ownerValue(task) || null }, 'owner')}
              placeholder="未指定负责人"
              placeholderTextColor="#94A3B8"
              style={styles.rowInput}
            />,
          )}
          {renderInfoRow(
            '截止日期',
            <View style={styles.rowValueInline}>
              <Text style={[styles.rowText, overdue ? styles.overdueText : null]}>{formatDueDate(dueValue(task))}</Text>
              {overdue ? <Text style={styles.overdueBadge}>超期</Text> : null}
              <Pressable onPress={openDuePicker} hitSlop={10} style={styles.inlineIconButton}>
                <LucideIcon name="calendar-days" color={overdue ? '#DC2626' : '#334155'} size={16} strokeWidth={2.2} />
              </Pressable>
            </View>,
          )}
          {renderInfoRow(
            '优先级',
            <Text style={[styles.rowText, styles[`${priority.tone}PriorityText`]]}>{priority.label}</Text>,
            () => setPriorityPickerOpen(true),
          )}
          {renderInfoRow(
            '关联会议',
            sourceMeetingTitle ? (
              <Text numberOfLines={1} style={styles.mutedRowText}>{sourceMeetingTitle}</Text>
            ) : (
              <Text style={styles.unavailableText}>来源会议不可用</Text>
            ),
          )}
          <View style={styles.evidenceBlock}>
            <Text style={styles.rowLabel}>来源证据</Text>
            <Text style={styles.evidenceText}>{sourceText || '暂无来源证据'}</Text>
          </View>
        </View>

        {renderSectionHeader('bell', '提醒设置')}
        <View style={styles.groupCard}>
          {renderInfoRow('提醒时间', <Text style={styles.rowText}>{reminderLabel(task.reminder_offset_minutes)}</Text>, () => setReminderPickerOpen(true))}
          {renderInfoRow('重复', <Text style={styles.rowText}>短信通知</Text>)}
        </View>

        {renderSectionHeader('file-text', `附件 (${attachments.length})`)}
        <View style={styles.attachmentSection}>
          {attachments.length ? (
            <View style={styles.attachmentList}>{attachments.map(renderAttachment)}</View>
          ) : (
            <Text style={styles.emptyAttachmentText}>暂无附件</Text>
          )}
          <Pressable onPress={handlePickAttachment} disabled={uploadingAttachment} style={styles.uploadDropzone}>
            {uploadingAttachment ? (
              <ActivityIndicator color="#2B6CFF" />
            ) : (
              <Text style={styles.uploadText}>+ 上传更多附件</Text>
            )}
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.navHeader}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.navButton}>
          <LucideIcon name="chevron-left" color="#111827" size={25} strokeWidth={2.4} />
        </Pressable>
        <Text style={styles.navTitle}>任务详情</Text>
        <View style={styles.navButton} />
      </View>
      <FlatList
        data={[0]}
        keyExtractor={(item) => String(item)}
        keyboardShouldPersistTaps="handled"
        renderItem={() => renderContent()}
        contentContainerStyle={styles.content}
        ListFooterComponent={<View style={styles.safeBottom} />}
      />
      <Modal transparent visible={duePickerOpen} animationType="fade" onRequestClose={() => setDuePickerOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>调整截止时间</Text>
            <TextInput
              value={dueDraft}
              onChangeText={setDueDraft}
              placeholder="例如 2026-07-26 14:00"
              placeholderTextColor="#94A3B8"
              style={styles.modalInput}
            />
            <View style={styles.modalActions}>
              <Pressable onPress={() => setDuePickerOpen(false)} style={[styles.modalButton, styles.modalCancel]}>
                <Text style={styles.modalCancelText}>取消</Text>
              </Pressable>
              <Pressable onPress={() => applyDueDraft()} style={[styles.modalButton, styles.modalSave]}>
                <Text style={styles.modalSaveText}>保存</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
      <Modal transparent visible={priorityPickerOpen} animationType="fade" onRequestClose={() => setPriorityPickerOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>调整优先级</Text>
            {[
              { value: 'high' as const, label: '高优先级' },
              { value: 'medium' as const, label: '中优先级' },
              { value: 'low' as const, label: '低优先级' },
            ].map((item) => (
              <Pressable key={item.value} onPress={() => applyPriority(item.value)} style={styles.priorityOption}>
                <Text style={[styles.priorityOptionText, styles[`${item.value}PriorityText`]]}>{item.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </Modal>
      <Modal transparent visible={reminderPickerOpen} animationType="fade" onRequestClose={() => setReminderPickerOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>提醒时间</Text>
            {[
              { value: 60 as const, label: '截止前 1 小时' },
              { value: 180 as const, label: '截止前 3 小时' },
              { value: 300 as const, label: '截止前 5 小时' },
            ].map((item) => (
              <Pressable key={item.value} onPress={() => applyReminder(item.value)} style={styles.priorityOption}>
                <Text style={styles.priorityOptionText}>{item.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: '#F3F6FA',
    flex: 1,
    paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight || 0 : 0,
  },
  navHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 56,
    paddingHorizontal: 16,
  },
  navButton: {
    alignItems: 'center',
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  navTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
    textAlign: 'center',
  },
  content: {
    paddingBottom: 18,
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  pageBody: {
    gap: 18,
  },
  taskCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E8EEF7',
    borderRadius: 22,
    borderWidth: 1,
    gap: 12,
    paddingHorizontal: 20,
    paddingVertical: 22,
    shadowColor: '#64748B',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.05,
    shadowRadius: 18,
    elevation: 2,
  },
  currentLabel: {
    color: '#8B95A7',
    fontSize: 12,
    fontWeight: '900',
  },
  taskTitleRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  statusButton: {
    alignItems: 'center',
    height: 30,
    justifyContent: 'center',
    marginTop: 1,
    width: 30,
  },
  emptySquare: {
    borderColor: '#CBD5E1',
    borderRadius: 6,
    borderWidth: 2,
    height: 23,
    width: 23,
  },
  emptySquareOverdue: {
    borderColor: '#F87171',
  },
  titleInput: {
    color: '#07112A',
    flex: 1,
    fontSize: 20,
    fontWeight: '900',
    lineHeight: 28,
    minHeight: 32,
    padding: 0,
    textAlignVertical: 'top',
  },
  taskTitleDone: {
    color: '#94A3B8',
    textDecorationLine: 'line-through',
  },
  descriptionInput: {
    color: '#5F6B7A',
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 23,
    minHeight: 62,
    padding: 0,
    textAlignVertical: 'top',
  },
  refreshRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  refreshText: {
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '800',
  },
  inlineNotice: {
    alignItems: 'flex-start',
    backgroundColor: '#FFFBEB',
    borderColor: '#FDE68A',
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    padding: 10,
  },
  inlineNoticeText: {
    color: '#92400E',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
  },
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 2,
    paddingHorizontal: 4,
  },
  sectionTitle: {
    color: '#0F172A',
    fontSize: 15,
    fontWeight: '900',
  },
  groupCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    overflow: 'hidden',
  },
  infoRow: {
    alignItems: 'center',
    borderBottomColor: '#EEF2F7',
    borderBottomWidth: 1,
    flexDirection: 'row',
    minHeight: 56,
    paddingHorizontal: 20,
  },
  rowLabel: {
    color: '#64748B',
    fontSize: 14,
    fontWeight: '700',
    width: 86,
  },
  rowValueWrap: {
    alignItems: 'flex-end',
    flex: 1,
    minWidth: 0,
  },
  rowInput: {
    color: '#07112A',
    fontSize: 15,
    fontWeight: '800',
    minHeight: 40,
    minWidth: 120,
    padding: 0,
    textAlign: 'right',
  },
  rowText: {
    color: '#07112A',
    fontSize: 15,
    fontWeight: '800',
  },
  mutedRowText: {
    color: '#8B95A7',
    flexShrink: 1,
    fontSize: 15,
    fontWeight: '800',
    textAlign: 'right',
  },
  rowValueInline: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    justifyContent: 'flex-end',
  },
  inlineIconButton: {
    alignItems: 'center',
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  unavailableText: {
    color: '#94A3B8',
    fontSize: 15,
    fontWeight: '800',
  },
  evidenceBlock: {
    gap: 8,
    paddingHorizontal: 20,
    paddingVertical: 14,
  },
  evidenceText: {
    color: '#64748B',
    fontSize: 13,
    lineHeight: 20,
  },
  overdueText: {
    color: '#DC2626',
  },
  overdueBadge: {
    backgroundColor: '#FEF2F2',
    borderRadius: 8,
    color: '#DC2626',
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  highPriorityText: {
    color: '#DC2626',
  },
  mediumPriorityText: {
    color: '#2563EB',
  },
  lowPriorityText: {
    color: '#64748B',
  },
  unknownPriorityText: {
    color: '#94A3B8',
  },
  attachmentSection: {
    gap: 10,
  },
  attachmentList: {
    gap: 10,
  },
  attachmentCard: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    flexDirection: 'row',
    gap: 10,
    minHeight: 52,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  attachmentIcon: {
    alignItems: 'center',
    backgroundColor: '#EFF6FF',
    borderRadius: 8,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  attachmentBody: {
    flex: 1,
    minWidth: 0,
  },
  attachmentName: {
    color: '#1F2937',
    fontSize: 14,
    fontWeight: '900',
  },
  attachmentMeta: {
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
  uploadDropzone: {
    alignItems: 'center',
    borderColor: '#D8DEE8',
    borderRadius: 14,
    borderStyle: 'dashed',
    borderWidth: 1.5,
    justifyContent: 'center',
    minHeight: 54,
  },
  uploadText: {
    color: '#8B95A7',
    fontSize: 14,
    fontWeight: '900',
  },
  localOnlyText: {
    color: '#94A3B8',
    fontSize: 12,
    lineHeight: 18,
    paddingHorizontal: 4,
  },
  emptyAttachmentText: {
    color: '#94A3B8',
    fontSize: 13,
    fontWeight: '800',
    paddingHorizontal: 4,
  },
  stateCard: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#EEF2F7',
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    padding: 28,
  },
  stateTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  stateText: {
    color: '#64748B',
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
  },
  retryButton: {
    backgroundColor: '#EEF4FF',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  retryText: {
    color: '#2B6CFF',
    fontSize: 13,
    fontWeight: '900',
  },
  safeBottom: {
    height: 22,
  },
  modalOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(15, 23, 42, 0.32)',
    flex: 1,
    justifyContent: 'center',
    padding: 18,
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    gap: 14,
    maxWidth: 420,
    padding: 18,
    width: '100%',
  },
  modalTitle: {
    color: '#111827',
    fontSize: 17,
    fontWeight: '900',
  },
  modalInput: {
    backgroundColor: '#F8FAFC',
    borderColor: '#E2E8F0',
    borderRadius: 12,
    borderWidth: 1,
    color: '#111827',
    fontSize: 15,
    fontWeight: '800',
    minHeight: 46,
    paddingHorizontal: 12,
  },
  modalActions: {
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'flex-end',
  },
  modalButton: {
    alignItems: 'center',
    borderRadius: 12,
    minWidth: 82,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  modalCancel: {
    backgroundColor: '#F1F5F9',
  },
  modalSave: {
    backgroundColor: '#2B6CFF',
  },
  modalCancelText: {
    color: '#64748B',
    fontSize: 14,
    fontWeight: '900',
  },
  modalSaveText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '900',
  },
  priorityOption: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  priorityOptionText: {
    fontSize: 15,
    fontWeight: '900',
  },
});
