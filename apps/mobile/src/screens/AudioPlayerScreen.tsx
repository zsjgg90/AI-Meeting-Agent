import { Audio, AVPlaybackStatus } from 'expo-av';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, GestureResponderEvent, Pressable, StyleSheet, Text, View } from 'react-native';

import { getMeeting, meetingAudioUrl, MeetingDetail } from '../api';

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
  const [sound, setSound] = useState<Audio.Sound | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [positionMillis, setPositionMillis] = useState(0);
  const [durationMillis, setDurationMillis] = useState(0);
  const progressWidthRef = useRef(1);

  const latestAudio = meeting?.audio_files[0] || null;
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
    return () => {
      sound?.unloadAsync().catch(() => undefined);
    };
  }, [sound]);

  function updatePlaybackStatus(status: AVPlaybackStatus) {
    if (!status.isLoaded) return;
    setIsPlaying(status.isPlaying);
    setPositionMillis(status.positionMillis);
    setDurationMillis(status.durationMillis || 0);
  }

  async function ensureSound(): Promise<Audio.Sound | null> {
    if (!meeting || !latestAudio) return null;
    if (sound) return sound;

    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    });

    const nextSound = new Audio.Sound();
    nextSound.setOnPlaybackStatusUpdate(updatePlaybackStatus);
    await nextSound.loadAsync({ uri: meetingAudioUrl(meeting.id, latestAudio.id) }, { shouldPlay: false });
    const status = await nextSound.getStatusAsync();
    updatePlaybackStatus(status);
    setSound(nextSound);
    return nextSound;
  }

  async function togglePlayback() {
    try {
      setError(null);
      const activeSound = await ensureSound();
      if (!activeSound) {
        setError('暂无可播放的录音文件。');
        return;
      }
      const status = await activeSound.getStatusAsync();
      if (status.isLoaded && status.isPlaying) {
        await activeSound.pauseAsync();
      } else {
        await activeSound.playAsync();
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '播放失败。');
    }
  }

  async function seekBy(offsetMillis: number) {
    const activeSound = await ensureSound();
    if (!activeSound) return;
    const nextPosition = Math.max(0, Math.min(durationMillis || 0, positionMillis + offsetMillis));
    await activeSound.setPositionAsync(nextPosition);
  }

  async function seekToProgress(nextProgress: number) {
    const activeSound = await ensureSound();
    if (!activeSound || !durationMillis) return;
    const nextPosition = Math.max(0, Math.min(1, nextProgress)) * durationMillis;
    setPositionMillis(nextPosition);
    await activeSound.setPositionAsync(nextPosition);
  }

  async function seekFromTouch(event: GestureResponderEvent) {
    const x = event.nativeEvent.locationX;
    const nextProgress = Math.max(0, Math.min(1, x / progressWidthRef.current));
    await seekToProgress(nextProgress);
  }

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
            onMoveShouldSetResponder={() => true}
            onResponderGrant={seekFromTouch}
            onResponderMove={seekFromTouch}
            onStartShouldSetResponder={() => true}
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
              <Text style={styles.skipText}>↺15</Text>
            </Pressable>
            <Pressable onPress={togglePlayback} style={styles.playButton}>
              <Text style={styles.playText}>{isPlaying ? 'Ⅱ' : '▶'}</Text>
            </Pressable>
            <Pressable onPress={() => seekBy(15000)} style={styles.skipButton}>
              <Text style={styles.skipText}>15↻</Text>
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
