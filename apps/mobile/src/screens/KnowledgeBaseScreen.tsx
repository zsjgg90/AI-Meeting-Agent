import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { getKnowledgeOverview, KnowledgeOverview } from '../api';
import { KnowledgeErrorState } from '../components/KnowledgeErrorState';
import { LucideIcon, LucideIconName } from '../components/LucideIcon';

type Props = {
  onOpenMeetings: () => void;
  onOpenDecisions: () => void;
  onOpenIssueRisks: () => void;
  onOpenSearch: (query?: string) => void;
};

type OverviewCountKey = 'meeting_count' | 'decision_count' | 'unresolved_issue_count' | 'risk_count' | 'all_count';

const entries: Array<{
  key: string;
  title: string;
  subtitle: string;
  icon: LucideIconName;
  color: string;
  bg: string;
  countKey?: OverviewCountKey;
}> = [
  { key: 'meetings', title: '会议记录', subtitle: '查看所有会议沉淀', icon: 'file-text', color: '#6657ff', bg: '#f0efff', countKey: 'meeting_count' },
  { key: 'decisions', title: '关键决策', subtitle: '查看团队重要决策', icon: 'circle-check-big', color: '#6657ff', bg: '#f0efff', countKey: 'decision_count' },
  { key: 'issues', title: '问题与风险', subtitle: '查看问题与风险', icon: 'triangle-alert', color: '#f97316', bg: '#fff7ed' },
  { key: 'all', title: '全部知识', subtitle: '搜索全部知识内容', icon: 'search', color: '#6657ff', bg: '#f0efff', countKey: 'all_count' },
];

export function KnowledgeBaseScreen({ onOpenMeetings, onOpenDecisions, onOpenIssueRisks, onOpenSearch }: Props) {
  const [overview, setOverview] = useState<KnowledgeOverview | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      refresh ? setRefreshing(true) : setLoading(true);
      setError(null);
      setOverview(await getKnowledgeOverview());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '知识库加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openEntry(key: string) {
    if (key === 'meetings') onOpenMeetings();
    if (key === 'decisions') onOpenDecisions();
    if (key === 'issues') onOpenIssueRisks();
    if (key === 'all') onOpenSearch();
  }

  function entryCount(entry: (typeof entries)[number]) {
    if (!overview) return 0;
    if (entry.key === 'issues') return `${overview.unresolved_issue_count} / ${overview.risk_count}`;
    return entry.countKey ? overview[entry.countKey] : 0;
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#6657ff" />}
    >
      <View style={styles.header}>
        <Text style={styles.title}>知识库</Text>
        <Text style={styles.subtitle}>沉淀会议知识，连接团队智慧</Text>
      </View>

      {loading ? <ActivityIndicator color="#6657ff" /> : null}
      {error && !loading ? <KnowledgeErrorState message={error} onRetry={() => load()} /> : null}

      {!error ? (
        <View style={styles.entryGrid}>
          {entries.map((entry) => (
            <Pressable key={entry.key} onPress={() => openEntry(entry.key)} style={styles.entryCard}>
              <View style={[styles.entryIcon, { backgroundColor: entry.bg }]}>
                <LucideIcon name={entry.icon} color={entry.color} size={24} strokeWidth={2.3} />
              </View>
              <View style={styles.entryText}>
                <Text style={styles.entryTitle}>{entry.title}</Text>
                <Text style={styles.entrySub}>{entry.subtitle}</Text>
              </View>
              <Text style={[styles.entryCount, { color: entry.color }]}>{entryCount(entry)}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={styles.searchPanel}>
        <Text style={styles.searchTitle}>知识搜索</Text>
        <View style={styles.searchBox}>
          <LucideIcon name="search" color="#8b95a7" size={20} strokeWidth={2.2} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => onOpenSearch(query)}
            placeholder="搜索会议、决策、问题、风险..."
            placeholderTextColor="#9ca3af"
            returnKeyType="search"
            style={styles.searchInput}
          />
          <Pressable onPress={() => onOpenSearch(query)} style={styles.searchButton}>
            <Text style={styles.searchButtonText}>搜索</Text>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f7f8fc' },
  content: { gap: 18, padding: 18, paddingBottom: 100 },
  header: { gap: 8, paddingTop: 10 },
  title: { color: '#111827', fontSize: 32, fontWeight: '900', letterSpacing: 0 },
  subtitle: { color: '#667085', fontSize: 14, fontWeight: '700', lineHeight: 21 },
  entryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  entryCard: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 12,
    minHeight: 148,
    padding: 14,
    width: '48%',
  },
  entryIcon: { alignItems: 'center', borderRadius: 14, height: 42, justifyContent: 'center', width: 42 },
  entryText: { flex: 1, gap: 5 },
  entryTitle: { color: '#111827', fontSize: 15, fontWeight: '900' },
  entrySub: { color: '#8b95a7', fontSize: 12, fontWeight: '700', lineHeight: 18 },
  entryCount: { fontSize: 13, fontWeight: '900' },
  searchPanel: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 20,
    borderWidth: 1,
    gap: 12,
    marginTop: 8,
    padding: 16,
  },
  searchTitle: { color: '#111827', fontSize: 17, fontWeight: '900' },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#f8f9ff',
    borderColor: '#6657ff',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 54,
    paddingHorizontal: 13,
  },
  searchInput: { color: '#111827', flex: 1, fontSize: 14, minHeight: 48 },
  searchButton: { backgroundColor: '#6657ff', borderRadius: 12, paddingHorizontal: 13, paddingVertical: 9 },
  searchButtonText: { color: '#ffffff', fontSize: 12, fontWeight: '900' },
});
