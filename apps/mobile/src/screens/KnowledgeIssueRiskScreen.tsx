import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';

import { KnowledgeItem, listKnowledgeIssues, listKnowledgeRisks } from '../api';
import { KnowledgeCard } from '../components/KnowledgeCard';
import { KnowledgeEmptyState } from '../components/KnowledgeEmptyState';
import { KnowledgeErrorState } from '../components/KnowledgeErrorState';
import { KnowledgeListSkeleton } from '../components/KnowledgeListSkeleton';
import { LucideIcon } from '../components/LucideIcon';
import { defaultKnowledgeFilters, filterDates, KnowledgeFilterSheet, KnowledgeFilters } from './KnowledgeFilterSheet';

type Props = {
  onBack: () => void;
  onOpenSource: (item: KnowledgeItem) => void;
};

type Tab = 'issues' | 'risks';
const PAGE_SIZE = 20;

export function KnowledgeIssueRiskScreen({ onBack, onOpenSource }: Props) {
  const [tab, setTab] = useState<Tab>('issues');
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<KnowledgeFilters>(defaultKnowledgeFilters);
  const [filterVisible, setFilterVisible] = useState(false);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (mode: 'initial' | 'refresh' | 'more' = 'initial') => {
    if (mode === 'more' && (loadingMore || !hasMore)) return;
    const offset = mode === 'more' ? items.length : 0;
    try {
      if (mode === 'refresh') setRefreshing(true);
      else if (mode === 'more') setLoadingMore(true);
      else setLoading(true);
      setError(null);
      const fetcher = tab === 'issues' ? listKnowledgeIssues : listKnowledgeRisks;
      const response = await fetcher({ query, meeting_type: filters.meeting_type, ...filterDates(filters.dateRange), limit: PAGE_SIZE, offset });
      setItems((current) => (mode === 'more' ? [...current, ...response.items] : response.items));
      setTotal(response.total);
      setHasMore(response.has_more);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '问题与风险加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [filters, hasMore, items.length, loadingMore, query, tab]);

  useEffect(() => {
    load();
  }, [query, filters, tab]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.iconButton}>
          <LucideIcon name="chevron-left" color="#111827" size={22} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.title}>问题与风险</Text>
      </View>
      <View style={styles.tabs}>
        <Pressable onPress={() => setTab('issues')} style={[styles.tab, tab === 'issues' ? styles.tabActive : null]}>
          <Text style={[styles.tabText, tab === 'issues' ? styles.tabTextActive : null]}>遗留问题</Text>
        </Pressable>
        <Pressable onPress={() => setTab('risks')} style={[styles.tab, tab === 'risks' ? styles.tabActive : null]}>
          <Text style={[styles.tabText, tab === 'risks' ? styles.tabTextActive : null]}>风险记录</Text>
        </Pressable>
      </View>
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <LucideIcon name="search" color="#8b95a7" size={18} strokeWidth={2.2} />
          <TextInput value={query} onChangeText={setQuery} onSubmitEditing={() => load('refresh')} placeholder="搜索问题、风险、会议..." placeholderTextColor="#9ca3af" style={styles.searchInput} />
        </View>
        <Pressable onPress={() => setFilterVisible(true)} style={styles.filterButton}>
          <LucideIcon name="filter" color="#111827" size={17} strokeWidth={2.2} />
        </Pressable>
      </View>
      <Text style={styles.count}>共 {total} 条{tab === 'issues' ? '遗留问题' : '风险记录'}</Text>
      {loading ? <KnowledgeListSkeleton /> : null}
      {error && !loading ? <KnowledgeErrorState message={error} onRetry={() => load()} /> : null}
      {!loading && !error ? (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={items.length ? styles.list : styles.emptyList}
          renderItem={({ item }) => <KnowledgeCard item={item} query={query} onPress={onOpenSource} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load('refresh')} tintColor="#6657ff" />}
          onEndReached={() => load('more')}
          onEndReachedThreshold={0.25}
          ListEmptyComponent={<KnowledgeEmptyState title={tab === 'issues' ? '暂无遗留问题' : '暂无风险记录'} text="字段不存在时不会展示推测内容。" />}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#6657ff" /> : null}
        />
      ) : null}
      <KnowledgeFilterSheet visible={filterVisible} value={filters} showContentType={false} onApply={setFilters} onClose={() => setFilterVisible(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: '#f7f8fc', flex: 1, padding: 18, paddingBottom: 88 },
  header: { alignItems: 'center', flexDirection: 'row', gap: 12, marginBottom: 14 },
  iconButton: { alignItems: 'center', height: 34, justifyContent: 'center', width: 34 },
  title: { color: '#111827', fontSize: 20, fontWeight: '900' },
  tabs: { backgroundColor: '#ffffff', borderRadius: 16, flexDirection: 'row', gap: 6, marginBottom: 12, padding: 5 },
  tab: { alignItems: 'center', borderRadius: 12, flex: 1, minHeight: 38, justifyContent: 'center' },
  tabActive: { backgroundColor: '#f0efff' },
  tabText: { color: '#8b95a7', fontSize: 13, fontWeight: '900' },
  tabTextActive: { color: '#6657ff' },
  searchRow: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  searchBox: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 16, borderWidth: 1, flex: 1, flexDirection: 'row', gap: 8, minHeight: 46, paddingHorizontal: 12 },
  searchInput: { color: '#111827', flex: 1, fontSize: 13, minHeight: 42 },
  filterButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 14, borderWidth: 1, height: 46, justifyContent: 'center', width: 46 },
  count: { color: '#667085', fontSize: 12, fontWeight: '800', marginBottom: 10 },
  list: { gap: 12, paddingBottom: 24 },
  emptyList: { flexGrow: 1, justifyContent: 'center' },
});
