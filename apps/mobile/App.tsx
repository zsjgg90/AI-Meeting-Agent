import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, BackHandler, Modal, SafeAreaView, StyleSheet, Text, View } from 'react-native';

import {
  analyzeMeeting,
  createMeeting,
  deleteMeeting,
  getMeeting,
  getMeetingSummary,
  getMeetingTranscript,
  KnowledgeItem,
  Meeting,
  MeetingDetail,
  MeetingSummary,
  processMeeting,
  TaskListItem,
  updateMeeting,
  uploadAudio,
} from './src/api';
import { AppHeader } from './src/components/AppHeader';
import { BottomNav, BottomTab } from './src/components/BottomNav';
import { featureFlags } from './src/config';
import { AgentRecordDetailScreen, AIAssistantScreen, AllAgentRecordsScreen } from './src/screens/AIAssistantScreen';
import { AIProcessingScreen } from './src/screens/AIProcessingScreen';
import { AboutScreen } from './src/screens/AboutScreen';
import { AddVoiceprintSampleScreen } from './src/screens/AddVoiceprintSampleScreen';
import { AudioPlayerScreen } from './src/screens/AudioPlayerScreen';
import { EditProfileScreen } from './src/screens/EditProfileScreen';
import { FaqScreen } from './src/screens/FaqScreen';
import { FeedbackScreen } from './src/screens/FeedbackScreen';
import { HelpFeedbackScreen } from './src/screens/HelpFeedbackScreen';
import { ImportMeetingScreen } from './src/screens/ImportMeetingScreen';
import { KnowledgeBaseScreen } from './src/screens/KnowledgeBaseScreen';
import { KnowledgeDecisionListScreen } from './src/screens/KnowledgeDecisionListScreen';
import { KnowledgeIssueRiskScreen } from './src/screens/KnowledgeIssueRiskScreen';
import { KnowledgeMeetingListScreen } from './src/screens/KnowledgeMeetingListScreen';
import { KnowledgeSearchResultsScreen } from './src/screens/KnowledgeSearchResultsScreen';
import { KnowledgeSearchScreen } from './src/screens/KnowledgeSearchScreen';
import { MeetingDetailScreen } from './src/screens/MeetingDetailScreen';
import { MeetingListScreen } from './src/screens/MeetingListScreen';
import { NewMeetingScreen } from './src/screens/NewMeetingScreen';
import { ProfileScreen } from './src/screens/ProfileScreen';
import { PushConfigScreen } from './src/screens/PushConfigScreen';
import { RecordingScreen } from './src/screens/RecordingScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { TaskSearchScreen } from './src/screens/TaskSearchScreen';
import { TaskDetailScreen } from './src/screens/TaskDetailScreen';
import { TodoScreen } from './src/screens/TodoScreen';
import { VoiceprintManagementScreen } from './src/screens/VoiceprintManagementScreen';
import { defaultMeetingTitle } from './src/utils/meetingTitle';

type Route =
  | { name: 'home' }
  | { name: 'allMeetings' }
  | { name: 'knowledge' }
  | { name: 'knowledgeMeetings' }
  | { name: 'knowledgeDecisions' }
  | { name: 'knowledgeIssueRisks' }
  | { name: 'knowledgeSearch'; query?: string }
  | { name: 'knowledgeSearchResults'; query: string }
  | { name: 'ai' }
  | { name: 'aiRecords' }
  | { name: 'aiRecordDetail'; recordId: string }
  | { name: 'todo' }
  | { name: 'taskSearch' }
  | { name: 'me' }
  | { name: 'voiceprintManagement' }
  | { name: 'pushConfig' }
  | { name: 'addVoiceprintSample' }
  | { name: 'editProfile' }
  | { name: 'settings' }
  | { name: 'helpFeedback' }
  | { name: 'faq' }
  | { name: 'feedback' }
  | { name: 'about' }
  | { name: 'newMeeting' }
  | { name: 'importMeeting' }
  | { name: 'recording'; meeting: Pick<Meeting, 'id' | 'title' | 'status'> }
  | { name: 'audioPlayer'; meetingId: string }
  | {
      name: 'processing';
      meeting: Pick<Meeting, 'id' | 'title' | 'status'>;
      recordingUri: string;
      endedAt: string;
      realtimeTranscriptReady?: boolean;
    }
  | { name: 'detail'; meetingId: string; initialTab?: 'summary' | 'transcript' | 'agent' | 'decisions' | 'questions' | 'actions' | 'risks'; sourceSegmentId?: string | null; startTime?: number | null; evidenceText?: string | null };

