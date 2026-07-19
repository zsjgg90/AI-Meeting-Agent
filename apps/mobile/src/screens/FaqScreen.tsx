import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

const faqs = [
  '如何创建一场会议？',
  '会议录音如何开始和结束？',
  'AI 分析需要多长时间？',
  '如何查看会议纪要？',
  '待办事项如何管理？',
  '数据会保存多久？',
  '可以在多个设备上使用吗？',
  '如何升级到 Pro 版本？',
  '遇到问题如何联系客服？',
];

export function FaqScreen() {
  const [keyword, setKeyword] = useState('');
  const data = useMemo(() => {
    const clean = keyword.trim();
    if (!clean) return faqs;
    return faqs.filter((item) => item.includes(clean));
  }, [keyword]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.searchBox}>
        <LucideIcon name="search" color="#9ca3af" size={20} strokeWidth={2} />
        <TextInput
          value={keyword}
          onChangeText={setKeyword}
          placeholder="搜索问题"
          placeholderTextColor="#a7adbb"
          style={styles.searchInput}
        />
      </View>

      <View style={styles.listCard}>
        {data.length ? (
          data.map((item) => {
            const originalIndex = faqs.indexOf(item);
            const isLast = item === data[data.length - 1];
            return (
              <Pressable
                key={item}
                onPress={() => console.log('FAQ pressed:', item)}
                style={[styles.row, !isLast ? styles.rowDivider : null]}
              >
                <View style={styles.numberBadge}>
                  <Text style={styles.numberText}>{originalIndex + 1}</Text>
                </View>
                <Text style={styles.question}>{item}</Text>
                <LucideIcon name="chevron-right" color="#9ca3af" size={19} strokeWidth={2.2} />
              </Pressable>
            );
          })
        ) : (
          <Text style={styles.empty}>未找到相关问题</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingBottom: 32,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 52,
    paddingHorizontal: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.05,
    shadowRadius: 18,
    elevation: 2,
  },
  searchInput: {
    color: '#111827',
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
    minHeight: 50,
    padding: 0,
  },
  listCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 24,
    borderWidth: 1,
    marginTop: 18,
    overflow: 'hidden',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.07,
    shadowRadius: 24,
    elevation: 4,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 62,
    paddingHorizontal: 14,
  },
  rowDivider: {
    borderBottomColor: '#eef0f6',
    borderBottomWidth: 1,
  },
  numberBadge: {
    alignItems: 'center',
    backgroundColor: '#f0edff',
    borderRadius: 14,
    height: 28,
    justifyContent: 'center',
    width: 28,
  },
  numberText: {
    color: '#6c4dff',
    fontSize: 12,
    fontWeight: '900',
  },
  question: {
    color: '#111827',
    flex: 1,
    fontSize: 14,
    fontWeight: '900',
  },
  empty: {
    color: '#8b95a7',
    fontSize: 14,
    fontWeight: '700',
    padding: 22,
    textAlign: 'center',
  },
});
