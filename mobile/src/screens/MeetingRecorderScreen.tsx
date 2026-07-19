import { Audio } from 'expo-av';
import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  createMeeting,
  getMeeting,
  getTask,
  MeetingRead,
  startTranscription,
  uploadAudio,
} from '../api';

type Step = 'idle' | 'recording' | 'uploaded' | 'processing' | 'completed' | 'failed';

export default function MeetingRecorderScreen() {
  const [apiBaseUrl, setApiBaseUrl] = useState('http://localhost:8000');
  const [title, setTitle] = useState('MVP Demo Meeting');
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [meeting, setMeeting] = useState<MeetingRead | null>(null);
  const [step, setStep] = useState<Step>('idle');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Create a meeting, record audio, then upload and analyze.');

  const canRecord = useMemo(() => !busy && step !== 'recording', [busy, step]);

  async function startRecording() {
    try {
      setBusy(true);
      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Microphone permission is required.');
        return;
      }

      const created = await createMeeting(apiBaseUrl, title || 'Untitled meeting');
      setMeetingId(created.meeting_id);
      setMeeting(null);
      setTaskId(null);

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const { recording: nextRecording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      setRecording(nextRecording);
      setRecordingUri(null);
      setStep('recording');
      setMessage(`Recording meeting ${created.meeting_id}`);
    } catch (error) {
      setStep('failed');
      setMessage(error instanceof Error ? error.message : 'Failed to start recording.');
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    if (!recording || !meetingId) return;
    try {
      setBusy(true);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);
      setRecordingUri(uri);
      if (!uri) throw new Error('Recording URI is empty.');

      setMessage('Uploading audio...');
      await uploadAudio(apiBaseUrl, meetingId, uri);
      setStep('uploaded');

      setMessage('Starting transcription and AI analysis...');
      const task = await startTranscription(apiBaseUrl, meetingId);
      setTaskId(task.task_id);
      setStep('processing');
      pollTask(task.task_id, meetingId);
    } catch (error) {
      setStep('failed');
      setMessage(error instanceof Error ? error.message : 'Failed to stop and upload recording.');
    } finally {
      setBusy(false);
    }
  }

  async function pollTask(nextTaskId: string, nextMeetingId: string) {
    const timer = setInterval(async () => {
      try {
        const task = await getTask(apiBaseUrl, nextTaskId);
        setMessage(`Task status: ${task.status}`);
        if (task.status === 'completed') {
          clearInterval(timer);
          const latestMeeting = await getMeeting(apiBaseUrl, nextMeetingId);
          setMeeting(latestMeeting);
          setStep('completed');
          setMessage('Meeting analysis completed.');
        }
        if (task.status === 'failed') {
          clearInterval(timer);
          setStep('failed');
          setMessage(task.error_message || 'Task failed.');
        }
      } catch (error) {
        clearInterval(timer);
        setStep('failed');
        setMessage(error instanceof Error ? error.message : 'Failed to poll task.');
      }
    }, 2500);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Meeting Agent MVP</Text>

        <View style={styles.panel}>
          <Text style={styles.label}>API Base URL</Text>
          <TextInput
            value={apiBaseUrl}
            onChangeText={setApiBaseUrl}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <Text style={styles.label}>Meeting title</Text>
          <TextInput value={title} onChangeText={setTitle} style={styles.input} />
        </View>

        <View style={styles.actions}>
          {step === 'recording' ? (
            <Pressable disabled={busy} style={[styles.button, styles.stopButton]} onPress={stopRecording}>
              <Text style={styles.buttonText}>End Recording</Text>
            </Pressable>
          ) : (
            <Pressable disabled={!canRecord} style={styles.button} onPress={startRecording}>
              <Text style={styles.buttonText}>Start Recording</Text>
            </Pressable>
          )}
        </View>

        <View style={styles.statusPanel}>
          <View style={styles.statusHeader}>
            <Text style={styles.status}>Status: {step}</Text>
            {busy || step === 'processing' ? <ActivityIndicator /> : null}
          </View>
          <Text style={styles.message}>{message}</Text>
          {meetingId ? <Text style={styles.meta}>Meeting: {meetingId}</Text> : null}
          {taskId ? <Text style={styles.meta}>Task: {taskId}</Text> : null}
          {recordingUri ? <Text style={styles.meta}>Audio: {recordingUri}</Text> : null}
        </View>

        {meeting?.output ? (
          <View style={styles.result}>
            <Text style={styles.sectionTitle}>Summary</Text>
            <Text style={styles.paragraph}>{meeting.output.summary}</Text>

            <Text style={styles.sectionTitle}>Speaker Segments</Text>
            {meeting.output.speaker_segments.map((segment, index) => (
              <Text key={`${segment.speaker}-${index}`} style={styles.paragraph}>
                {segment.speaker}: {segment.text}
              </Text>
            ))}

            <Text style={styles.sectionTitle}>Action Items</Text>
            {meeting.output.action_items.map((item, index) => (
              <Text key={`action-${index}`} style={styles.paragraph}>
                - {item.task || JSON.stringify(item)}
              </Text>
            ))}

            <Text style={styles.sectionTitle}>Decisions</Text>
            {meeting.output.decisions.map((item, index) => (
              <Text key={`decision-${index}`} style={styles.paragraph}>
                - {item.decision || JSON.stringify(item)}
              </Text>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f7f7f4',
  },
  container: {
    gap: 16,
    padding: 20,
  },
  title: {
    color: '#1d2939',
    fontSize: 28,
    fontWeight: '700',
  },
  panel: {
    gap: 8,
  },
  label: {
    color: '#475467',
    fontSize: 14,
    fontWeight: '600',
  },
  input: {
    minHeight: 46,
    borderColor: '#d0d5dd',
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: '#ffffff',
    paddingHorizontal: 12,
    color: '#101828',
  },
  actions: {
    flexDirection: 'row',
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#2563eb',
    borderRadius: 8,
    flex: 1,
    minHeight: 48,
    justifyContent: 'center',
  },
  stopButton: {
    backgroundColor: '#dc2626',
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  statusPanel: {
    backgroundColor: '#ffffff',
    borderColor: '#e4e7ec',
    borderRadius: 8,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  statusHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  status: {
    color: '#101828',
    fontSize: 16,
    fontWeight: '700',
  },
  message: {
    color: '#344054',
    lineHeight: 20,
  },
  meta: {
    color: '#667085',
    fontSize: 12,
  },
  result: {
    backgroundColor: '#ffffff',
    borderColor: '#e4e7ec',
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  sectionTitle: {
    color: '#101828',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  paragraph: {
    color: '#344054',
    lineHeight: 22,
  },
});
