import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';

import { KnowledgeItem, listKnowledgeDecisions } from '../api';
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

const PAGE_SIZE = 20;

export function KnowledgeDecisionListScreen({ onBack, onOpenSource }: Props) {
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
      const response = await listKnowledgeDecisions({ query, meeting_type: filters.meeting_type, ...filterDates(filters.dateRange), limit: PAGE_SIZE, offset });
      setItems((current) => (mode === 'more' ? [...current, ...response.items] : response.items));
      setTotal(response.total);
      setHasMore(response.has_more);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '关键决策加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [filters, hasMore, items.length, loadingMore, query]);

  useEffect(() => {
    load();
  }, [query, filters]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.iconButton}>
          <LucideIcon name="chevron-left" color="#111827" size={22} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.title}>关键决策</Text>
      </View>
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <LucideIcon name="search" color="#8b95a7" size={18} strokeWidth={2.2} />
          <TextInput value={query} onChangeText={setQuery} onSubmitEditing={() => load('refresh')} placeholder="搜索决策内容、会议..." placeholderTextColor="#9ca3af" style={styles.searchInput} />
        </View>
        <Pressable onPress={() => setFilterVisible(true)} style={styles.filterButton}>
          <LucideIcon name="filter" color="#111827" size={17} strokeWidth={2.2} />
        </Pressable>
      </View>
      <Text style={styles.count}>共 {total} 条关键决策</Text>
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
          ListEmptyComponent={<KnowledgeEmptyState title="暂无关键决策" text="完成会议分析后，正式结论会在这里沉淀。" />}
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
  searchRow: { flexDirection: 'row', gap: 10, marginBottom: 10 },
  searchBox: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 16, borderWidth: 1, flex: 1, flexDirection: 'row', gap: 8, minHeight: 46, paddingHorizontal: 12 },
  searchInput: { color: '#111827', flex: 1, fontSize: 13, minHeight: 42 },
  filterButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 14, borderWidth: 1, height: 46, justifyContent: 'center', width: 46 },
  count: { color: '#667085', fontSize: 12, fontWeight: '800', marginBottom: 10 },
  list: { gap: 12, paddingBottom: 24 },
  emptyList: { flexGrow: 1, justifyContent: 'center' },
});
