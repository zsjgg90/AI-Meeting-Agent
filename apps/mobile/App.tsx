import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Animated, PanResponder, SafeAreaView, StyleSheet, Text, View } from 'react-native';

import { deleteMeeting, KnowledgeItem, Meeting } from './src/api';
import { AppHeader } from './src/components/AppHeader';
import { BottomNav, BottomTab } from './src/components/BottomNav';
import { featureFlags } from './src/config';
import { AIAssistantScreen } from './src/screens/AIAssistantScreen';
import { AIProcessingScreen } from './src/screens/AIProcessingScreen';
import { AboutScreen } from './src/screens/AboutScreen';
import { AudioPlayerScreen } from './src/screens/AudioPlayerScreen';
import { EditProfileScreen } from './src/screens/EditProfileScreen';
import { FaqScreen } from './src/screens/FaqScreen';
import { FeedbackScreen } from './src/screens/FeedbackScreen';
import { HelpFeedbackScreen } from './src/screens/HelpFeedbackScreen';
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
import { RecordingScreen } from './src/screens/RecordingScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { TodoScreen } from './src/screens/TodoScreen';

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
  | { name: 'todo' }
  | { name: 'me' }
  | { name: 'editProfile' }
  | { name: 'settings' }
  | { name: 'helpFeedback' }
  | { name: 'faq' }
  | { name: 'feedback' }
  | { name: 'about' }
  | { name: 'newMeeting' }
  | { name: 'recording'; meeting: Pick<Meeting, 'id' | 'title' | 'status'> }
  | { name: 'audioPlayer'; meetingId: string }
  | {
      name: 'processing';
      meeting: Pick<Meeting, 'id' | 'title' | 'status'>;
      recordingUri: string;
      endedAt: string;
      realtimeTranscriptReady?: boolean;
    }
  | { name: 'detail'; meetingId: string; initialTab?: 'summary' | 'transcript' | 'decisions' | 'questions' | 'actions' | 'risks'; sourceSegmentId?: string | null; startTime?: number | null; evidenceText?: string | null };

const floatingWaveHeights = [12, 22, 32, 22, 12];

function FloatingRecordingIcon() {
  const waves = useRef(floatingWaveHeights.map(() => new Animated.Value(0))).current;

  useEffect(() => {
    const animations = waves.map((wave, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 90),
          Animated.timing(wave, {
            toValue: 1,
            duration: 360,
            useNativeDriver: false,
          }),
          Animated.timing(wave, {
            toValue: 0,
            duration: 360,
            useNativeDriver: false,
          }),
        ]),
      ),
    );
    animations.forEach((animation) => animation.start());
    return () => animations.forEach((animation) => animation.stop());
  }, [waves]);

  return (
    <View style={styles.floatingIconWrap}>
      <View style={styles.floatingWave}>
        {waves.map((wave, index) => {
          const baseHeight = floatingWaveHeights[index];
          const height = wave.interpolate({
            inputRange: [0, 1],
            outputRange: [baseHeight * 0.62, baseHeight],
          });
          return <Animated.View key={index} style={[styles.floatingWaveBar, { height }]} />;
        })}
      </View>
    </View>
  );
}

function bottomTabForRoute(route: Route): BottomTab | null {
  if (route.name === 'home') return 'home';
  if (['knowledge', 'knowledgeMeetings', 'knowledgeDecisions', 'knowledgeIssueRisks', 'knowledgeSearch', 'knowledgeSearchResults'].includes(route.name)) return 'knowledge';
  if (featureFlags.enableAiAssistantUi && route.name === 'ai') return 'ai';
  if (route.name === 'todo') return 'todo';
  if (route.name === 'me') return 'me';
  return null;
}

