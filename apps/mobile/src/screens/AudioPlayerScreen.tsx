import { Audio, AVPlaybackStatus } from 'expo-av';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

import { getMeeting, meetingAudioUrl, MeetingDetail } from '../api';
import { LucideIcon } from '../components/LucideIcon';
import { chooseMeetingAudioFile } from '../utils/audioFiles';

type Props = {
  meetingId: string;
};

function formatTime(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function durationFromMeeting(meeting: MeetingDetail | null): string {
  if (!meeting) return '';
  const lastSegment = meeting.transcript_segments[meeting.transcript_segments.length - 1];
  if (lastSegment?.end_time) {
    const minutes = Math.floor(lastSegment.end_time / 60);
    const seconds = Math.round(lastSegment.end_time % 60);
    return minutes ? `${minutes}分${seconds}秒` : `${seconds}秒`;
  }
  return '录音文件';
}

export function AudioPlayerScreen({ meetingId }: Props) {
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [, setSound] = useState<Audio.Sound | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [positionMillis, setPositionMillis] = useState(0);
  const [durationMillis, setDurationMillis] = useState(0);
  const soundRef = useRef<Audio.Sound | null>(null);
  const loadedAudioKeyRef = useRef<string | null>(null);
  const audioBusyRef = useRef(false);
  const progressWidthRef = useRef(1);
  const pendingSeekMillisRef = useRef<number | null>(null);
  const isScrubbingRef = useRef(false);

  const selectedAudio = useMemo(() => chooseMeetingAudioFile(meeting?.audio_files || []), [meeting?.audio_files]);
  const selectedAudioKey = meeting && selectedAudio ? `${meeting.id}:${selectedAudio.id}` : null;
  const progress = durationMillis > 0 ? Math.min(1, positionMillis / durationMillis) : 0;
  const speakerCount = useMemo(() => {
    const speakerLabels = new Set(
      (meeting?.transcript_segments || [])
        .map((segment) => segment.speaker_name || segment.speaker_label)
        .filter(Boolean),
    );
    if (speakerLabels.size > 0) return speakerLabels.size;
    return meeting?.speaker_mappings.length || 0;
  }, [meeting?.speaker_mappings.length, meeting?.transcript_segments]);

  const waveform = useMemo(
    () => [24, 31, 19, 38, 27, 44, 33, 58, 41, 68, 35, 47, 30, 43, 37, 52, 34, 45, 29, 40, 32, 50, 28, 36, 22],
    [],
  );

  const loadMeeting = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getMeeting(meetingId);
      setMeeting(data);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '录音详情加载失败。');
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    loadMeeting();
  }, [loadMeeting]);

  useEffect(() => {
    const activeSound = soundRef.current;
    soundRef.current = null;
    loadedAudioKeyRef.current = null;
    audioBusyRef.current = false;
    setSound(null);
    setIsPlaying(false);
    setPositionMillis(0);
    setDurationMillis(0);
    activeSound?.unloadAsync().catch(() => undefined);
  }, [meetingId]);

  useEffect(() => {
    if (loadedAudioKeyRef.current === null || loadedAudioKeyRef.current === selectedAudioKey) return;
    const activeSound = soundRef.current;
    soundRef.current = null;
    loadedAudioKeyRef.current = null;
    audioBusyRef.current = false;
    setSound(null);
    setIsPlaying(false);
    setPositionMillis(0);
    setDurationMillis(0);
    activeSound?.unloadAsync().catch(() => undefined);
  }, [selectedAudioKey]);

  useEffect(
    () => () => {
      soundRef.current?.unloadAsync().catch(() => undefined);
      soundRef.current = null;
      loadedAudioKeyRef.current = null;
    },
    [],
  );

  function updatePlaybackStatus(status: AVPlaybackStatus) {
    if (!status.isLoaded) return;
    setIsPlaying(status.isPlaying);
    if (!isScrubbingRef.current) setPositionMillis(status.positionMillis);
    setDurationMillis(status.durationMillis || 0);
  }

  async function ensureSound(): Promise<Audio.Sound | null> {
    if (!meeting || !selectedAudio || !selectedAudioKey) return null;
    if (soundRef.current && loadedAudioKeyRef.current === selectedAudioKey) return soundRef.current;
    if (soundRef.current) {
      const staleSound = soundRef.current;
      soundRef.current = null;
      loadedAudioKeyRef.current = null;
      setSound(null);
      setIsPlaying(false);
      await staleSound.unloadAsync().catch(() => undefined);
    }

    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    });

    const nextSound = new Audio.Sound();
    nextSound.setOnPlaybackStatusUpdate(updatePlaybackStatus);
    await nextSound.loadAsync({ uri: meetingAudioUrl(meeting.id, selectedAudio.id) }, { shouldPlay: false });
    soundRef.current = nextSound;
    loadedAudioKeyRef.current = selectedAudioKey;
    const status = await nextSound.getStatusAsync();
    updatePlaybackStatus(status);
    setSound(nextSound);
    return nextSound;
  }

  async function runAudioAction(action: (activeSound: Audio.Sound) => Promise<void>) {
    if (audioBusyRef.current) return;
    audioBusyRef.current = true;
    try {
      setError(null);
      const activeSound = await ensureSound();
      if (!activeSound) {
        setError('暂无可播放的录音文件。');
        return;
      }
      await action(activeSound);
      updatePlaybackStatus(await activeSound.getStatusAsync());
    } catch (nextError) {
      setIsPlaying(false);
      setError(nextError instanceof Error ? nextError.message : '播放失败。');
    } finally {
      audioBusyRef.current = false;
    }
  }

  async function togglePlayback() {
    await runAudioAction(async (activeSound) => {
      const status = await activeSound.getStatusAsync();
      if (status.isLoaded && status.isPlaying) {
        await activeSound.pauseAsync();
      } else {
        await activeSound.playAsync();
      }
    });
  }

  async function seekBy(offsetMillis: number) {
    await runAudioAction(async (activeSound) => {
      const status = await activeSound.getStatusAsync();
      if (!status.isLoaded) return;
      const duration = status.durationMillis || durationMillis || 0;
      const nextPosition = Math.max(0, Math.min(duration || Number.MAX_SAFE_INTEGER, status.positionMillis + offsetMillis));
      await activeSound.setPositionAsync(nextPosition);
    });
  }

  async function seekToProgress(nextProgress: number) {
    if (!durationMillis) return;
    await runAudioAction(async (activeSound) => {
      const nextPosition = Math.max(0, Math.min(1, nextProgress)) * durationMillis;
      setPositionMillis(nextPosition);
      await activeSound.setPositionAsync(nextPosition);
    });
  }

  function previewProgressSeek(x: number) {
    const nextProgress = Math.max(0, Math.min(1, x / progressWidthRef.current));
    if (!durationMillis) return;
    const nextMillis = nextProgress * durationMillis;
    pendingSeekMillisRef.current = nextMillis;
    isScrubbingRef.current = true;
    setPositionMillis(nextMillis);
  }

  function commitProgressSeek() {
    const nextMillis = pendingSeekMillisRef.current;
    pendingSeekMillisRef.current = null;
    isScrubbingRef.current = false;
    if (nextMillis === null || !durationMillis) return;
    void seekToProgress(nextMillis / durationMillis);
  }

  const progressPanResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: () => durationMillis > 0,
        onPanResponderGrant: (event) => previewProgressSeek(event.nativeEvent.locationX),
        onPanResponderMove: (event) => previewProgressSeek(event.nativeEvent.locationX),
        onPanResponderRelease: commitProgressSeek,
        onPanResponderTerminate: commitProgressSeek,
        onStartShouldSetPanResponder: () => durationMillis > 0,
      }),
    [durationMillis],
  );

  return (
    <View style={styles.container}>
      {loading ? <ActivityIndicator color="#6657ff" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {meeting ? (
        <View style={styles.playerCard}>
          <View style={styles.meetingRow}>
            <View style={styles.meetingInfo}>
              <Text numberOfLines={1} style={styles.meetingTitle}>
                {meeting.title}
              </Text>
              <Text style={styles.meetingMeta}>
                {new Date(meeting.created_at).toLocaleDateString()} · {durationFromMeeting(meeting)}
              </Text>
              <Text style={styles.peopleText}>{speakerCount}人</Text>
            </View>
          </View>

          <View style={styles.waveform}>
            {waveform.map((height, index) => (
              <View
                key={`${height}-${index}`}
                style={[
                  styles.waveBar,
                  {
                    height,
                    opacity: index / waveform.length <= progress ? 1 : 0.22,
                  },
                ]}
              />
            ))}
          </View>

          <View
            onLayout={(event) => {
              progressWidthRef.current = Math.max(1, event.nativeEvent.layout.width);
            }}
            {...progressPanResponder.panHandlers}
            style={styles.progressTrack}
          >
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
            <View style={[styles.progressThumb, { left: `${progress * 100}%` }]} />
          </View>

          <View style={styles.timeRow}>
            <Text style={styles.currentTime}>{formatTime(positionMillis)}</Text>
            <Text style={styles.totalTime}>{formatTime(durationMillis)}</Text>
          </View>

          <View style={styles.controls}>
            <Pressable onPress={() => seekBy(-15000)} style={styles.skipButton}>
              <Text style={styles.skipText}>-15</Text>
            </Pressable>
            <Pressable onPress={togglePlayback} style={styles.playButton}>
              <LucideIcon name={isPlaying ? 'pause' : 'play'} color="#ffffff" size={28} strokeWidth={2.6} />
            </Pressable>
            <Pressable onPress={() => seekBy(15000)} style={styles.skipButton}>
              <Text style={styles.skipText}>+15</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 8,
  },
  playerCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    paddingBottom: 18,
  },
  meetingRow: {
    alignItems: 'flex-start',
    borderBottomColor: '#eef0f6',
    borderBottomWidth: 1,
    flexDirection: 'row',
    padding: 16,
  },
  meetingInfo: {
    flex: 1,
    gap: 8,
  },
  meetingTitle: {
    color: '#111827',
    fontSize: 17,
    fontWeight: '900',
  },
  meetingMeta: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
  },
  peopleText: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '900',
  },
  waveform: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 3,
    justifyContent: 'center',
    minHeight: 96,
    paddingHorizontal: 14,
    paddingTop: 28,
  },
  waveBar: {
    backgroundColor: '#6657ff',
    borderRadius: 3,
    width: 3,
  },
  progressTrack: {
    backgroundColor: '#eceeff',
    borderRadius: 3,
    height: 6,
    marginHorizontal: 16,
    marginTop: 8,
  },
  progressFill: {
    backgroundColor: '#6657ff',
    borderRadius: 3,
    height: 6,
  },
  progressThumb: {
    backgroundColor: '#6657ff',
    borderColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 2,
    height: 16,
    marginLeft: -8,
    position: 'absolute',
    top: -5,
    width: 16,
  },
  timeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  currentTime: {
    color: '#6657ff',
    fontSize: 12,
    fontWeight: '900',
  },
  totalTime: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '800',
  },
  controls: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 26,
    justifyContent: 'center',
    paddingTop: 18,
  },
  skipButton: {
    alignItems: 'center',
    backgroundColor: '#f4f5fb',
    borderRadius: 24,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  skipText: {
    color: '#111827',
    fontSize: 12,
    fontWeight: '900',
  },
  playButton: {
    alignItems: 'center',
    backgroundColor: '#111827',
    borderRadius: 34,
    height: 68,
    justifyContent: 'center',
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.24,
    shadowRadius: 18,
    width: 68,
  },
  playText: {
    color: '#ffffff',
    fontSize: 27,
    fontWeight: '900',
  },
  error: {
    color: '#ef4444',
    marginBottom: 12,
    textAlign: 'center',
  },
});