const failedProcessingStatuses = new Set(['failed', 'transcription_failed', 'summary_failed']);
type RecordingDisplayState = 'hidden' | 'expanded' | 'collapsed';

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function hasSummaryContent(summary: MeetingSummary | null | undefined): boolean {
  return Boolean(summary?.meeting_summary?.trim() || summary?.overview?.trim() || (summary as any)?.summary?.trim());
}

function isMeetingProcessingFailed(meeting: MeetingDetail | null): boolean {
  return Boolean(meeting && failedProcessingStatuses.has(meeting.status));
}

async function waitForRecordingTranscript(meetingId: string): Promise<boolean> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 120000) {
    await wait(3000);
    const [transcript, meeting] = await Promise.all([getMeetingTranscript(meetingId), getMeeting(meetingId)]);
    if (transcript.segments.length > 0 || meeting.transcript_segments.length > 0) return true;
    if (isMeetingProcessingFailed(meeting)) return false;
  }
  return false;
}

async function waitForRecordingSummary(meetingId: string): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < 600000) {
    await wait(3000);
    const [summary, meeting] = await Promise.all([getMeetingSummary(meetingId), getMeeting(meetingId)]);
    if (hasSummaryContent(summary) || hasSummaryContent(meeting.summary) || meeting.status === 'completed') return;
    if (isMeetingProcessingFailed(meeting)) return;
  }
}

async function runRecordingProcessingInBackground(
  meeting: Pick<Meeting, 'id' | 'title' | 'status'>,
  recordingUri: string,
  endedAt: string,
): Promise<void> {
  try {
    await updateMeeting(meeting.id, { end_at: endedAt }).catch(() => undefined);
    const currentMeeting = await getMeeting(meeting.id);
    if (!currentMeeting.audio_files.length) {
      await uploadAudio(meeting.id, recordingUri, endedAt);
    }

    const initialTranscript = await getMeetingTranscript(meeting.id);
    let hasTranscriptSegments = initialTranscript.segments.length > 0 || currentMeeting.transcript_segments.length > 0;
    if (!hasTranscriptSegments) {
      await processMeeting(meeting.id);
      hasTranscriptSegments = await waitForRecordingTranscript(meeting.id);
    }
    if (!hasTranscriptSegments) return;

    const currentSummary = await getMeetingSummary(meeting.id).catch(() => null);
    if (!hasSummaryContent(currentSummary)) {
      await analyzeMeeting(meeting.id);
      await waitForRecordingSummary(meeting.id);
    }
  } catch (error) {
    Alert.alert('录音处理失败', error instanceof Error ? error.message : '请稍后在首页会议列表中重试处理。');
  }
}

function bottomTabForRoute(route: Route): BottomTab | null {
  if (route.name === 'home') return 'home';
  if (['knowledge', 'knowledgeMeetings', 'knowledgeDecisions', 'knowledgeIssueRisks', 'knowledgeSearch', 'knowledgeSearchResults'].includes(route.name)) return 'knowledge';
  if (route.name === 'todo') return 'todo';
  if (['me', 'pushConfig'].includes(route.name)) return 'me';
  return null;
}

