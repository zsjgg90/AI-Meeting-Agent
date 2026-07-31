import { Audio } from 'expo-av';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Modal, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

type DisplayState = 'hidden' | 'expanded' | 'collapsed';

type Props = {
  meeting: { id: string; title: string; status: string };
  createdAt?: string;
  onProcessing: (recordingUri: string, endedAt: string, realtimeTranscriptReady: boolean) => void;
  onDiscard: () => void;
  onStarted?: () => void;
  displayState?: DisplayState;
  discardSignal?: number;
  onCollapse?: () => void;
  onExpand?: () => void;
  minimized?: boolean;
};

type RecordingState = 'idle' | 'recording' | 'paused' | 'stopped';

const stateText: Record<RecordingState, string> = {
  idle: '准备录音',
  recording: '正在录音',
  paused: '录音已暂停',
  stopped: '录音结束',
};

function formatDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, totalSeconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  const twoDigits = (value: number) => String(value).padStart(2, '0');
  if (hours > 0) return [hours, minutes, seconds].map(twoDigits).join(':');
  return [minutes, seconds].map(twoDigits).join(':');
}

function formatDateTime(value: string | undefined): string {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  const two = (next: number) => String(next).padStart(2, '0');
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())} ${two(date.getHours())}:${two(date.getMinutes())}`;
}

function meteringToLevel(metering: number | undefined): number | null {
  if (typeof metering !== 'number' || Number.isNaN(metering)) return null;
  return Math.max(0, Math.min(1, (metering + 60) / 60));
}

export function RecordingScreen({
  meeting,
  createdAt,
  onProcessing,
  onDiscard,
  onStarted,
  displayState,
  discardSignal = 0,
  onCollapse,
  onExpand,
  minimized = false,
}: Props) {
  const effectiveDisplayState: DisplayState = displayState || (minimized ? 'hidden' : 'expanded');
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const [state, setState] = useState<RecordingState>('idle');
  const stateRef = useRef<RecordingState>('idle');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const stoppingRef = useRef(false);
  const startedOnceRef = useRef(false);
  const lastDiscardSignalRef = useRef(discardSignal);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const elapsedSecondsRef = useRef(0);
  const elapsedBeforeResumeSecondsRef = useRef(0);
  const recordingStartedAtMsRef = useRef<number | null>(null);
  const [meteringLevel, setMeteringLevel] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [discardConfirmVisible, setDiscardConfirmVisible] = useState(false);

  const waveform = useMemo(() => [8, 14, 10, 19, 12, 23, 15, 21, 11, 17], []);
  const waveAnimations = useRef(waveform.map(() => new Animated.Value(0))).current;
  const sheetDragY = useRef(new Animated.Value(0)).current;
  const miniDragY = useRef(new Animated.Value(0)).current;
  const createdTimeText = useMemo(() => formatDateTime(createdAt), [createdAt]);

  const resetElapsedSeconds = useCallback((nextSeconds = 0) => {
    const safeSeconds = Math.max(0, nextSeconds);
    elapsedSecondsRef.current = safeSeconds;
    setElapsedSeconds(safeSeconds);
  }, []);

  const updateElapsedSeconds = useCallback((nextSeconds: number) => {
    const safeSeconds = Math.max(0, nextSeconds);
    const monotonicSeconds = Math.max(elapsedSecondsRef.current, safeSeconds);
    if (monotonicSeconds === elapsedSecondsRef.current) return;
    elapsedSecondsRef.current = monotonicSeconds;
    setElapsedSeconds(monotonicSeconds);
  }, []);

  const updateElapsedFromClock = useCallback(() => {
    if (recordingStartedAtMsRef.current === null) return elapsedSecondsRef.current;
    const nextSeconds = elapsedBeforeResumeSecondsRef.current + Math.floor((Date.now() - recordingStartedAtMsRef.current) / 1000);
    updateElapsedSeconds(nextSeconds);
    return nextSeconds;
  }, [updateElapsedSeconds]);

  const setRecordingState = useCallback((nextState: RecordingState) => {
    stateRef.current = nextState;
    setState(nextState);
  }, []);

  const setOperationBusy = useCallback((nextBusy: boolean) => {
    busyRef.current = nextBusy;
    setBusy(nextBusy);
  }, []);

  useEffect(() => {
    if (state !== 'recording') {
      waveAnimations.forEach((animation) => {
        animation.stopAnimation();
        animation.setValue(0);
      });
      return undefined;
    }
    const loops = waveAnimations.map((animation, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 34),
          Animated.timing(animation, { toValue: 1, duration: 420, useNativeDriver: true }),
          Animated.timing(animation, { toValue: 0, duration: 420, useNativeDriver: true }),
        ]),
      ),
    );
    loops.forEach((loop) => loop.start());
    return () => loops.forEach((loop) => loop.stop());
  }, [state, waveAnimations]);

  const releaseRecording = useCallback(async () => {
    const activeRecording = recordingRef.current;
    if (!activeRecording) return;
    recordingRef.current = null;
    setRecording(null);
    try {
      await activeRecording.stopAndUnloadAsync();
    } catch {
      // Native recording may already be stopped after a short recording or platform error.
    }
    try {
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });
    } catch {
      // Audio mode reset must not block cleanup.
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (busyRef.current || recordingRef.current || stoppingRef.current) return;
    try {
      setOperationBusy(true);
      setError(null);
      resetElapsedSeconds(0);
      elapsedBeforeResumeSecondsRef.current = 0;
      recordingStartedAtMsRef.current = null;
      setMeteringLevel(null);

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
        setMeteringLevel(meteringToLevel((status as { metering?: number }).metering));
      });
      nextRecording.setProgressUpdateInterval(500);
      await nextRecording.prepareToRecordAsync({ ...Audio.RecordingOptionsPresets.HIGH_QUALITY, isMeteringEnabled: true });
      await nextRecording.startAsync();

      recordingStartedAtMsRef.current = Date.now();
      recordingRef.current = nextRecording;
      setRecording(nextRecording);
      setRecordingState('recording');
      onStarted?.();
    } catch (nextError) {
      await releaseRecording();
      setError(nextError instanceof Error ? nextError.message : '启动录音失败，请重试。');
    } finally {
      setOperationBusy(false);
    }
  }, [onStarted, releaseRecording, resetElapsedSeconds, setOperationBusy, setRecordingState]);

  useEffect(() => {
    if (startedOnceRef.current) return;
    startedOnceRef.current = true;
    startRecording();
  }, [startRecording]);

  useEffect(() => {
    return () => {
      releaseRecording().catch(() => undefined);
    };
  }, [releaseRecording]);

  useEffect(() => {
    if (state !== 'recording') return undefined;
    const timer = setInterval(updateElapsedFromClock, 250);
    return () => clearInterval(timer);
  }, [state, updateElapsedFromClock]);

  async function pauseRecording() {
    const activeRecording = recordingRef.current;
    if (!activeRecording || busyRef.current || stoppingRef.current || stateRef.current !== 'recording') return;
    try {
      setOperationBusy(true);
      setError(null);
      const pausedAtSeconds = updateElapsedFromClock();
      elapsedBeforeResumeSecondsRef.current = pausedAtSeconds;
      recordingStartedAtMsRef.current = null;
      setRecordingState('paused');
      setMeteringLevel(null);
      await activeRecording.pauseAsync();
    } catch (nextError) {
      recordingStartedAtMsRef.current = Date.now();
      setRecordingState('recording');
      setError(nextError instanceof Error ? nextError.message : '暂停录音失败。');
    } finally {
      setOperationBusy(false);
    }
  }

  async function resumeRecording() {
    const activeRecording = recordingRef.current;
    if (!activeRecording || busyRef.current || stoppingRef.current || stateRef.current !== 'paused') return;
    try {
      setOperationBusy(true);
      setError(null);
      recordingStartedAtMsRef.current = Date.now();
      setRecordingState('recording');
      await activeRecording.startAsync();
    } catch (nextError) {
      recordingStartedAtMsRef.current = null;
      setRecordingState('paused');
      setError(nextError instanceof Error ? nextError.message : '继续录音失败。');
    } finally {
      setOperationBusy(false);
    }
  }

  async function stopRecording() {
    const activeRecording = recordingRef.current;
    if (!activeRecording || stoppingRef.current || (stateRef.current !== 'recording' && stateRef.current !== 'paused')) return;
    try {
      stoppingRef.current = true;
      setOperationBusy(true);
      setError(null);
      const endedAt = new Date().toISOString();
      if (stateRef.current === 'recording') {
        elapsedBeforeResumeSecondsRef.current = updateElapsedFromClock();
        recordingStartedAtMsRef.current = null;
      }
      const uriBeforeStop = activeRecording.getURI();
      await activeRecording.stopAndUnloadAsync();
      const uri = uriBeforeStop || activeRecording.getURI();
      recordingRef.current = null;
      setRecording(null);
      setRecordingState('stopped');
      setMeteringLevel(null);
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });
      if (!uri) {
        setError('录音文件保存失败。');
        return;
      }
      onProcessing(uri, endedAt, false);
    } catch (nextError) {
      stoppingRef.current = false;
      setError(nextError instanceof Error ? nextError.message : '结束录音失败。');
    } finally {
      setOperationBusy(false);
    }
  }

  async function discardRecording() {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    setDiscardConfirmVisible(false);
    setOperationBusy(true);
    await releaseRecording();
    setRecordingState('stopped');
    onDiscard();
  }

  useEffect(() => {
    if (discardSignal === lastDiscardSignalRef.current) return;
    lastDiscardSignalRef.current = discardSignal;
    discardRecording().catch((nextError) => {
      setError(nextError instanceof Error ? nextError.message : '放弃录音失败。');
    });
  }, [discardSignal]);

  function collapseSheet() {
    sheetDragY.setValue(0);
    onCollapse?.();
  }

  function expandMiniBar() {
    miniDragY.setValue(0);
    onExpand?.();
  }

  const sheetPanResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 4 && Math.abs(gesture.dy) > Math.abs(gesture.dx),
      onPanResponderMove: (_, gesture) => sheetDragY.setValue(Math.max(0, gesture.dy)),
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dy > 78 || gesture.vy > 0.95) {
          collapseSheet();
          return;
        }
        Animated.spring(sheetDragY, { toValue: 0, useNativeDriver: true, bounciness: 0, speed: 18 }).start();
      },
    }),
  ).current;

  const miniPanResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 3 && Math.abs(gesture.dy) > Math.abs(gesture.dx) * 1.15,
      onPanResponderMove: (_, gesture) => {
        const resistedDy = gesture.dy < 0 ? gesture.dy * 0.86 : gesture.dy * 0.18;
        miniDragY.setValue(Math.min(10, Math.max(-86, resistedDy)));
      },
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dy < -46 || gesture.vy < -0.62) {
          expandMiniBar();
          return;
        }
        Animated.spring(miniDragY, { toValue: 0, useNativeDriver: true, tension: 170, friction: 20 }).start();
      },
    }),
  ).current;

  const hasMetering = meteringLevel !== null;
  const canControl = Boolean(recording) && !busy && !stoppingRef.current;
  const showDisabledControl = !recording || stoppingRef.current;
  const isRecording = state === 'recording';
  const isPaused = state === 'paused';
  const timerText = formatDuration(elapsedSeconds);
  const controlIconName = isPaused ? 'play' : 'pause';
  const miniScale = miniDragY.interpolate({
    inputRange: [-86, 0, 10],
    outputRange: [1.015, 1, 0.995],
    extrapolate: 'clamp',
  });
  const statusLabel = isPaused ? '录音已暂停' : isRecording ? '正在录音' : stateText[state];

  function Waveform({ compact = false }: { compact?: boolean }) {
    return (
      <View style={[styles.waveform, compact ? styles.waveformCompact : null, { opacity: isRecording ? 1 : 0.34 }]}>
        {waveform.map((baseHeight, index) => {
          const level = meteringLevel || 0;
          const scaleY = isRecording
            ? waveAnimations[index].interpolate({
                inputRange: [0, 1],
                outputRange: hasMetering ? [0.68 + level * 0.12, 1 + level * 0.4] : [0.62, 1.18],
              })
            : 0.42;
          return (
            <Animated.View
              key={`${baseHeight}-${index}`}
              style={[
                styles.waveBar,
                compact ? styles.waveBarCompact : null,
                { height: compact ? Math.max(9, baseHeight * 0.61) : baseHeight, transform: [{ scaleY }] },
              ]}
            />
          );
        })}
      </View>
    );
  }

  const pauseResumeButton = (
    <Pressable
      disabled={!canControl || (!isRecording && !isPaused)}
      onPress={isPaused ? resumeRecording : pauseRecording}
      style={[styles.roundButton, isPaused ? styles.resumeButton : null, showDisabledControl ? styles.disabledControl : null]}
    >
      {busy && state === 'idle' ? <ActivityIndicator color="#ffffff" size="small" /> : <LucideIcon name={controlIconName} color="#ffffff" size={21} strokeWidth={2.8} />}
    </Pressable>
  );

  const endButton = (
    <Pressable disabled={!canControl || (!isRecording && !isPaused)} onPress={stopRecording} style={[styles.stopButton, showDisabledControl ? styles.disabledControl : null]}>
      <View style={styles.stopSquare} />
    </Pressable>
  );

  if (effectiveDisplayState === 'hidden') return null;

  return (
    <>
      {effectiveDisplayState === 'expanded' ? (
        <View pointerEvents="box-none" style={styles.overlay}>
          <Animated.View style={[styles.sheet, { transform: [{ translateY: sheetDragY }] }]}>
            <View {...sheetPanResponder.panHandlers} style={styles.dragZone}>
              <View style={styles.dragHandle} />
            </View>
            <View style={styles.sheetTopRow}>
              <Pressable onPress={onCollapse} hitSlop={10} style={styles.iconButton}>
                <LucideIcon name="chevron-down" color="#111827" size={25} strokeWidth={2.5} />
              </Pressable>
            </View>
            <View style={styles.titleBlock}>
              <Text style={[styles.statusText, isRecording ? styles.statusTextRecording : null]}>{statusLabel}</Text>
              <Text numberOfLines={2} style={styles.meetingTitle}>{meeting.title}</Text>
              <Text style={styles.createdAt}>{createdTimeText}</Text>
            </View>
            <View style={styles.blankArea}>
              {error ? <Text style={styles.error}>{error}</Text> : null}
              {busy && state === 'idle' ? (
                <View style={styles.startingRow}>
                  <ActivityIndicator color="#2B6CFF" size="small" />
                  <Text style={styles.startingText}>正在启动录音...</Text>
                </View>
              ) : null}
            </View>
            <View style={styles.controlPanel}>
              <View style={styles.soundprintRow}>
                <Waveform />
                <Text numberOfLines={1} style={styles.timerLarge}>{timerText}</Text>
              </View>
              <View style={styles.controlButtons}>{pauseResumeButton}{endButton}</View>
            </View>
          </Animated.View>
        </View>
      ) : null}

      {effectiveDisplayState === 'collapsed' ? (
        <Animated.View {...miniPanResponder.panHandlers} style={styles.miniBar}>
          <Animated.View style={[styles.miniPanel, { transform: [{ translateY: miniDragY }, { scale: miniScale }] }]}>
            <View style={styles.miniDragZone}>
              <View style={styles.miniDragHandle} />
            </View>
            <Pressable onPress={onExpand} style={styles.miniContentRow}>
              <View style={styles.miniWaveBlock}>
                <Waveform compact />
                <Text numberOfLines={1} style={styles.miniTimer}>{timerText}</Text>
              </View>
              <View style={styles.miniActions}>{pauseResumeButton}{endButton}</View>
            </Pressable>
          </Animated.View>
        </Animated.View>
      ) : null}

      <Modal transparent visible={discardConfirmVisible} animationType="fade" onRequestClose={() => setDiscardConfirmVisible(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <View style={styles.modalIcon}>
              <LucideIcon name="triangle-alert" color="#ef4444" size={28} strokeWidth={2.3} />
            </View>
            <Text style={styles.modalTitle}>放弃本次录制？</Text>
            <Text style={styles.modalText}>放弃后将停止录音并清理本次自动创建的会议。</Text>
            <View style={styles.modalActions}>
              <Pressable disabled={busy} onPress={discardRecording} style={[styles.modalPrimary, styles.modalDanger]}>
                {busy ? <ActivityIndicator color="#ffffff" size="small" /> : <Text style={styles.modalPrimaryText}>放弃录音</Text>}
              </Pressable>
              <Pressable disabled={busy} onPress={() => setDiscardConfirmVisible(false)} style={styles.modalSecondary}>
                <Text style={styles.modalSecondaryText}>继续录制</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(17, 24, 39, 0.24)', justifyContent: 'flex-end', zIndex: 50 },
  sheet: { backgroundColor: '#ffffff', borderTopLeftRadius: 32, borderTopRightRadius: 32, elevation: 18, height: '84%', paddingBottom: 16, paddingHorizontal: 18, shadowColor: '#111827', shadowOffset: { width: 0, height: -12 }, shadowOpacity: 0.16, shadowRadius: 26 },
  dragZone: { alignItems: 'center', paddingBottom: 8, paddingTop: 10 },
  dragHandle: { backgroundColor: '#d8dde8', borderRadius: 999, height: 5, width: 48 },
  sheetTopRow: { alignItems: 'flex-start', flexDirection: 'row', marginTop: -14, minHeight: 42 },
  iconButton: { alignItems: 'center', backgroundColor: '#f5f7fb', borderRadius: 21, height: 42, justifyContent: 'center', width: 42 },
  titleBlock: { marginTop: 6 },
  statusText: { color: '#6b7280', fontSize: 13, fontWeight: '900' },
  statusTextRecording: { color: '#ef4444' },
  meetingTitle: { color: '#111827', fontSize: 20, fontWeight: '900', lineHeight: 27, marginTop: 7 },
  createdAt: { color: '#9ca3af', fontSize: 12, fontWeight: '800', marginTop: 5 },
  blankArea: { alignItems: 'center', flex: 1, justifyContent: 'center', paddingHorizontal: 10 },
  startingRow: { alignItems: 'center', flexDirection: 'row', gap: 8, marginTop: 18 },
  startingText: { color: '#2B6CFF', fontSize: 13, fontWeight: '900' },
  error: { color: '#ef4444', fontSize: 13, fontWeight: '800', lineHeight: 19, marginTop: 14, textAlign: 'center' },
  controlPanel: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 24, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', minHeight: 104, paddingHorizontal: 16, shadowColor: '#6b7280', shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.08, shadowRadius: 20, elevation: 4 },
  soundprintRow: { alignItems: 'center', flex: 1, flexDirection: 'row', gap: 12, minWidth: 0 },
  timerLarge: { color: '#111827', fontSize: 24, fontVariant: ['tabular-nums'], fontWeight: '900', includeFontPadding: false, textAlign: 'left', width: 92 },
  waveform: { alignItems: 'center', flexDirection: 'row', gap: 2, height: 27, overflow: 'hidden', width: 52 },
  waveformCompact: { gap: 2, height: 24, width: 52 },
  waveBar: { backgroundColor: '#111827', borderRadius: 4, width: 2 },
  waveBarCompact: { width: 2 },
  controlButtons: { alignItems: 'center', flexDirection: 'row', gap: 12, marginLeft: 12 },
  roundButton: { alignItems: 'center', backgroundColor: '#2B6CFF', borderRadius: 28, height: 56, justifyContent: 'center', shadowColor: '#2B6CFF', shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.24, shadowRadius: 18, width: 56, elevation: 5 },
  resumeButton: { backgroundColor: '#f97316', shadowColor: '#f97316' },
  stopButton: { alignItems: 'center', backgroundColor: '#eef0f5', borderRadius: 28, height: 56, justifyContent: 'center', width: 56 },
  stopSquare: { backgroundColor: '#111827', borderRadius: 5, height: 19, width: 19 },
  disabledControl: { opacity: 0.55 },
  miniBar: { backgroundColor: '#ffffff', bottom: 0, elevation: 24, left: 0, minHeight: 120, position: 'absolute', right: 0, shadowColor: '#111827', shadowOffset: { width: 0, height: -10 }, shadowOpacity: 0.16, shadowRadius: 22, zIndex: 95 },
  miniPanel: { backgroundColor: '#ffffff', borderColor: '#e6ebf2', borderTopLeftRadius: 28, borderTopRightRadius: 28, borderWidth: 1, minHeight: 120, paddingHorizontal: 22, paddingTop: 7 },
  miniDragZone: { alignItems: 'center', height: 24, justifyContent: 'center' },
  miniDragHandle: { backgroundColor: '#d8dde8', borderRadius: 999, height: 5, width: 48 },
  miniContentRow: { alignItems: 'center', flexDirection: 'row', gap: 10, justifyContent: 'space-between', minHeight: 81 },
  miniWaveBlock: { alignItems: 'center', flex: 1, flexDirection: 'row', gap: 12, minWidth: 0 },
  miniTimer: { color: '#111827', fontSize: 22, fontVariant: ['tabular-nums'], fontWeight: '900', includeFontPadding: false, textAlign: 'left', width: 76 },
  miniActions: { alignItems: 'center', flexDirection: 'row', gap: 10, transform: [{ scale: 1.01 }] },
  modalBackdrop: { alignItems: 'center', backgroundColor: 'rgba(17, 24, 39, 0.42)', flex: 1, justifyContent: 'center', padding: 28 },
  modalCard: { alignItems: 'center', backgroundColor: '#ffffff', borderRadius: 24, padding: 22, width: '100%' },
  modalIcon: { alignItems: 'center', backgroundColor: '#f3f4f6', borderRadius: 32, height: 64, justifyContent: 'center', marginBottom: 14, width: 64 },
  modalTitle: { color: '#111827', fontSize: 18, fontWeight: '900', textAlign: 'center' },
  modalText: { color: '#6b7280', fontSize: 14, fontWeight: '700', lineHeight: 22, marginTop: 8, textAlign: 'center' },
  modalActions: { gap: 10, marginTop: 24, width: '100%' },
  modalPrimary: { alignItems: 'center', backgroundColor: '#111827', borderRadius: 14, minHeight: 46, justifyContent: 'center' },
  modalDanger: { backgroundColor: '#ef4444' },
  modalPrimaryText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
  modalSecondary: { alignItems: 'center', backgroundColor: '#f3f4f6', borderRadius: 14, minHeight: 46, justifyContent: 'center' },
  modalSecondaryText: { color: '#4b5563', fontSize: 14, fontWeight: '900' },
});
