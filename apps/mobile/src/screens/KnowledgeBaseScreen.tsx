import { useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

type Props = {
  onOpenDecisions: () => void;
  onOpenIssueRisks: () => void;
  onOpenSearch: (query?: string) => void;
  onOpenImportAudio: () => void;
};

const quickQuestions = [
  '最近会议重点是什么？',
  '帮我整理最近一周待办事项，并按负责人和优先级列出',
  '总结最近所有文件的核心结论和趋势变化',
];

export function KnowledgeBaseScreen({ onOpenDecisions, onOpenIssueRisks, onOpenSearch, onOpenImportAudio }: Props) {
  const [query, setQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitNotice, setSubmitNotice] = useState<string | null>(null);

  function fillQuestion(question: string) {
    if (submitting) return;
    setQuery(question);
    setSubmitNotice('已填入快捷问题。当前版本暂未开放知识库问答，可使用知识搜索查看相关会议证据。');
  }

  function submitQuestion() {
    const clean = query.trim();
    if (!clean || submitting) return;
    setSubmitting(true);
    setSubmitNotice('当前版本暂未开放知识库问答。已为你保留问题，可进入知识搜索查看真实会议知识条目。');
    setTimeout(() => setSubmitting(false), 250);
  }

  function openHistory() {
    Alert.alert('暂未开放', '当前版本没有真实问答历史或持久化搜索历史。');
  }

  function openVoiceInput() {
    Alert.alert('暂未开放', '当前版本没有知识库语音问答输入，会议录音链路不会直接接入此输入框。');
  }

  function renderHeader() {
    return (
      <View style={styles.headerContent}>
        <View style={styles.topBar}>
          <Text style={styles.brand}>MeetMind AI</Text>
          <Pressable onPress={openHistory} style={styles.historyButton}>
            <LucideIcon name="clock-3" color="#9ca3af" size={20} strokeWidth={2.2} />
            <Text style={styles.historyText}>暂未开放</Text>
          </Pressable>
        </View>

        <View style={styles.hero}>
          <View style={styles.heroTitleRow}>
            <Text style={styles.hi}>Hi</Text>
            <View style={styles.botAvatar}>
              <View style={styles.botAntenna} />
              <View style={styles.botHead}>
                <View style={styles.botFace}>
                  <View style={styles.botEye} />
                  <View style={styles.botEye} />
                </View>
              </View>
            </View>
          </View>
          <Text style={styles.heroTitle}>会议达人，有什么吩咐？</Text>
          <Text style={styles.heroText}>我可以帮你总结要点、整理待办、提炼结论、生成会议材料，也可以继续追问会议相关细节。</Text>
        </View>

        <View style={styles.quickSection}>
          {quickQuestions.map((question) => (
            <Pressable disabled={submitting} key={question} onPress={() => fillQuestion(question)} style={[styles.quickBubble, submitting ? styles.disabled : null]}>
              <Text style={styles.quickText}>{question}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.linkRow}>
          <Pressable onPress={() => onOpenSearch(query)} style={styles.linkButton}>
            <LucideIcon name="search" color="#2B6CFF" size={16} strokeWidth={2.2} />
            <Text style={styles.linkText}>搜索知识</Text>
          </Pressable>
          <Pressable onPress={onOpenDecisions} style={styles.linkButton}>
            <LucideIcon name="circle-check-big" color="#2B6CFF" size={16} strokeWidth={2.2} />
            <Text style={styles.linkText}>关键决策</Text>
          </Pressable>
          <Pressable onPress={onOpenIssueRisks} style={styles.linkButton}>
            <LucideIcon name="triangle-alert" color="#f97316" size={16} strokeWidth={2.2} />
            <Text style={[styles.linkText, styles.warnLinkText]}>问题风险</Text>
          </Pressable>
        </View>

      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.container}>
      <FlatList
        data={[]}
        ListHeaderComponent={renderHeader}
        contentContainerStyle={styles.content}
        renderItem={null}
      />

      <View style={styles.inputPanel}>
        {submitNotice ? <Text style={styles.notice}>{submitNotice}</Text> : null}
        <View style={styles.inputRow}>
          <Pressable onPress={openVoiceInput} style={styles.roundButton}>
            <LucideIcon name="mic" color="#9ca3af" size={21} strokeWidth={2.2} />
          </Pressable>
          <TextInput
            value={query}
            onChangeText={(value) => {
              setQuery(value);
              if (submitNotice) setSubmitNotice(null);
            }}
            onSubmitEditing={submitQuestion}
            placeholder="输入会议或知识库相关问题"
            placeholderTextColor="#9ca3af"
            multiline
            returnKeyType="send"
            style={styles.input}
          />
          {query.trim() ? (
            <Pressable disabled={submitting} onPress={submitQuestion} style={[styles.sendButton, submitting ? styles.disabled : null]}>
              <LucideIcon name="chevron-right" color="#ffffff" size={21} strokeWidth={2.6} />
            </Pressable>
          ) : (
            <Pressable onPress={onOpenImportAudio} style={styles.roundButton}>
              <LucideIcon name="image-plus" color="#6b7280" size={21} strokeWidth={2.2} />
            </Pressable>
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: '#f6f7fb', flex: 1 },
  content: { gap: 12, paddingBottom: 136, paddingHorizontal: 20, paddingTop: 10 },
  headerContent: { gap: 22 },
  topBar: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  brand: { color: '#111827', fontSize: 21, fontWeight: '900', letterSpacing: 0 },
  historyButton: {
    alignItems: 'center',
    borderColor: '#edf0f7',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 5,
    minHeight: 38,
    paddingHorizontal: 10,
  },
  historyText: { color: '#9ca3af', fontSize: 11, fontWeight: '800' },
  hero: { gap: 8, paddingTop: 8 },
  heroTitleRow: { alignItems: 'center', flexDirection: 'row', gap: 13 },
  hi: { color: '#111827', fontSize: 42, fontWeight: '900', letterSpacing: 0, lineHeight: 50 },
  botAvatar: { alignItems: 'center', backgroundColor: '#e8f0fe', borderRadius: 25, height: 50, justifyContent: 'center', width: 50 },
  botAntenna: { backgroundColor: '#2B6CFF', borderRadius: 2, height: 8, position: 'absolute', top: 5, width: 3 },
  botHead: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#d9e2f1', borderRadius: 17, borderWidth: 1, height: 31, justifyContent: 'center', marginTop: 7, width: 36 },
  botFace: { alignItems: 'center', backgroundColor: '#111827', borderRadius: 12, flexDirection: 'row', gap: 6, height: 19, justifyContent: 'center', width: 26 },
  botEye: { backgroundColor: '#2B6CFF', borderRadius: 4, height: 5, width: 5 },
  heroTitle: { color: '#111827', fontSize: 24, fontWeight: '900', letterSpacing: 0, lineHeight: 31 },
  heroText: { color: '#8b95a7', fontSize: 14, fontWeight: '700', lineHeight: 22, paddingRight: 10 },
  quickSection: { gap: 11 },
  quickBubble: { alignSelf: 'flex-start', backgroundColor: '#ffffff', borderColor: '#eef0f6', borderRadius: 18, borderTopLeftRadius: 4, borderWidth: 1, maxWidth: '100%', paddingHorizontal: 14, paddingVertical: 12 },
  quickText: { color: '#273142', fontSize: 13, fontWeight: '800', lineHeight: 19 },
  linkRow: { flexDirection: 'row', gap: 8 },
  linkButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 14, borderWidth: 1, flex: 1, flexDirection: 'row', gap: 5, justifyContent: 'center', minHeight: 42, paddingHorizontal: 8 },
  linkText: { color: '#2B6CFF', fontSize: 12, fontWeight: '900' },
  warnLinkText: { color: '#f97316' },
  inputPanel: {
    backgroundColor: 'rgba(255,255,255,0.98)',
    borderTopColor: '#eef0f6',
    borderTopWidth: 1,
    bottom: 0,
    gap: 8,
    left: 0,
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 12,
    position: 'absolute',
    right: 0,
  },
  notice: { color: '#2B6CFF', fontSize: 12, fontWeight: '800', lineHeight: 17, paddingHorizontal: 5 },
  inputRow: { alignItems: 'flex-end', flexDirection: 'row', gap: 9 },
  roundButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#e5e7eb', borderRadius: 22, borderWidth: 1, height: 44, justifyContent: 'center', width: 44 },
  input: {
    backgroundColor: '#f7f8fc',
    borderColor: '#edf0f7',
    borderRadius: 22,
    borderWidth: 1,
    color: '#111827',
    flex: 1,
    fontSize: 14,
    maxHeight: 92,
    minHeight: 44,
    paddingHorizontal: 15,
    paddingVertical: 11,
  },
  sendButton: { alignItems: 'center', backgroundColor: '#2B6CFF', borderRadius: 22, height: 44, justifyContent: 'center', width: 44 },
  disabled: { opacity: 0.56 },
});
