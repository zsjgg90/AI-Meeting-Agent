import { Pressable, StyleSheet, Text, View } from 'react-native';

import { KnowledgeItem, KnowledgeMeetingItem } from '../api';
import { LucideIcon } from './LucideIcon';

type Props = {
  item: KnowledgeItem;
  query?: string;
  onPress: (item: KnowledgeItem) => void;
};

const typeMeta: Record<string, { label: string; color: string; bg: string }> = {
  meeting_summary: { label: '会议总结', color: '#6657ff', bg: '#f0efff' },
  meeting_agenda: { label: '会议议程', color: '#6657ff', bg: '#f0efff' },
  key_decision: { label: '关键决策', color: '#6657ff', bg: '#f0efff' },
  action_item: { label: '待办引用', color: '#16a34a', bg: '#ecfdf3' },
  unresolved_issue: { label: '遗留问题', color: '#f97316', bg: '#fff7ed' },
  risk: { label: '风险记录', color: '#ef4444', bg: '#fff1f2' },
  transcript: { label: '全文证据', color: '#8b95a7', bg: '#f3f4f6' },
};

export function KnowledgeCard({ item, query, onPress }: Props) {
  const meta = typeMeta[item.content_type] || typeMeta.meeting_summary;
  return (
    <Pressable onPress={() => onPress(item)} style={styles.card}>
      <View style={styles.header}>
        <View style={[styles.badge, { backgroundColor: meta.bg }]}>
          <Text style={[styles.badgeText, { color: meta.color }]}>{meta.label}</Text>
        </View>
        <LucideIcon name="chevron-right" color="#9ca3af" size={17} strokeWidth={2.2} />
      </View>
      <HighlightedText text={item.content} query={query} style={styles.title} highlightStyle={styles.highlight} />
      <Text style={styles.meta}>{item.meeting_title}{item.meeting_date ? ` · ${formatDate(item.meeting_date)}` : ''}</Text>
      {item.evidence_text ? (
        <HighlightedText text={item.evidence_text} query={query} style={styles.evidence} highlightStyle={styles.highlight} />
      ) : null}
      {(item.speaker_label || item.start_time !== null || item.end_time !== null) ? (
        <Text style={styles.sourceMeta}>
          {[item.speaker_label, item.start_time !== null ? formatTime(item.start_time) : null].filter(Boolean).join(' · ')}
        </Text>
      ) : null}
    </Pressable>
  );
}

export function KnowledgeMeetingCard({ item, onPress }: { item: KnowledgeMeetingItem; onPress: (meetingId: string) => void }) {
  return (
    <Pressable onPress={() => onPress(item.meeting_id)} style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{item.title}</Text>
        <LucideIcon name="chevron-right" color="#9ca3af" size={17} strokeWidth={2.2} />
      </View>
      <Text style={styles.meta}>
        {item.meeting_id} · {item.meeting_time ? formatDate(item.meeting_time) : '未设置时间'}{item.duration ? ` · ${formatDuration(item.duration)}` : ''}
      </Text>
      <View style={styles.stats}>
        <Text style={styles.stat}>结论 {item.conclusion_count}</Text>
        <Text style={styles.stat}>待办 {item.action_count}</Text>
        <Text style={styles.stat}>问题 {item.unresolved_issue_count}</Text>
        <Text style={styles.stat}>风险 {item.risk_count}</Text>
      </View>
    </Pressable>
  );
}

function HighlightedText({ text, query, style, highlightStyle }: { text: string; query?: string; style: any; highlightStyle: any }) {
  const keyword = query?.trim();
  if (!keyword) return <Text style={style}>{text}</Text>;
  const index = text.toLowerCase().indexOf(keyword.toLowerCase());
  if (index < 0) return <Text style={style}>{text}</Text>;
  return (
    <Text style={style}>
      {text.slice(0, index)}
      <Text style={highlightStyle}>{text.slice(index, index + keyword.length)}</Text>
      {text.slice(index + keyword.length)}
    </Text>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function formatTime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
}

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return minutes ? `${minutes} 分 ${rest} 秒` : `${rest} 秒`;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 9,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.05,
    shadowRadius: 18,
    elevation: 2,
  },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  badge: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 },
  badgeText: { fontSize: 11, fontWeight: '900' },
  title: { color: '#111827', flex: 1, fontSize: 15, fontWeight: '900', lineHeight: 22 },
  meta: { color: '#8b95a7', fontSize: 12, fontWeight: '700', lineHeight: 18 },
  evidence: { color: '#4b5563', fontSize: 13, lineHeight: 21 },
  sourceMeta: { color: '#8b95a7', fontSize: 11, fontWeight: '800' },
  highlight: { backgroundColor: '#fff7ad', color: '#111827' },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  stat: {
    backgroundColor: '#f8f9ff',
    borderRadius: 999,
    color: '#667085',
    fontSize: 11,
    fontWeight: '900',
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
});
