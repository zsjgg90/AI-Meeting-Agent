import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

export function AIAssistantScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>知识库</Text>
      <View style={styles.messageCard}>
        <Text style={styles.messageTitle}>你好！我是你的 AI 会议助手</Text>
        <Text style={styles.messageText}>我可以帮你回答关于会议纪要、待办事项和决策点的问题。</Text>
      </View>

      <View style={styles.quickList}>
        <Pressable style={styles.quickButton}>
          <Text style={styles.quickText}>本次会议的主要决策是什么？</Text>
        </Pressable>
        <Pressable style={styles.quickButton}>
          <Text style={styles.quickText}>谁负责设计稿的输出？</Text>
        </Pressable>
        <Pressable style={styles.quickButton}>
          <Text style={styles.quickText}>还有哪些风险需要关注？</Text>
        </Pressable>
      </View>

      <View style={styles.inputBar}>
        <TextInput placeholder="输入你的问题..." placeholderTextColor="#a8afbd" style={styles.input} />
        <Pressable style={styles.sendButton}>
          <Text style={styles.sendText}>↗</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 18,
  },
  title: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '900',
    marginBottom: 24,
    textAlign: 'center',
  },
  messageCard: {
    backgroundColor: '#f0f2ff',
    borderRadius: 14,
    gap: 8,
    padding: 16,
  },
  messageTitle: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '900',
  },
  messageText: {
    color: '#4b5563',
    fontSize: 13,
    lineHeight: 21,
  },
  quickList: {
    gap: 12,
    marginTop: 28,
  },
  quickButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#f3f4ff',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  quickText: {
    color: '#6657ff',
    fontSize: 13,
    fontWeight: '800',
  },
  inputBar: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginTop: 'auto',
    marginBottom: 22,
    padding: 8,
  },
  input: {
    color: '#111827',
    flex: 1,
    fontSize: 14,
    minHeight: 40,
    paddingHorizontal: 10,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 10,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  sendText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '900',
  },
});