export default function App() {
  const [route, setRoute] = useState<Route>({ name: 'home' });
  const [recordingSession, setRecordingSession] = useState<{
    meeting: Pick<Meeting, 'id' | 'title' | 'status'>;
    started: boolean;
  } | null>(null);
  const recordingSessionRef = useRef<typeof recordingSession>(null);
  const feedbackSubmitRef = useRef<null | (() => void)>(null);
  const floatingPan = useRef(new Animated.ValueXY({ x: 0, y: 0 })).current;
  const floatingOffset = useRef({ x: 0, y: 0 });
  const floatingMoved = useRef(false);
  recordingSessionRef.current = recordingSession;

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
      setRoute({ name: 'recording', meeting: current.meeting });
      return;
    }
    setRoute({ name: 'detail', meetingId });
  }, []);
  const openRecordingSession = useCallback(() => {
    const current = recordingSessionRef.current;
    if (current) {
      setRoute({ name: 'recording', meeting: current.meeting });
    }
  }, []);
  const floatingPanResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 4 || Math.abs(gesture.dy) > 4,
      onPanResponderGrant: () => {
        floatingMoved.current = false;
        floatingPan.setOffset(floatingOffset.current);
        floatingPan.setValue({ x: 0, y: 0 });
      },
      onPanResponderMove: (event, gesture) => {
        if (Math.abs(gesture.dx) > 4 || Math.abs(gesture.dy) > 4) {
          floatingMoved.current = true;
        }
        Animated.event([null, { dx: floatingPan.x, dy: floatingPan.y }], { useNativeDriver: false })(event, gesture);
      },
      onPanResponderRelease: (_, gesture) => {
        floatingPan.flattenOffset();
        floatingOffset.current = {
          x: floatingOffset.current.x + gesture.dx,
          y: floatingOffset.current.y + gesture.dy,
        };
        if (!floatingMoved.current) {
          openRecordingSession();
        }
      },
    }),
  ).current;

  const headerTitle =
    route.name === 'newMeeting'
      ? '新建会议'
      : route.name === 'recording'
        ? '会议录音'
        : route.name === 'processing'
          ? 'AI 处理'
          : route.name === 'audioPlayer'
            ? '会议录音'
            : route.name === 'allMeetings'
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
    'recording',
    'processing',
    'allMeetings',
    'detail',
    'audioPlayer',
    'editProfile',
    'settings',
    'helpFeedback',
    'faq',
    'feedback',
    'about',
  ].includes(route.name);
  const headerRightText = route.name === 'editProfile' ? '保存' : route.name === 'feedback' ? '提交' : undefined;
  const activeTab = bottomTabForRoute(route);
  const showFloatingRecording =
    recordingSession?.started && route.name !== 'recording' && route.name !== 'processing';

  async function handleBack() {
    if (['editProfile', 'settings', 'helpFeedback', 'about'].includes(route.name)) {
      setRoute({ name: 'me' });
      return;
    }

    if (['faq', 'feedback'].includes(route.name)) {
      setRoute({ name: 'helpFeedback' });
      return;
    }

    if (route.name === 'recording' && recordingSession) {
      if (recordingSession.started) {
        setRoute({ name: 'home' });
        return;
      }

      const meetingId = recordingSession.meeting.id;
      setRecordingSession(null);
      try {
        await deleteMeeting(meetingId);
      } catch {
        // The draft meeting should not block navigation if cleanup fails.
      }
      setRoute({ name: 'home' });
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
    if (tab === 'home') setRoute({ name: 'home' });
    if (tab === 'knowledge') setRoute({ name: 'knowledge' });
    if (tab === 'ai' && featureFlags.enableAiAssistantUi) setRoute({ name: 'ai' });
    if (tab === 'todo') setRoute({ name: 'todo' });
    if (tab === 'me') setRoute({ name: 'me' });
  }

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
          onCreateMeeting={() => setRoute({ name: 'newMeeting' })}
          onOpenMeeting={openMeeting}
          onShowAll={() => setRoute({ name: 'allMeetings' })}
        />
      ) : null}

      {route.name === 'allMeetings' ? (
        <MeetingListScreen
          mode="all"
          activeRecordingMeetingId={recordingSession?.started ? recordingSession.meeting.id : null}
          onCreateMeeting={() => setRoute({ name: 'newMeeting' })}
          onOpenMeeting={openMeeting}
        />
      ) : null}

      {route.name === 'knowledge' && featureFlags.enableKnowledgeBaseUi ? (
        <KnowledgeBaseScreen
          onOpenMeetings={() => setRoute({ name: 'knowledgeMeetings' })}
          onOpenDecisions={() => setRoute({ name: 'knowledgeDecisions' })}
          onOpenIssueRisks={() => setRoute({ name: 'knowledgeIssueRisks' })}
          onOpenSearch={(query) => setRoute({ name: 'knowledgeSearch', query })}
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

      {featureFlags.enableAiAssistantUi && route.name === 'ai' ? <AIAssistantScreen /> : null}
      {route.name === 'todo' ? <TodoScreen /> : null}
      {route.name === 'me' ? (
        <ProfileScreen
          onEditProfile={() => setRoute({ name: 'editProfile' })}
          onHelpFeedback={() => setRoute({ name: 'helpFeedback' })}
          onAbout={() => setRoute({ name: 'about' })}
          onSettings={() => setRoute({ name: 'settings' })}
        />
      ) : null}
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
            setRecordingSession({ meeting, started: false });
            setRoute({ name: 'recording', meeting });
          }}
          onCancel={goHome}
        />
      ) : null}

      {recordingSession ? (
        <RecordingScreen
          meeting={recordingSession.meeting}
          minimized={route.name !== 'recording'}
          onStarted={() =>
            setRecordingSession((current) => (current ? { ...current, started: true } : current))
          }
          onProcessing={(recordingUri, endedAt, realtimeTranscriptReady) => {
            const meeting = recordingSession.meeting;
            setRecordingSession(null);
            setRoute({
              name: 'processing',
              meeting,
              recordingUri,
              endedAt,
              realtimeTranscriptReady,
            });
          }}
        />
      ) : null}

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
          onRecord={(meeting) => setRoute({ name: 'recording', meeting })}
          onOpenAudioPlayer={(meetingId) => setRoute({ name: 'audioPlayer', meetingId })}
        />
      ) : null}

      {route.name === 'audioPlayer' ? <AudioPlayerScreen meetingId={route.meetingId} /> : null}

      {showFloatingRecording ? (
        <Animated.View
          {...floatingPanResponder.panHandlers}
          style={[styles.floatingRecording, { transform: floatingPan.getTranslateTransform() }]}
        >
          <View style={styles.floatingDot} />
          <FloatingRecordingIcon />
        </Animated.View>
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
  floatingRecording: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 33,
    bottom: 86,
    elevation: 12,
    height: 66,
    justifyContent: 'center',
    position: 'absolute',
    right: 18,
    shadowColor: '#6657ff',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 18,
    width: 66,
    zIndex: 30,
  },
  floatingDot: {
    backgroundColor: '#ef4444',
    borderColor: '#ffffff',
    borderRadius: 6,
    borderWidth: 2,
    height: 12,
    position: 'absolute',
    right: 9,
    top: 9,
    width: 12,
  },
  floatingIconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  floatingWave: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 3,
  },
  floatingWaveBar: {
    backgroundColor: 'rgba(255,255,255,0.48)',
    borderRadius: 999,
    width: 3,
  },
});
