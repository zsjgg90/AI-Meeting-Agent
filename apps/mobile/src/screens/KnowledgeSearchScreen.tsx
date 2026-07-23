import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

type Props = {
  initialQuery?: string;
  onBack: () => void;
  onSearch: (query: string) => void;
};

const suggestions = ['订单接口延期', '本周需求限定原因', '风险汇总', '接口性能问题', '数据迁移口径', '测试进度'];

export function KnowledgeSearchScreen({ initialQuery = '', onBack, onSearch }: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [recent, setRecent] = useState<string[]>(initialQuery ? [initialQuery] : []);

  function submit(value = query) {
    const clean = value.trim();
    if (!clean) return;
    setRecent((current) => [clean, ...current.filter((item) => item !== clean)].slice(0, 6));
    onSearch(clean);
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.iconButton}>
          <LucideIcon name="chevron-left" color="#111827" size={22} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.title}>知识搜索</Text>
      </View>
      <View style={styles.searchBox}>
        <LucideIcon name="search" color="#6657ff" size={20} strokeWidth={2.3} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={() => submit()}
          placeholder="搜索会议、决策、问题、风险..."
          placeholderTextColor="#9ca3af"
          returnKeyType="search"
          style={styles.searchInput}
        />
      </View>
      <Pressable onPress={() => submit()} style={styles.searchButton}>
        <Text style={styles.searchButtonText}>搜索</Text>
      </Pressable>

      {recent.length ? (
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>最近搜索</Text>
            <Pressable onPress={() => setRecent([])}>
              <Text style={styles.clear}>清空</Text>
            </Pressable>
          </View>
          {recent.map((item) => (
            <Pressable key={item} onPress={() => submit(item)} style={styles.recentRow}>
              <LucideIcon name="clock-3" color="#8b95a7" size={15} strokeWidth={2.1} />
              <Text style={styles.recentText}>{item}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>搜索建议</Text>
        <View style={styles.suggestions}>
          {suggestions.map((item) => (
            <Pressable key={item} onPress={() => submit(item)} style={styles.suggestionChip}>
              <Text style={styles.suggestionText}>{item}</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: '#f7f8fc', flex: 1 },
  content: { gap: 16, padding: 18, paddingBottom: 100 },
  header: { alignItems: 'center', flexDirection: 'row', gap: 12 },
  iconButton: { alignItems: 'center', height: 34, justifyContent: 'center', width: 34 },
  title: { color: '#111827', fontSize: 20, fontWeight: '900' },
  searchBox: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#6657ff', borderRadius: 18, borderWidth: 1.3, flexDirection: 'row', gap: 9, minHeight: 54, paddingHorizontal: 13 },
  searchInput: { color: '#111827', flex: 1, fontSize: 14, minHeight: 48 },
  searchButton: { alignItems: 'center', backgroundColor: '#6657ff', borderRadius: 15, minHeight: 46, justifyContent: 'center' },
  searchButtonText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
  section: { gap: 10, marginTop: 4 },
  sectionHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  sectionTitle: { color: '#111827', fontSize: 14, fontWeight: '900' },
  clear: { color: '#6657ff', fontSize: 12, fontWeight: '900' },
  recentRow: { alignItems: 'center', flexDirection: 'row', gap: 9, minHeight: 34 },
  recentText: { color: '#374151', flex: 1, fontSize: 13, fontWeight: '800' },
  suggestions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  suggestionChip: { backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 12, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 9 },
  suggestionText: { color: '#667085', fontSize: 12, fontWeight: '900' },
});
