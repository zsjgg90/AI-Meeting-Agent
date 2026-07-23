import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { KnowledgeContentType } from '../api';

export type KnowledgeFilters = {
  content_type: KnowledgeContentType;
  dateRange: 'all' | 'today' | '7d' | '30d';
  meeting_type: string;
};

type Props = {
  visible: boolean;
  value: KnowledgeFilters;
  showContentType?: boolean;
  onApply: (value: KnowledgeFilters) => void;
  onClose: () => void;
};

const contentTypes: Array<{ key: KnowledgeContentType; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'meeting_summary', label: '会议总结' },
  { key: 'meeting_agenda', label: '会议议程' },
  { key: 'key_decision', label: '关键决策' },
  { key: 'action_item', label: '待办引用' },
  { key: 'unresolved_issue', label: '遗留问题' },
  { key: 'risk', label: '风险记录' },
  { key: 'transcript', label: '全文记录' },
];

const dateRanges = [
  { key: 'all', label: '全部' },
  { key: 'today', label: '今天' },
  { key: '7d', label: '最近 7 天' },
  { key: '30d', label: '最近 30 天' },
] as const;

export function KnowledgeFilterSheet({ visible, value, showContentType = true, onApply, onClose }: Props) {
  const next = { ...value };
  function applyPatch(patch: Partial<KnowledgeFilters>) {
    Object.assign(next, patch);
    onApply(next);
  }

  return (
    <Modal transparent visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <Text style={styles.title}>筛选条件</Text>
            <Pressable onPress={() => onApply({ content_type: 'all', dateRange: 'all', meeting_type: 'all' })}>
              <Text style={styles.reset}>重置</Text>
            </Pressable>
          </View>

          {showContentType ? (
            <View style={styles.section}>
              <Text style={styles.label}>内容类型</Text>
              <View style={styles.options}>
                {contentTypes.map((item) => (
                  <Pressable
                    key={item.key}
                    onPress={() => applyPatch({ content_type: item.key })}
                    style={[styles.chip, value.content_type === item.key ? styles.chipActive : null]}
                  >
                    <Text style={[styles.chipText, value.content_type === item.key ? styles.chipTextActive : null]}>{item.label}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}

          <View style={styles.section}>
            <Text style={styles.label}>会议时间</Text>
            <View style={styles.options}>
              {dateRanges.map((item) => (
                <Pressable
                  key={item.key}
                  onPress={() => applyPatch({ dateRange: item.key })}
                  style={[styles.chip, value.dateRange === item.key ? styles.chipActive : null]}
                >
                  <Text style={[styles.chipText, value.dateRange === item.key ? styles.chipTextActive : null]}>{item.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>

          <View style={styles.section}>
            <Text style={styles.label}>会议类型</Text>
            <View style={styles.disabledSelect}>
              <Text style={styles.disabledText}>全部类型</Text>
            </View>
          </View>

          <Pressable onPress={onClose} style={styles.applyButton}>
            <Text style={styles.applyText}>查看结果</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

export function filterDates(range: KnowledgeFilters['dateRange']): { date_from?: string; date_to?: string } {
  if (range === 'all') return {};
  const end = new Date();
  const start = new Date(end);
  if (range === 'today') start.setHours(0, 0, 0, 0);
  if (range === '7d') start.setDate(start.getDate() - 7);
  if (range === '30d') start.setDate(start.getDate() - 30);
  return { date_from: start.toISOString(), date_to: end.toISOString() };
}

export const defaultKnowledgeFilters: KnowledgeFilters = {
  content_type: 'all',
  dateRange: 'all',
  meeting_type: 'all',
};

const styles = StyleSheet.create({
  overlay: { backgroundColor: 'rgba(17, 24, 39, 0.35)', flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: '#ffffff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    gap: 18,
    padding: 18,
    paddingBottom: 28,
  },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  title: { color: '#111827', fontSize: 17, fontWeight: '900' },
  reset: { color: '#6657ff', fontSize: 13, fontWeight: '900' },
  section: { gap: 10 },
  label: { color: '#111827', fontSize: 13, fontWeight: '900' },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    backgroundColor: '#f8f9ff',
    borderColor: '#edf0f7',
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 8,
  },
  chipActive: { backgroundColor: '#6657ff', borderColor: '#6657ff' },
  chipText: { color: '#667085', fontSize: 12, fontWeight: '900' },
  chipTextActive: { color: '#ffffff' },
  disabledSelect: {
    backgroundColor: '#f8f9ff',
    borderColor: '#edf0f7',
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  disabledText: { color: '#8b95a7', fontSize: 13, fontWeight: '800' },
  applyButton: { alignItems: 'center', backgroundColor: '#6657ff', borderRadius: 14, minHeight: 46, justifyContent: 'center' },
  applyText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
});
