import { StyleSheet, Text, View } from 'react-native';

export function AboutScreen() {
  return (
    <View style={styles.container}>
      <View style={styles.logo}>
        <View style={styles.wave}>
          {[12, 22, 30, 22, 12].map((height, index) => (
            <View key={index} style={[styles.bar, { height }]} />
          ))}
        </View>
      </View>
      <Text style={styles.title}>MeetMind AI</Text>
      <Text style={styles.sub}>AI 会议记录助手</Text>
      <View style={styles.card}>
        <Text style={styles.text}>MeetMind AI 帮助你记录会议、整理转写、生成结构化纪要和待办事项。</Text>
        <View style={styles.divider} />
        <Text style={styles.version}>当前版本 V1.0.0</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    flex: 1,
    paddingHorizontal: 24,
    paddingTop: 44,
  },
  logo: {
    alignItems: 'center',
    backgroundColor: '#f7f8fc',
    borderRadius: 26,
    height: 88,
    justifyContent: 'center',
    marginBottom: 18,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    width: 88,
  },
  wave: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  bar: {
    backgroundColor: '#111827',
    borderRadius: 999,
    width: 4,
  },
  title: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '900',
  },
  sub: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
    marginTop: 6,
  },
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    marginTop: 28,
    padding: 20,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.07,
    shadowRadius: 24,
    width: '100%',
  },
  text: {
    color: '#374151',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 24,
    textAlign: 'center',
  },
  divider: {
    backgroundColor: '#eef0f6',
    height: 1,
  },
  version: {
    color: '#2B6CFF',
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'center',
  },
});
