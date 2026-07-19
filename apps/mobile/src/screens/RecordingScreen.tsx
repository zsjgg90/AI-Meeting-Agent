import { Audio } from 'expo-av';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Animated, Pressable, StyleSheet, Text, View } from 'react-native';

type Props = {
  meeting: {
    id: string;
    title: string;
    status: string;
  };
  onProcessing: (recordingUri: string, endedAt: string, realtimeTranscriptReady: boolean) => void;
  onStarted?: () => void;
  minimized?: boolean;
};

type RecordingState = 'idle' | 'recording' | 'paused' | 'stopped';

const recordingStateText: Record<RecordingState, string> = {
  idle: '准备录音',
  recording: '录音中',
  paused: '已暂停',
  stopped: '录音结束',
};

function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

export function RecordingScreen({ meeting, onProcessing, onStarted, minimized = false }: Props) {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [state, setState] = useState<RecordingState>('idle');
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const waveProgress = useRef(new Animated.Value(0)).current;

  const waveform = useMemo(
    () => [24, 34, 18, 42, 28, 52, 30, 64, 38, 72, 44, 60, 36, 48, 30, 56, 26, 44, 34, 58, 22, 36],
    [],
  );

  useEffect(() => {
    if (state !== 'recording') return undefined;
    const timer = setInterval(() => {
      setElapsedSeconds((value) => value + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [state]);

  useEffect(() => {
    if (state !== 'recording') {
      waveProgress.stopAnimation();
      waveProgress.setValue(0);
      return undefined;
    }

    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(waveProgress, {
          toValue: 1,
          duration: 520,
          useNativeDriver: true,
        }),
        Animated.timing(waveProgress, {
          toValue: 0,
          duration: 520,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [state, waveProgress]);

  useEffect(() => {
    return () => {
      recording?.stopAndUnloadAsync().catch(() => undefined);
    };
  }, [recording]);

  async function startRecording() {
    try {
      setBusy(true);
      setError(null);
      setElapsedSeconds(0);

      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setError('请允许麦克风权限后再开始录音。');
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
      nextRecording.setOnRecordingStatusUpdate((status) => {
        if (status.isRecording && typeof status.durationMillis === 'number') {
          setElapsedSeconds(Math.floor(status.durationMillis / 1000));
        }
      });
      nextRecording.setProgressUpdateInterval(500);
      await nextRecording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await nextRecording.startAsync();

      setRecording(nextRecording);
      setState('recording');
      onStarted?.();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '启动录音失败，请重试。');
    } finally {
      setBusy(false);
    }
  }

  async function pauseRecording() {
    if (!recording) return;
    try {
      setBusy(true);
      await recording.pauseAsync();
      setState('paused');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '暂停录音失败。');
    } finally {
      setBusy(false);
    }
  }

  async function resumeRecording() {
    if (!recording) return;
    try {
      setBusy(true);
      await recording.startAsync();
      setState('recording');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '继续录音失败。');
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    if (!recording) return;
    try {
      setBusy(true);
      setError(null);
      const endedAt = new Date().toISOString();
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      setState('stopped');

      if (!uri) {
        setError('录音文件保存失败。');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
      });
      onProcessing(uri, endedAt, false);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '结束录音失败。');
    } finally {
      setBusy(false);
    }
  }

  function confirmStopRecording() {
    if (state !== 'recording' && state !== 'paused') return;
    Alert.alert('结束会议？', '结束后将停止录音并进入 AI 分析。', [
      { text: '取消', style: 'cancel' },
      { text: '确认结束', style: 'destructive', onPress: stopRecording },
    ]);
  }

  if (minimized) {
    return null;
  }

  return (
    <View style={styles.container}>
      <View style={styles.titleBlock}>
        <Text numberOfLines={1} style={styles.meetingTitle}>
          {meeting.title}
        </Text>
      </View>

      <View style={styles.statusLine}>
        <View style={state === 'recording' ? styles.redDot : styles.grayDot} />
        <Text style={[styles.statusText, state === 'recording' ? styles.statusTextRecording : null]}>
          {recordingStateText[state]}
        </Text>
      </View>

      <Text style={styles.timer}>{formatDuration(elapsedSeconds)}</Text>

      <View style={styles.waveform}>
        {waveform.map((height, index) => {
          const peak = 1.15 + (index % 5) * 0.12;
          const low = 0.5 + (index % 4) * 0.08;
          const scaleY =
            state === 'recording'
              ? waveProgress.interpolate({
                  inputRange: [0, 0.5, 1],
                  outputRange: index % 2 === 0 ? [low, peak, low] : [peak, low, peak],
                })
              : 0.55;
          return (
            <Animated.View
              key={`${height}-${index}`}
              style={[
                styles.waveBar,
                {
                  height,
                  opacity: state === 'recording' ? 1 : 0.45,
                  transform: [{ scaleY }],
                },
              ]}
            />
          );
        })}
      </View>

      <View style={styles.noticePanel}>
        <Text style={styles.noticeTitle}>会后转写</Text>
        <Text style={styles.noticeText}>实时字幕已关闭。结束会议后，AI 会上传录音并生成转写、纪要和待办事项。</Text>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      {busy ? <ActivityIndicator color="#6657ff" /> : null}

      <View style={styles.actions}>
        {state === 'idle' ? (
          <View style={styles.centerAction}>
            <Pressable disabled={busy} onPress={startRecording} style={styles.startRound}>
              <Text style={styles.startRoundText}>▶</Text>
            </Pressable>
            <Text style={styles.actionLabel}>开始</Text>
          </View>
        ) : null}

        {state === 'recording' ? (
          <>
            <View style={styles.actionItem}>
              <Pressable disabled={busy} onPress={pauseRecording} style={styles.mainRound}>
                <Text style={styles.mainRoundText}>Ⅱ</Text>
              </Pressable>
              <Text style={styles.actionLabel}>暂停</Text>
            </View>
            <View style={styles.actionItem}>
              <Pressable disabled={busy} onPress={confirmStopRecording} style={styles.smallRound}>
                <Text style={styles.smallRoundText}>■</Text>
              </Pressable>
              <Text style={styles.actionLabel}>结束会议</Text>
            </View>
          </>
        ) : null}

        {state === 'paused' ? (
          <>
            <View style={styles.actionItem}>
              <Pressable disabled={busy} onPress={resumeRecording} style={styles.mainRound}>
                <Text style={styles.mainRoundText}>▶</Text>
              </Pressable>
              <Text style={styles.actionLabel}>继续</Text>
            </View>
            <View style={styles.actionItem}>
              <Pressable disabled={busy} onPress={confirmStopRecording} style={styles.smallRound}>
                <Text style={styles.smallRoundText}>■</Text>
              </Pressable>
              <Text style={styles.actionLabel}>结束会议</Text>
            </View>
          </>
        ) : null}

        {state === 'stopped' ? <Text style={styles.actionLabel}>正在进入 AI 处理...</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 0,
  },
  titleBlock: {
    alignItems: 'center',
    gap: 4,
    marginTop: 0,
  },
  meetingTitle: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
  },
  statusLine: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'center',
    marginTop: 22,
  },
  redDot: {
    backgroundColor: '#ef4444',
    borderRadius: 4,
    height: 8,
    width: 8,
  },
  grayDot: {
    backgroundColor: '#cbd5e1',
    borderRadius: 4,
    height: 8,
    width: 8,
  },
  statusText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
  },
  statusTextRecording: {
    color: '#ef4444',
  },
  timer: {
    color: '#111827',
    fontSize: 39,
    fontWeight: '900',
    letterSpacing: 0,
    marginTop: 12,
    textAlign: 'center',
  },
  waveform: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
    justifyContent: 'center',
    marginHorizontal: -18,
    marginTop: 24,
    minHeight: 78,
  },
  waveBar: {
    backgroundColor: '#7467ff',
    borderRadius: 4,
    width: 4,
  },
  noticePanel: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 14,
    borderWidth: 1,
    marginTop: 24,
    padding: 18,
  },
  noticeTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  noticeText: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: 8,
  },
  error: {
    color: '#ef4444',
    marginTop: 10,
    textAlign: 'center',
  },
  actions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 34,
    justifyContent: 'center',
    marginTop: 'auto',
    paddingBottom: 34,
  },
  actionItem: {
    alignItems: 'center',
    gap: 8,
    minWidth: 96,
  },
  centerAction: {
    alignItems: 'center',
    gap: 10,
  },
  smallRound: {
    alignItems: 'center',
    backgroundColor: '#f1f3f8',
    borderRadius: 31,
    height: 62,
    justifyContent: 'center',
    width: 62,
  },
  smallRoundText: {
    color: '#111827',
    fontSize: 19,
    fontWeight: '900',
  },
  mainRound: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 34,
    height: 68,
    justifyContent: 'center',
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.24,
    shadowRadius: 18,
    width: 68,
  },
  mainRoundText: {
    color: '#ffffff',
    fontSize: 23,
    fontWeight: '900',
  },
  startRound: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 48,
    height: 96,
    justifyContent: 'center',
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.28,
    shadowRadius: 22,
    width: 96,
  },
  startRoundText: {
    color: '#ffffff',
    fontSize: 34,
    fontWeight: '900',
  },
  actionLabel: {
    color: '#374151',
    fontSize: 13,
    fontWeight: '900',
  },
});
