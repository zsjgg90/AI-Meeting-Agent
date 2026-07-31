import * as DocumentPicker from 'expo-document-picker';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { createMeeting, MeetingCreated } from '../api';
import { LucideIcon } from '../components/LucideIcon';
import { defaultMeetingTitle } from '../utils/meetingTitle';

type ImportedMeeting = {
  meeting: MeetingCreated;
  fileUri: string;
  endedAt: string;
};

type Props = {
  onImported: (result: ImportedMeeting) => void;
  onCancel: () => void;
};

function meetingTitleFromFileName(fileName: string | undefined): string {
  const name = fileName?.trim() || '导入音频';
  const withoutExtension = name.replace(/\.[^.]+$/, '').trim();
  return withoutExtension || '导入音频';
}

export function ImportMeetingScreen({ onImported, onCancel }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pickFile() {
    try {
      setBusy(true);
      setError(null);
      const result = await DocumentPicker.getDocumentAsync({
        type: 'audio/*',
        copyToCacheDirectory: true,
        multiple: false,
      });

      if (result.canceled || !result.assets?.[0]) {
        return;
      }

      const asset = result.assets[0];
      const meeting = await createMeeting(defaultMeetingTitle('import'), { title_source: 'fallback' });
      onImported({
        meeting,
        fileUri: asset.uri,
        endedAt: new Date().toISOString(),
      });
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '文件导入失败，请稍后重试。');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <View style={styles.iconWrap}>
          <LucideIcon name="file-text" color="#2B6CFF" size={30} strokeWidth={2.2} />
        </View>
        <Text style={styles.title}>导入音频</Text>
        <Text style={styles.description}>
          选择本地音频文件后，将复用现有会议上传和 AI 分析流程生成转写、摘要和待办。
        </Text>
        <View style={styles.supportRow}>
          <Text style={styles.supportText}>支持常见音频格式，具体解析能力以后端服务为准。</Text>
        </View>
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>

      <View style={styles.actions}>
        <Pressable disabled={busy} onPress={onCancel} style={styles.secondaryButton}>
          <Text style={styles.secondaryText}>取消</Text>
        </Pressable>
        <Pressable disabled={busy} onPress={pickFile} style={[styles.primaryButton, busy ? styles.disabledButton : null]}>
          {busy ? <ActivityIndicator color="#ffffff" /> : <Text style={styles.primaryText}>选择音频</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'space-between',
    paddingHorizontal: 18,
    paddingTop: 10,
  },
  card: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingVertical: 28,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  iconWrap: {
    alignItems: 'center',
    backgroundColor: '#e8f0fe',
    borderRadius: 28,
    height: 56,
    justifyContent: 'center',
    width: 56,
  },
  title: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
    marginTop: 18,
  },
  description: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 21,
    marginTop: 10,
    textAlign: 'center',
  },
  supportRow: {
    backgroundColor: '#f8f9ff',
    borderRadius: 14,
    marginTop: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  supportText: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 18,
    textAlign: 'center',
  },
  error: {
    color: '#ef4444',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 14,
    textAlign: 'center',
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    paddingBottom: 28,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#2B6CFF',
    borderRadius: 16,
    flex: 1,
    minHeight: 52,
    justifyContent: 'center',
  },
  disabledButton: {
    opacity: 0.7,
  },
  primaryText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    minHeight: 52,
    justifyContent: 'center',
  },
  secondaryText: {
    color: '#6b7280',
    fontSize: 15,
    fontWeight: '900',
  },
});
