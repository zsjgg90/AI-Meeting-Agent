import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

export function KnowledgeBaseScreen() {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <View style={styles.iconBox}>
          <LucideIcon name="book-open" color="#4f46e5" size={30} strokeWidth={2.4} />
        </View>
        <Text style={styles.title}>知识库</Text>
        <Text style={styles.subtitle}>沉淀会议资料、项目背景和团队知识。</Text>
      </View>

      <View style={styles.emptyPanel}>
        <View style={styles.emptyIcon}>
          <LucideIcon name="file-text" color="#8b95a7" size={34} strokeWidth={2.2} />
        </View>
        <Text style={styles.emptyTitle}>暂无知识内容</Text>
        <Text style={styles.emptyText}>本阶段仅开放知识库入口和基础空状态，完整 RAG 问答将在后续版本接入。</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f7f8fc' },
  content: { gap: 18, padding: 18, paddingBottom: 100 },
  header: { gap: 10, paddingTop: 10 },
  iconBox: {
    alignItems: 'center',
    backgroundColor: '#eef2ff',
    borderRadius: 8,
    height: 54,
    justifyContent: 'center',
    width: 54,
  },
  title: { color: '#111827', fontSize: 34, fontWeight: '900', letterSpacing: 0 },
  subtitle: { color: '#667085', fontSize: 15, fontWeight: '700', lineHeight: 22 },
  emptyPanel: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
    minHeight: 240,
    justifyContent: 'center',
    padding: 24,
  },
  emptyIcon: {
    alignItems: 'center',
    backgroundColor: '#f3f4f6',
    borderRadius: 8,
    height: 62,
    justifyContent: 'center',
    width: 62,
  },
  emptyTitle: { color: '#111827', fontSize: 18, fontWeight: '900' },
  emptyText: { color: '#8b95a7', fontSize: 14, fontWeight: '700', lineHeight: 21, textAlign: 'center' },
});
