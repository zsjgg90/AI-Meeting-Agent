import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { createMeeting, MeetingCreated } from '../api';

type Props = {
  onCreated: (meeting: MeetingCreated) => void;
  onCancel: () => void;
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function NewMeetingScreen({ onCreated }: Props) {
  const [title, setTitle] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    const cleanTitle = title.trim();
    const cleanLocation = location.trim();
    if (!cleanTitle) {
      setError('请输入会议名称。');
      return;
    }

    try {
      setBusy(true);
      setError(null);
      const meeting = await createMeeting(cleanTitle, {
        location: cleanLocation || undefined,
      });
      await wait(700);
      onCreated(meeting);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '会议创建失败。');
    } finally {
      setBusy(false);
    }
  }

  if (busy) {
    return (
      <View style={styles.loadingContainer}>
        <View style={styles.loadingCard}>
          <ActivityIndicator color="#6657ff" size="large" />
          <Text style={styles.loadingTitle}>正在创建会议...</Text>
          <Text style={styles.loadingText}>稍等一下，即将进入会议录音页面</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.formCard}>
        <View style={styles.formIntro}>
          <Text style={styles.formTitle}>创建一场新会议</Text>
          <Text style={styles.formSub}>填写基础信息后进入录音页，会议开始后才会保存到列表。</Text>
        </View>

        <View style={styles.formGroup}>
          <Text style={styles.label}>会议名称</Text>
          <TextInput
            value={title}
            onChangeText={setTitle}
            placeholder="请输入会议名称"
            placeholderTextColor="#c0c5d2"
            style={styles.input}
          />
        </View>

        <View style={styles.formGroup}>
          <Text style={styles.label}>会议地址</Text>
          <TextInput
            value={location}
            onChangeText={setLocation}
            placeholder="请输入会议地址（选填）"
            placeholderTextColor="#c0c5d2"
            style={styles.input}
          />
        </View>

        <View style={styles.formGroup}>
          <Text style={styles.label}>会议描述（可选）</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            placeholder="请输入会议描述或议题"
            placeholderTextColor="#c0c5d2"
            style={styles.textarea}
            multiline
            textAlignVertical="top"
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>

      <Pressable disabled={busy} onPress={submit} style={styles.primaryButton}>
        <Text style={styles.primaryText}>创建</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    gap: 18,
    paddingHorizontal: 18,
    paddingTop: 10,
  },
  loadingContainer: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 28,
  },
  loadingCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 22,
    borderWidth: 1,
    gap: 12,
    padding: 26,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    width: '100%',
    elevation: 4,
  },
  loadingTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  loadingText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  formCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    gap: 16,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  formIntro: {
    gap: 5,
    marginBottom: 2,
  },
  formTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  formSub: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
  },
  formGroup: {
    gap: 8,
  },
  label: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '800',
  },
  input: {
    backgroundColor: '#f8f9ff',
    borderColor: '#edf0f7',
    borderRadius: 14,
    borderWidth: 1,
    color: '#111827',
    fontSize: 14,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  textarea: {
    backgroundColor: '#f8f9ff',
    borderColor: '#edf0f7',
    borderRadius: 14,
    borderWidth: 1,
    color: '#111827',
    fontSize: 14,
    minHeight: 112,
    padding: 14,
  },
  primaryButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: '#6657ff',
    borderRadius: 16,
    minHeight: 54,
    justifyContent: 'center',
    marginTop: 4,
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.22,
    shadowRadius: 20,
    elevation: 5,
  },
  primaryText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
  },
  error: {
    color: '#ef4444',
  },
});
