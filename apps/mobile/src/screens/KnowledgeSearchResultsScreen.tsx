import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';

import { KnowledgeItem, searchKnowledge } from '../api';
import { KnowledgeCard } from '../components/KnowledgeCard';
import { KnowledgeEmptyState } from '../components/KnowledgeEmptyState';
import { KnowledgeErrorState } from '../components/KnowledgeErrorState';
import { KnowledgeListSkeleton } from '../components/KnowledgeListSkeleton';
import { LucideIcon } from '../components/LucideIcon';
import { defaultKnowledgeFilters, filterDates, KnowledgeFilterSheet, KnowledgeFilters } from './KnowledgeFilterSheet';

type Props = {
  query: string;
  onBack: () => void;
  onCancel: () => void;
  onOpenSource: (item: KnowledgeItem) => void;
};

const PAGE_SIZE = 20;

export function KnowledgeSearchResultsScreen({ query: initialQuery, onBack, onCancel, onOpenSource }: Props) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery);
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
      const response = await searchKnowledge({
        query: submittedQuery,
        content_type: filters.content_type,
        meeting_type: filters.meeting_type,
        ...filterDates(filters.dateRange),
        limit: PAGE_SIZE,
        offset,
      });
      setItems((current) => (mode === 'more' ? [...current, ...response.items] : response.items));
      setTotal(response.total);
      setHasMore(response.has_more);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '搜索失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [filters, hasMore, items.length, loadingMore, submittedQuery]);

  useEffect(() => {
    load();
  }, [submittedQuery, filters]);

  function submit() {
    setSubmittedQuery(query.trim());
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.iconButton}>
          <LucideIcon name="chevron-left" color="#111827" size={22} strokeWidth={2.3} />
        </Pressable>
        <View style={styles.searchBox}>
          <LucideIcon name="search" color="#8b95a7" size={17} strokeWidth={2.2} />
          <TextInput value={query} onChangeText={setQuery} onSubmitEditing={submit} placeholder="搜索知识..." placeholderTextColor="#9ca3af" style={styles.searchInput} />
        </View>
        <Pressable onPress={onCancel}>
          <Text style={styles.cancel}>取消</Text>
        </Pressable>
      </View>
      <View style={styles.filterRow}>
        <Text style={styles.count}>共找到 {total} 条结果</Text>
        <Pressable onPress={() => setFilterVisible(true)} style={styles.filterButton}>
          <LucideIcon name="filter" color="#111827" size={16} strokeWidth={2.2} />
          <Text style={styles.filterText}>筛选</Text>
        </Pressable>
      </View>
      {loading ? <KnowledgeListSkeleton /> : null}
      {error && !loading ? <KnowledgeErrorState message={error} onRetry={() => load()} /> : null}
      {!loading && !error ? (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={items.length ? styles.list : styles.emptyList}
          renderItem={({ item }) => <KnowledgeCard item={item} query={submittedQuery} onPress={onOpenSource} />}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load('refresh')} tintColor="#6657ff" />}
          onEndReached={() => load('more')}
          onEndReachedThreshold={0.25}
          ListEmptyComponent={<KnowledgeEmptyState title="暂无搜索结果" text="请尝试更换关键词或筛选条件。" />}
          ListFooterComponent={loadingMore ? <ActivityIndicator color="#6657ff" /> : null}
        />
      ) : null}
      <KnowledgeFilterSheet visible={filterVisible} value={filters} onApply={setFilters} onClose={() => setFilterVisible(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: '#f7f8fc', flex: 1, padding: 18, paddingBottom: 88 },
  header: { alignItems: 'center', flexDirection: 'row', gap: 10, marginBottom: 12 },
  iconButton: { alignItems: 'center', height: 34, justifyContent: 'center', width: 34 },
  searchBox: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 16, borderWidth: 1, flex: 1, flexDirection: 'row', gap: 8, minHeight: 44, paddingHorizontal: 12 },
  searchInput: { color: '#111827', flex: 1, fontSize: 13, minHeight: 40 },
  cancel: { color: '#6657ff', fontSize: 13, fontWeight: '900' },
  filterRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  count: { color: '#667085', fontSize: 12, fontWeight: '800' },
  filterButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 12, borderWidth: 1, flexDirection: 'row', gap: 5, paddingHorizontal: 10, paddingVertical: 8 },
  filterText: { color: '#111827', fontSize: 12, fontWeight: '900' },
  list: { gap: 12, paddingBottom: 24 },
  emptyList: { flexGrow: 1, justifyContent: 'center' },
});
