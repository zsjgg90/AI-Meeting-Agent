import { StyleSheet, View } from 'react-native';

export function KnowledgeListSkeleton() {
  return (
    <View style={styles.wrap}>
      {[0, 1, 2, 3].map((item) => (
        <View key={item} style={styles.card}>
          <View style={[styles.line, styles.short]} />
          <View style={styles.line} />
          <View style={[styles.line, styles.medium]} />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
  line: {
    backgroundColor: '#eef1f7',
    borderRadius: 999,
    height: 12,
    width: '100%',
  },
  medium: { width: '64%' },
  short: { width: '38%' },
});
