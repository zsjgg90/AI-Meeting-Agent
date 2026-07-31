import { Audio } from 'expo-av';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

type Props = {
  onBack: () => void;
};

type RecordingState = 'idle' | 'recording' | 'recorded';

const sampleText = '早上开会时，我会先听取大家的意见，然后再发表看法。有时候我说话比较快，有时候会放慢语速，强调重点内容。';

function formatDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, totalSeconds);
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function AddVoiceprintSampleScreen({ onBack }: Props) {
  const [name, setName] = useState('');
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const startedAtMsRef = useRef<number | null>(null);

  const releaseRecording = useCallback(async () => {
    const activeRecording = recordingRef.current;
    if (!activeRecording) return;
    recordingRef.current = null;
    try {
      await activeRecording.stopAndUnloadAsync();
    } catch {
      // The native recorder may already be stopped while leaving the page.
    }
    try {
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });
    } catch {
      // Audio mode reset should not block page cleanup.
    }
  }, []);

  useEffect(() => {
    return () => {
      releaseRecording().catch(() => undefined);
    };
  }, [releaseRecording]);

  useEffect(() => {
    if (recordingState !== 'recording') return undefined;
    const timer = setInterval(() => {
      if (startedAtMsRef.current === null) return;
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAtMsRef.current) / 1000)));
    }, 250);
    return () => clearInterval(timer);
  }, [recordingState]);

  async function startRecording() {
    if (busy || recordingRef.current) return;
    const trimmedName = name.trim();
    if (!trimmedName) {
      Alert.alert('请输入用户姓名', '声纹样本需要先填写用户姓名。');
      return;
    }

    try {
      setBusy(true);
      setError(null);
      setRecordingUri(null);
      setElapsedSeconds(0);

      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setError('请允许麦克风权限后再开始录制声纹样本。');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: false,
        shouldDuckAndroid: true,
        playThroughEarpieceAndroid: false,
      });

      const nextRecording = new Audio.Recording();
      await nextRecording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await nextRecording.startAsync();
      recordingRef.current = nextRecording;
      startedAtMsRef.current = Date.now();
      setRecordingState('recording');
    } catch (nextError) {
      await releaseRecording();
      setRecordingState('idle');
      setError(nextError instanceof Error ? nextError.message : '启动声纹录制失败，请重试。');
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    const activeRecording = recordingRef.current;
    if (!activeRecording || busy) return;
    try {
      setBusy(true);
      setError(null);
      const uriBeforeStop = activeRecording.getURI();
      await activeRecording.stopAndUnloadAsync();
      const uri = uriBeforeStop || activeRecording.getURI();
      recordingRef.current = null;
      startedAtMsRef.current = null;
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });
      if (!uri) {
        setRecordingState('idle');
        setError('声纹录音文件保存失败，请重新录制。');
        return;
      }
      setRecordingUri(uri);
      setRecordingState('recorded');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '停止声纹录制失败。');
    } finally {
      setBusy(false);
    }
  }

  function handleSave() {
    if (!name.trim()) {
      Alert.alert('请输入用户姓名', '保存前需要填写用户姓名。');
      return;
    }
    if (!recordingUri) {
      Alert.alert('请先录制样本', '保存前需要完成一段声纹样本录制。');
      return;
    }
    Alert.alert('待接入接口', '声纹注册 API 尚未开放，当前样本未上传、未注册，也不会用于身份匹配。');
  }

  const isRecording = recordingState === 'recording';
  const timerText = formatDuration(elapsedSeconds);

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.headerButton}>
          <LucideIcon name="chevron-left" color="#111827" size={24} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.headerTitle}>添加声纹样本</Text>
        <Pressable onPress={handleSave} hitSlop={10} style={styles.saveButton}>
          <Text style={styles.saveText}>保存</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={styles.inputCard}>
          <Text style={styles.inputLabel}>用户姓名</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            editable={!isRecording}
            placeholder="请输入用户姓名"
            placeholderTextColor="#b8bfcb"
            style={styles.nameInput}
          />
        </View>

        <View style={styles.guideCard}>
          <Text style={styles.guideTitle}>录制声纹样本</Text>
          <Text style={styles.guideSub}>保持自然语速，完整朗读下方内容</Text>
          <View style={styles.sampleBox}>
            <Text style={styles.sampleText}>{sampleText}</Text>
          </View>
        </View>

        <View style={styles.recorderBlock}>
          <Pressable
            disabled={busy}
            onPress={isRecording ? stopRecording : startRecording}
            style={[styles.recordButton, isRecording ? styles.stopRecordButton : null, busy ? styles.disabledButton : null]}
          >
            {busy ? (
              <ActivityIndicator color="#ffffff" size="small" />
            ) : isRecording ? (
              <View style={styles.stopSquare} />
            ) : (
              <LucideIcon name="mic" color="#ffffff" size={29} strokeWidth={2.5} />
            )}
          </Pressable>
          <Text style={styles.recordHint}>{isRecording ? '点击停止录音' : recordingUri ? '已录制，可重新录制' : '点击开始录音'}</Text>
          <Text style={[styles.timer, isRecording ? styles.timerActive : null]}>{timerText}</Text>
          {recordingUri ? <Text style={styles.recordedText}>已生成本地声纹样本，等待正式接口接入后才能保存。</Text> : null}
          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#f6f7fb',
    flex: 1,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 58,
    paddingHorizontal: 16,
    paddingVertical: 9,
  },
  headerButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  headerTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
  },
  saveButton: {
    alignItems: 'center',
    minHeight: 40,
    justifyContent: 'center',
    minWidth: 40,
  },
  saveText: {
    color: '#2B6CFF',
    fontSize: 14,
    fontWeight: '900',
  },
  content: {
    paddingBottom: 32,
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  inputCard: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    marginBottom: 14,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  inputLabel: {
    color: '#404040',
    fontSize: 13,
    fontWeight: '900',
    marginBottom: 6,
  },
  nameInput: {
    borderBottomColor: '#edf0f7',
    borderBottomWidth: 1,
    color: '#111827',
    fontSize: 16,
    fontWeight: '800',
    minHeight: 42,
    paddingVertical: 8,
  },
  guideCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 18,
    padding: 22,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  guideTitle: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
    textAlign: 'center',
  },
  guideSub: {
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 8,
    textAlign: 'center',
  },
  sampleBox: {
    backgroundColor: '#f8faff',
    borderRadius: 14,
    marginTop: 24,
    padding: 18,
    width: '100%',
  },
  sampleText: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 26,
    textAlign: 'justify',
  },
  recorderBlock: {
    alignItems: 'center',
    marginTop: 44,
  },
  recordButton: {
    alignItems: 'center',
    backgroundColor: '#2B6CFF',
    borderRadius: 36,
    height: 72,
    justifyContent: 'center',
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 18,
    width: 72,
    elevation: 5,
  },
  stopRecordButton: {
    backgroundColor: '#ef4444',
    shadowColor: '#ef4444',
  },
  disabledButton: {
    opacity: 0.68,
  },
  stopSquare: {
    backgroundColor: '#ffffff',
    borderRadius: 5,
    height: 22,
    width: 22,
  },
  recordHint: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
    marginTop: 13,
  },
  timer: {
    color: '#111827',
    fontSize: 24,
    fontVariant: ['tabular-nums'],
    fontWeight: '900',
    includeFontPadding: false,
    marginTop: 10,
  },
  timerActive: {
    color: '#ef4444',
  },
  recordedText: {
    color: '#4b5563',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 12,
    paddingHorizontal: 10,
    textAlign: 'center',
  },
  errorText: {
    color: '#ef4444',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 18,
    marginTop: 12,
    textAlign: 'center',
  },
});