export default function App() {
  const [route, setRoute] = useState<Route>({ name: 'home' });
  const [recordingSession, setRecordingSession] = useState<{
    meeting: Pick<Meeting, 'id' | 'title' | 'status' | 'title_source'>;
    started: boolean;
    createdAt: string;
  } | null>(null);
  const [recordingDisplayState, setRecordingDisplayState] = useState<RecordingDisplayState>('hidden');
  const [recordingDiscardSignal, setRecordingDiscardSignal] = useState(0);
  const [creatingRecordingMeeting, setCreatingRecordingMeeting] = useState(false);
  const [recordingAnalysisNoticeVisible, setRecordingAnalysisNoticeVisible] = useState(false);
  const [recordingProcessingMeeting, setRecordingProcessingMeeting] = useState<Meeting | null>(null);
  const [meetingListRefreshKey, setMeetingListRefreshKey] = useState(0);
  const [historyMeetingCount, setHistoryMeetingCount] = useState(0);
  const [taskDetail, setTaskDetail] = useState<{ task: TaskListItem } | null>(null);
  const [taskOverrides, setTaskOverrides] = useState<Record<string, Partial<TaskListItem>>>({});
  const recordingSessionRef = useRef<typeof recordingSession>(null);
  const recordingAnalysisNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const feedbackSubmitRef = useRef<null | (() => void)>(null);
  recordingSessionRef.current = recordingSession;

  useEffect(() => {
    return () => {
      if (recordingAnalysisNoticeTimerRef.current) {
        clearTimeout(recordingAnalysisNoticeTimerRef.current);
      }
    };
  }, []);

  const goHome = useCallback(() => setRoute({ name: 'home' }), []);
  const openDetail = useCallback((meetingId: string) => setRoute({ name: 'detail', meetingId }), []);
  const openKnowledgeSource = useCallback((item: KnowledgeItem) => {
    const initialTab =
      item.content_type === 'transcript'
        ? 'transcript'
        : item.content_type === 'key_decision'
          ? 'decisions'
          : item.content_type === 'unresolved_issue'
            ? 'questions'
            : item.content_type === 'risk'
              ? 'risks'
              : item.content_type === 'action_item'
                ? 'actions'
                : 'summary';
    setRoute({
      name: 'detail',
      meetingId: item.meeting_id,
      initialTab,
      sourceSegmentId: item.source_segment_id,
      startTime: item.start_time,
      evidenceText: item.evidence_text || item.highlight || item.content,
    });
  }, []);
  const openMeeting = useCallback((meetingId: string) => {
    const current = recordingSessionRef.current;
    if (current?.started && current.meeting.id === meetingId) {
      setRecordingDisplayState('expanded');
      return;
    }
    setRoute({ name: 'detail', meetingId });
  }, []);
  const openRecordingSession = useCallback(() => {
    const current = recordingSessionRef.current;
    if (current) {
      setRecordingDisplayState('expanded');
    }
  }, []);
  const headerTitle =
    route.name === 'allMeetings'
      ? `历史会议（${historyMeetingCount}）`
      : route.name === 'newMeeting'
      ? '新建会议'
      : route.name === 'importMeeting'
        ? '导入音频'
      : route.name === 'recording'
        ? '会议录音'
        : route.name === 'processing'
          ? 'AI 处理'
          : route.name === 'audioPlayer'
            ? '会议录音'
            : false
              ? '历史会议'
              : route.name === 'detail'
                ? '会议纪要'
                : route.name === 'editProfile'
                  ? '编辑资料'
                  : route.name === 'settings'
                    ? '设置'
                    : route.name === 'helpFeedback'
                      ? '帮助与反馈'
                      : route.name === 'faq'
                        ? '常见问题'
                        : route.name === 'feedback'
                          ? '意见反馈'
                          : route.name === 'about'
                            ? '关于 MeetMind AI'
                : '';
  const showHeader = [
    'newMeeting',
    'processing',
    'allMeetings',
    'audioPlayer',
    'editProfile',
    'settings',
    'helpFeedback',
    'faq',
    'feedback',
    'about',
    'importMeeting',
  ].includes(route.name);
  const headerRightText = route.name === 'editProfile' ? '保存' : route.name === 'feedback' ? '提交' : undefined;
  const activeTab = taskDetail ? null : bottomTabForRoute(route);
  const miniRecordingVisible =
    recordingSession?.started && recordingDisplayState === 'collapsed' && route.name !== 'processing' && !taskDetail;

  function mergeTaskOverride(task: TaskListItem): TaskListItem {
    return { ...task, ...(taskOverrides[task.id] || {}) };
  }

  function handleOpenTask(task: TaskListItem) {
    setTaskDetail({ task: mergeTaskOverride(task) });
  }

  function handleTaskDetailChange(task: TaskListItem) {
    setTaskOverrides((current) => ({ ...current, [task.id]: { ...(current[task.id] || {}), ...task } }));
    setTaskDetail((current) => (current?.task.id === task.id ? { task } : current));
  }

  async function handleBack() {
    if (['editProfile', 'settings', 'helpFeedback', 'about', 'voiceprintManagement', 'pushConfig'].includes(route.name)) {
      setRoute({ name: 'me' });
      return;
    }

    if (route.name === 'addVoiceprintSample') {
      setRoute({ name: 'voiceprintManagement' });
      return;
    }

    if (['faq', 'feedback'].includes(route.name)) {
      setRoute({ name: 'helpFeedback' });
      return;
    }

    if (route.name === 'recording' && recordingSession) {
      Alert.alert('录音仍在进行', '返回首页不会停止录音。你也可以放弃本次录音。', [
        { text: '继续录制', onPress: () => {
          setRecordingDisplayState('collapsed');
          setRoute({ name: 'home' });
        } },
        { text: '放弃录音', style: 'destructive', onPress: () => {
          setRecordingDiscardSignal((current) => current + 1);
          setRoute({ name: 'home' });
        } },
      ]);
      return;
    }

    if (['knowledgeMeetings', 'knowledgeDecisions', 'knowledgeIssueRisks', 'knowledgeSearch'].includes(route.name)) {
      setRoute({ name: 'knowledge' });
      return;
    }
    if (route.name === 'knowledgeSearchResults') {
      setRoute({ name: 'knowledgeSearch', query: route.query });
      return;
    }

    goHome();
  }

  function handleHeaderRightPress() {
    if (route.name === 'editProfile') {
      Alert.alert('已保存', '资料保存功能将在接入账号系统后同步到服务端。');
    }
    if (route.name === 'feedback') {
      feedbackSubmitRef.current?.();
    }
  }

  function handleTabPress(tab: BottomTab) {
    if (tab === 'recording') {
      if (recordingSessionRef.current) {
        setRecordingDisplayState('expanded');
        return;
      }
      createRecordingMeeting();
      return;
    }

    const applyTab = () => {
      if (tab === 'home') setRoute({ name: 'home' });
      if (tab === 'knowledge') setRoute({ name: 'knowledge' });
      if (tab === 'todo') setRoute({ name: 'todo' });
      if (tab === 'me') setRoute({ name: 'me' });
    };

    if (recordingSessionRef.current?.started) {
      Alert.alert('录音仍在进行', '切换页面不会停止录音。你也可以放弃本次录音。', [
        { text: '继续录制', onPress: () => {
          setRecordingDisplayState('collapsed');
          applyTab();
        } },
        { text: '放弃录音', style: 'destructive', onPress: () => {
          setRecordingDiscardSignal((current) => current + 1);
          applyTab();
        } },
      ]);
      return;
    }

    applyTab();
  }

  async function createRecordingMeeting() {
    if (creatingRecordingMeeting) return;
    try {
      setCreatingRecordingMeeting(true);
      const createdAtDate = new Date();
      const createdAt = createdAtDate.toISOString();
      const meeting = await createMeeting(defaultMeetingTitle('recording', createdAtDate), {
        start_at: createdAt,
        title_source: 'fallback',
      });
      setRecordingSession({ meeting, started: false, createdAt });
      setRecordingDisplayState('expanded');
      setRoute({ name: 'home' });
    } catch (error) {
      Alert.alert('会议创建失败', error instanceof Error ? error.message : '请稍后重试。');
    } finally {
      setCreatingRecordingMeeting(false);
    }
  }

  useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (recordingSessionRef.current) {
        Alert.alert('录音仍在进行', '返回不会停止录音。你也可以放弃本次录音。', [
          { text: '继续录制', onPress: () => setRecordingDisplayState('collapsed') },
          { text: '放弃录音', style: 'destructive', onPress: () => setRecordingDiscardSignal((current) => current + 1) },
        ]);
        return true;
      }

      if (route.name !== 'home') {
        handleBack();
        return true;
      }

      return false;
    });
    return () => subscription.remove();
  }, [route.name]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      {showHeader ? (
        <AppHeader
          title={headerTitle}
          canGoBack={true}
          onBack={handleBack}
          rightText={headerRightText}
          onRightPress={handleHeaderRightPress}
        />
      ) : null}

      {route.name === 'home' ? (
        <MeetingListScreen
          mode="home"
          activeRecordingMeetingId={recordingSession?.started ? recordingSession.meeting.id : null}
          processingRecordingMeeting={recordingProcessingMeeting}
          refreshKey={meetingListRefreshKey}
          miniRecordingVisible={miniRecordingVisible}
          creatingMeeting={creatingRecordingMeeting}
          onCreateMeeting={createRecordingMeeting}
          onImportFile={() => setRoute({ name: 'importMeeting' })}
          onOpenMeeting={openMeeting}
          onShowAll={() => setRoute({ name: 'allMeetings' })}
        />
      ) : null}

      {route.name === 'allMeetings' ? (
        <MeetingListScreen
          mode="all"
          activeRecordingMeetingId={recordingSession?.started ? recordingSession.meeting.id : null}
          processingRecordingMeeting={recordingProcessingMeeting}
          refreshKey={meetingListRefreshKey}
          miniRecordingVisible={miniRecordingVisible}
          creatingMeeting={creatingRecordingMeeting}
          onCreateMeeting={createRecordingMeeting}
          onOpenMeeting={openMeeting}
          onMeetingCountChange={setHistoryMeetingCount}
        />
      ) : null}

      {route.name === 'knowledge' && featureFlags.enableKnowledgeBaseUi ? (
        <KnowledgeBaseScreen
          onOpenDecisions={() => setRoute({ name: 'knowledgeDecisions' })}
          onOpenIssueRisks={() => setRoute({ name: 'knowledgeIssueRisks' })}
          onOpenSearch={(query) => setRoute({ name: 'knowledgeSearch', query })}
          onOpenImportAudio={() => setRoute({ name: 'importMeeting' })}
        />
      ) : null}
      {route.name === 'knowledgeMeetings' ? <KnowledgeMeetingListScreen onBack={() => setRoute({ name: 'knowledge' })} onOpenMeeting={openMeeting} /> : null}
      {route.name === 'knowledgeDecisions' ? <KnowledgeDecisionListScreen onBack={() => setRoute({ name: 'knowledge' })} onOpenSource={openKnowledgeSource} /> : null}
      {route.name === 'knowledgeIssueRisks' ? <KnowledgeIssueRiskScreen onBack={() => setRoute({ name: 'knowledge' })} onOpenSource={openKnowledgeSource} /> : null}
      {route.name === 'knowledgeSearch' ? (
        <KnowledgeSearchScreen
          initialQuery={route.query}
          onBack={() => setRoute({ name: 'knowledge' })}
          onSearch={(query) => setRoute({ name: 'knowledgeSearchResults', query })}
        />
      ) : null}
      {route.name === 'knowledgeSearchResults' ? (
        <KnowledgeSearchResultsScreen
          query={route.query}
          onBack={() => setRoute({ name: 'knowledgeSearch', query: route.query })}
          onCancel={() => setRoute({ name: 'knowledge' })}
          onOpenSource={openKnowledgeSource}
        />
      ) : null}

      {featureFlags.enableAiAssistantUi && route.name === 'ai' ? (
        <AIAssistantScreen
          onOpenRecords={() => setRoute({ name: 'aiRecords' })}
          onOpenRecordDetail={(recordId) => setRoute({ name: 'aiRecordDetail', recordId })}
        />
      ) : null}
      {featureFlags.enableAiAssistantUi && route.name === 'aiRecords' ? (
        <AllAgentRecordsScreen
          onBack={() => setRoute({ name: 'ai' })}
          onOpenRecordDetail={(recordId) => setRoute({ name: 'aiRecordDetail', recordId })}
        />
      ) : null}
      {featureFlags.enableAiAssistantUi && route.name === 'aiRecordDetail' ? (
        <AgentRecordDetailScreen recordId={route.recordId} onBack={() => setRoute({ name: 'aiRecords' })} />
      ) : null}
      {route.name === 'todo' || route.name === 'taskSearch' ? (
        <TodoScreen
          onOpenSearch={() => setRoute({ name: 'taskSearch' })}
          onOpenMeeting={(meetingId, initialTab) => setRoute({ name: 'detail', meetingId, initialTab })}
          onOpenTask={handleOpenTask}
          taskOverrides={taskOverrides}
        />
      ) : null}
      {route.name === 'taskSearch' ? (
        <View style={styles.overlayScreen}>
          <TaskSearchScreen
            onBack={() => setRoute({ name: 'todo' })}
            onOpenMeeting={(meetingId, initialTab) => setRoute({ name: 'detail', meetingId, initialTab })}
            onOpenTask={handleOpenTask}
            taskOverrides={taskOverrides}
          />
        </View>
      ) : null}
      {route.name === 'me' ? (
        <ProfileScreen
          onEditProfile={() => setRoute({ name: 'editProfile' })}
          onVoiceprintManagement={() => setRoute({ name: 'voiceprintManagement' })}
          onPushConfig={() => setRoute({ name: 'pushConfig' })}
          onHelpFeedback={() => setRoute({ name: 'helpFeedback' })}
          onAbout={() => setRoute({ name: 'about' })}
          onSettings={() => setRoute({ name: 'settings' })}
        />
      ) : null}
      {route.name === 'voiceprintManagement' ? (
        <VoiceprintManagementScreen
          onBack={() => setRoute({ name: 'me' })}
          onAddVoiceprint={() => setRoute({ name: 'addVoiceprintSample' })}
        />
      ) : null}
      {route.name === 'addVoiceprintSample' ? <AddVoiceprintSampleScreen onBack={() => setRoute({ name: 'voiceprintManagement' })} /> : null}
      {route.name === 'pushConfig' ? <PushConfigScreen onBack={() => setRoute({ name: 'me' })} /> : null}
      {route.name === 'editProfile' ? <EditProfileScreen /> : null}
      {route.name === 'settings' ? <SettingsScreen /> : null}
      {route.name === 'helpFeedback' ? (
        <HelpFeedbackScreen onFaq={() => setRoute({ name: 'faq' })} onFeedback={() => setRoute({ name: 'feedback' })} />
      ) : null}
      {route.name === 'faq' ? <FaqScreen /> : null}
      {route.name === 'feedback' ? (
        <FeedbackScreen registerSubmit={(handler) => { feedbackSubmitRef.current = handler; }} />
      ) : null}
      {route.name === 'about' ? <AboutScreen /> : null}

      {route.name === 'newMeeting' ? (
        <NewMeetingScreen
          onCreated={(meeting) => {
            setRecordingSession({ meeting, started: false, createdAt: new Date().toISOString() });
            setRecordingDisplayState('expanded');
            setRoute({ name: 'recording', meeting });
          }}
          onCancel={goHome}
        />
      ) : null}

      {route.name === 'importMeeting' ? (
        <ImportMeetingScreen
          onImported={({ meeting, fileUri, endedAt }) => {
            setRecordingSession(null);
            setRecordingDisplayState('hidden');
            setRoute({
              name: 'processing',
              meeting,
              recordingUri: fileUri,
              endedAt,
              realtimeTranscriptReady: false,
            });
          }}
          onCancel={goHome}
        />
      ) : null}

      {recordingSession ? (
        <RecordingScreen
          meeting={recordingSession.meeting}
          createdAt={recordingSession.createdAt}
          displayState={recordingDisplayState}
          discardSignal={recordingDiscardSignal}
          onCollapse={() => setRecordingDisplayState('collapsed')}
          onExpand={openRecordingSession}
          onStarted={() =>
            setRecordingSession((current) => (current ? { ...current, started: true } : current))
          }
          onDiscard={() => {
            const meetingId = recordingSession.meeting.id;
            setRecordingSession(null);
            setRecordingDisplayState('hidden');
            deleteMeeting(meetingId).catch(() => undefined);
            setRoute({ name: 'home' });
          }}
          onProcessing={(recordingUri, endedAt) => {
            const meeting = recordingSession.meeting;
            const processingMeeting: Meeting = {
              id: meeting.id,
              title: meeting.title,
              title_source: meeting.title_source,
              status: 'processing',
              start_at: recordingSession.createdAt,
              end_at: endedAt,
              location: null,
              created_at: recordingSession.createdAt,
              updated_at: endedAt,
            };
            setRecordingProcessingMeeting(processingMeeting);
            setMeetingListRefreshKey((current) => current + 1);
            setRecordingAnalysisNoticeVisible(true);
            runRecordingProcessingInBackground(meeting, recordingUri, endedAt).finally(() => {
              setRecordingProcessingMeeting(null);
              setMeetingListRefreshKey((current) => current + 1);
            });
            if (recordingAnalysisNoticeTimerRef.current) {
              clearTimeout(recordingAnalysisNoticeTimerRef.current);
            }
            recordingAnalysisNoticeTimerRef.current = setTimeout(() => {
              setRecordingSession(null);
              setRecordingAnalysisNoticeVisible(false);
              setRoute({ name: 'home' });
              recordingAnalysisNoticeTimerRef.current = null;
            }, 500);
            setRecordingDisplayState('hidden');
          }}
        />
      ) : null}

      <Modal transparent visible={recordingAnalysisNoticeVisible} animationType="fade">
        <View style={styles.recordingNoticeBackdrop}>
          <View style={styles.recordingNoticeCard}>
            <ActivityIndicator color="#ffffff" size="small" />
            <Text style={styles.recordingNoticeText}>已进入AI结构化分析</Text>
          </View>
        </View>
      </Modal>

      {route.name === 'processing' ? (
        <AIProcessingScreen
          meeting={route.meeting}
          recordingUri={route.recordingUri}
          endedAt={route.endedAt}
          realtimeTranscriptReady={route.realtimeTranscriptReady}
          onBackHome={goHome}
          onOpenDetail={openDetail}
        />
      ) : null}

      {route.name === 'detail' ? (
        <MeetingDetailScreen
          meetingId={route.meetingId}
          initialTab={route.initialTab}
          sourceSegmentId={route.sourceSegmentId}
          startTime={route.startTime}
          evidenceText={route.evidenceText}
          onBack={handleBack}
          onRecord={(meeting) => setRoute({ name: 'recording', meeting })}
          onOpenAudioPlayer={(meetingId) => setRoute({ name: 'audioPlayer', meetingId })}
          onOpenKnowledgeBase={() => setRoute({ name: 'knowledge' })}
        />
      ) : null}

      {route.name === 'audioPlayer' ? <AudioPlayerScreen meetingId={route.meetingId} /> : null}

      {taskDetail ? (
        <View style={styles.taskDetailOverlay}>
          <TaskDetailScreen
            initialTask={taskDetail.task}
            onBack={() => setTaskDetail(null)}
            onTaskChange={handleTaskDetailChange}
            onOpenMeeting={({ meetingId, initialTab, sourceSegmentId, evidenceText }) => {
              setTaskDetail(null);
              setRoute({ name: 'detail', meetingId, initialTab, sourceSegmentId, evidenceText });
            }}
          />
        </View>
      ) : null}

      {activeTab ? <BottomNav active={activeTab} onTabPress={handleTabPress} /> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#f6f7fb',
  },
  overlayScreen: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#f5f7fa',
    zIndex: 60,
  },
  taskDetailOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#f5f7fa',
    zIndex: 80,
  },
  recordingNoticeBackdrop: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.42)',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 28,
  },
  recordingNoticeCard: {
    alignItems: 'center',
    backgroundColor: '#111827',
    borderRadius: 16,
    elevation: 8,
    flexDirection: 'row',
    gap: 10,
    minHeight: 56,
    paddingHorizontal: 18,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.22,
    shadowRadius: 18,
  },
  recordingNoticeText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '900',
  },
});
