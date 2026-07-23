import { Audio } from 'expo-av';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  getMeeting,
  getMeetingSummary,
  Meeting,
  meetingAudioUrl,
  meetingExportUrl,
  MeetingDetail,
  MeetingSummary,
  updateSpeakerMapping,
} from '../api';
import { LucideIcon } from '../components/LucideIcon';
import { NumberedList } from '../components/NumberedList';
import { normalizeNumberedListItems } from '../utils/numberedList';

type Props = {
  meetingId: string;
  onRecord: (meeting: Meeting) => void;
  onOpenAudioPlayer: (meetingId: string) => void;
  initialTab?: DetailTab;
  sourceSegmentId?: string | null;
  startTime?: number | null;
  evidenceText?: string | null;
};

type DetailTab = 'summary' | 'transcript' | 'decisions' | 'questions' | 'actions' | 'risks';
type ExportFormat = 'md' | 'pdf' | 'docx' | 'txt';

const tabs: Array<{ key: DetailTab; label: string }> = [
  { key: 'summary', label: '纪要' },
  { key: 'transcript', label: '全文记录' },
  { key: 'decisions', label: '核心结论' },
  { key: 'questions', label: '遗留问题' },
  { key: 'actions', label: '待办与后续安排' },
  { key: 'risks', label: '风险与关注点' },
];

const meetingStatusText: Record<string, string> = {
  created: '待录音',
  uploaded: '已上传',
  audio_uploaded: '已上传',
  processing: '分析中',
  transcribing: '转写中',
  transcribed: '已转写',
  summarizing: '生成纪要中',
  completed: '已完成',
  failed: '失败',
  transcription_failed: '转写失败',
  summary_failed: '纪要失败',
};

function statusText(status: string): string {
  return meetingStatusText[status] || status;
}

function resultSourceText(summary: MeetingSummary | null | undefined): string {
  const source = summary?.metadata?.result_source;
  if (source === 'fixture') return 'fixture 人工结果';
  if (source === 'legacy_qwen_rag') return '旧 Qwen3 + RAG';
  if (source === 'semantic_pipeline') return '语义 shadow';
  return '来源未知';
}

function textValue(item: unknown, keys: string[]): string {
  if (typeof item === 'string') return item.trim();
  if (!item || typeof item !== 'object') return '';
  const record = item as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return Object.entries(record)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join('、') : String(value)}`)
    .join('；');
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '未设置';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未设置';
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day} ${hours}:${minutes}`;
}

function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const rest = safe % 60;
  if (hours) return `${hours}小时${minutes}分${rest}秒`;
  if (minutes) return `${minutes}分${rest}秒`;
  return `${rest}秒`;
}

function formatSegmentTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function speakerSortValue(label: string): number {
  const match = label.match(/\d+/);
  return match ? Number(match[0]) : 999;
}

function meetingDuration(meeting: MeetingDetail): string {
  if (meeting.created_at && meeting.end_at) {
    const start = new Date(meeting.created_at).getTime();
    const end = new Date(meeting.end_at).getTime();
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
      return formatClock((end - start) / 1000);
    }
  }
  const lastSegment = meeting.transcript_segments[meeting.transcript_segments.length - 1];
  if (lastSegment?.end_time) return formatClock(lastSegment.end_time);
  return '未计算';
}

function cleanSummaryText(value: string): string {
  return value
    .replace(/\[[^\]]+\]\s*[^:：]+[:：]\s*/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function MeetingDetailScreen({ meetingId, initialTab = 'summary', sourceSegmentId, startTime, evidenceText, onRecord, onOpenAudioPlayer }: Props) {
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [summaryOverride, setSummaryOverride] = useState<MeetingSummary | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>(initialTab);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [speakerNameDrafts, setSpeakerNameDrafts] = useState<Record<string, string>>({});
  const [speakerNoteDrafts, setSpeakerNoteDrafts] = useState<Record<string, string>>({});
  const [savingSpeaker, setSavingSpeaker] = useState<string | null>(null);
  const [editingSpeakerLabel, setEditingSpeakerLabel] = useState<string | null>(null);
  const [sound, setSound] = useState<Audio.Sound | null>(null);
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null);
  const [playingSegmentId, setPlayingSegmentId] = useState<string | null>(null);
  const [transcriptSearch, setTranscriptSearch] = useState(evidenceText || '');

  const loadMeeting = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const nextMeeting = await getMeeting(meetingId);
      setMeeting(nextMeeting);
      try {
        setSummaryOverride(await getMeetingSummary(meetingId));
      } catch {
        setSummaryOverride(nextMeeting.summary);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '会议详情加载失败。');
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    loadMeeting();
  }, [loadMeeting]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab, meetingId]);

  useEffect(() => {
    return () => {
      sound?.unloadAsync().catch(() => undefined);
    };
  }, [sound]);

  useEffect(() => {
    if (!meeting) return;
    const names: Record<string, string> = {};
    const notes: Record<string, string> = {};
    for (const segment of meeting.transcript_segments) {
      if (segment.speaker_label) {
        names[segment.speaker_label] = '';
        notes[segment.speaker_label] = '';
      }
    }
    for (const mapping of meeting.speaker_mappings) {
      names[mapping.speaker_label] = mapping.display_name;
      notes[mapping.speaker_label] = mapping.note || '';
    }
    setSpeakerNameDrafts((current) => ({ ...names, ...current }));
    setSpeakerNoteDrafts((current) => ({ ...notes, ...current }));
  }, [meeting]);

  useEffect(() => {
    if (!meeting || activeTab !== 'transcript') return;
    if (evidenceText?.trim()) {
      setTranscriptSearch(evidenceText.trim());
      return;
    }
    if (sourceSegmentId) {
      const segment = meeting.transcript_segments.find((item) => item.id === sourceSegmentId);
      if (segment?.text) setTranscriptSearch(segment.text);
      return;
    }
    if (typeof startTime === 'number') {
      const segment = meeting.transcript_segments.find((item) => item.start_time <= startTime && item.end_time >= startTime);
      if (segment?.text) setTranscriptSearch(segment.text);
    }
  }, [activeTab, evidenceText, meeting, sourceSegmentId, startTime]);

  useEffect(() => {
    if (!meeting || !['processing', 'transcribing', 'transcribed', 'summarizing'].includes(meeting.status)) {
      return undefined;
    }
    const timer = setInterval(loadMeeting, 3000);
    return () => clearInterval(timer);
  }, [loadMeeting, meeting]);

  const summary = summaryOverride || meeting?.summary;
  const fallbackOutput = meeting?.output;
  const speakerDisplayNames = useMemo(
    () =>
      meeting?.speaker_mappings.reduce<Record<string, string>>((acc, mapping) => {
        acc[mapping.speaker_label] = mapping.display_name;
        return acc;
      }, {}) || {},
    [meeting],
  );
  const speakerLabels = useMemo(
    () =>
      Array.from(
        new Set(meeting?.transcript_segments.map((segment) => segment.speaker_label).filter(Boolean) as string[]),
      ).sort((left, right) => speakerSortValue(left) - speakerSortValue(right)),
    [meeting],
  );
  const participants = useMemo(() => {
    const names = speakerLabels.map((label) => displaySpeaker(label));
    return names.length ? names.join('、') : '待 AI 识别';
  }, [speakerDisplayNames, speakerLabels]);
  const actionItems = summary?.action_items?.length
    ? summary.action_items
    : meeting?.action_items?.length
      ? meeting.action_items
      : fallbackOutput?.action_items || [];
  const decisions = summary?.key_conclusions?.length
    ? summary.key_conclusions
    : summary?.decisions?.length
      ? summary.decisions
      : fallbackOutput?.decisions || [];
  const filteredTranscriptSegments = useMemo(() => {
    const segments = meeting?.transcript_segments || [];
    const keyword = transcriptSearch.trim().toLowerCase();
    if (!keyword) return segments;
    return segments.filter((segment) => {
      const speaker = displaySpeaker(segment.speaker_label).toLowerCase();
      return segment.text.toLowerCase().includes(keyword) || speaker.includes(keyword);
    });
  }, [meeting?.transcript_segments, speakerDisplayNames, transcriptSearch]);
  const speakerDurations = useMemo(() => {
    const totals: Record<string, { seconds: number }> = {};
    for (const segment of meeting?.transcript_segments || []) {
      const label = displaySpeaker(segment.speaker_label);
      if (!totals[label]) totals[label] = { seconds: 0 };
      totals[label].seconds += Math.max(0, segment.end_time - segment.start_time);
    }
    return Object.entries(totals).sort(([left], [right]) => speakerSortValue(left) - speakerSortValue(right));
  }, [meeting?.transcript_segments, speakerDisplayNames]);

  function displaySpeaker(speakerLabel: string | null): string {
    if (!speakerLabel) return '发言人';
    if (speakerDisplayNames[speakerLabel]) return speakerDisplayNames[speakerLabel];
    const index = speakerLabels.indexOf(speakerLabel);
    return index >= 0 ? `发言人${index + 1}` : '发言人';
  }

  function replaceSpeakerLabels(value: string | null | undefined): string {
    if (!value) return '';
    let result = value;
    for (const speakerLabel of speakerLabels) {
      const displayName = displaySpeaker(speakerLabel);
      result = result.replace(new RegExp(escapeRegExp(speakerLabel), 'g'), displayName);
      result = result.replace(new RegExp(escapeRegExp(speakerLabel.replace('_', '')), 'g'), displayName);
    }
    return result;
  }

  function openSpeakerEditor(speakerLabel: string) {
    setSpeakerNameDrafts((current) => ({
      ...current,
      [speakerLabel]: speakerDisplayNames[speakerLabel] || displaySpeaker(speakerLabel),
    }));
    setEditingSpeakerLabel(speakerLabel);
  }

  async function toggleAudioPlayback(startSeconds?: number, stopSeconds?: number, segmentId?: string) {
    if (!meeting) return;
    const audioFile = meeting.audio_files[0];
    if (!audioFile) {
      onRecord(meeting);
      return;
    }

    try {
      setError(null);
      if (sound && playingAudioId === audioFile.id) {
        const status = await sound.getStatusAsync();
        if (status.isLoaded && status.isPlaying) {
          await sound.pauseAsync();
          setPlayingAudioId(null);
          setPlayingSegmentId(null);
          return;
        }
        if (typeof startSeconds === 'number') await sound.setPositionAsync(Math.max(0, startSeconds * 1000));
        await sound.playAsync();
        setPlayingAudioId(audioFile.id);
        setPlayingSegmentId(segmentId || null);
        return;
      }

      if (sound) await sound.unloadAsync();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
        shouldDuckAndroid: true,
        playThroughEarpieceAndroid: false,
      });

      const nextSound = new Audio.Sound();
      await nextSound.loadAsync({ uri: meetingAudioUrl(meeting.id, audioFile.id) }, { shouldPlay: true });
      if (typeof startSeconds === 'number') await nextSound.setPositionAsync(Math.max(0, startSeconds * 1000));
      nextSound.setOnPlaybackStatusUpdate((status) => {
        if (!status.isLoaded) return;
        if (
          typeof stopSeconds === 'number' &&
          status.isPlaying &&
          status.positionMillis >= Math.max(0, stopSeconds * 1000)
        ) {
          nextSound.pauseAsync().catch(() => undefined);
          setPlayingAudioId(null);
          setPlayingSegmentId(null);
          return;
        }
        if (status.didJustFinish) {
          setPlayingAudioId(null);
          setPlayingSegmentId(null);
        }
      });
      setSound(nextSound);
      setPlayingAudioId(audioFile.id);
      setPlayingSegmentId(segmentId || null);
    } catch (nextError) {
      setPlayingAudioId(null);
      setPlayingSegmentId(null);
      setError(nextError instanceof Error ? nextError.message : '录音播放失败，请确认服务端音频文件仍存在。');
    }
  }

  async function saveSpeaker(speakerLabel: string) {
    const displayName = (speakerNameDrafts[speakerLabel] || '').trim();
    const note = (speakerNoteDrafts[speakerLabel] || '').trim();
    if (!displayName) {
      setError('发言人姓名不能为空。');
      return;
    }
    try {
      setSavingSpeaker(speakerLabel);
      setError(null);
      await updateSpeakerMapping(meetingId, speakerLabel, displayName, note);
      setEditingSpeakerLabel(null);
      await loadMeeting();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '保存发言人信息失败。');
    } finally {
      setSavingSpeaker(null);
    }
  }

  async function openExport(kind: 'transcript' | 'summary', format: ExportFormat) {
    try {
      setError(null);
      await Linking.openURL(meetingExportUrl(meetingId, kind, format));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '打开导出文件失败。');
    }
  }

  function renderExportButtons(kind: 'transcript' | 'summary') {
    const formats: ExportFormat[] = ['md', 'pdf', 'docx', 'txt'];
    return (
      <View style={styles.exportRow}>
        {formats.map((format) => (
          <Pressable key={`${kind}-${format}`} onPress={() => openExport(kind, format)} style={styles.exportButton}>
            <Text style={styles.exportText}>{format.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>
    );
  }

  function renderListSection(title: string, rows: string[]) {
    const items = normalizeNumberedListItems(rows).map(replaceSpeakerLabels);

    return (
      <View style={styles.contentCard}>
        <Text style={styles.cardTitle}>{title}</Text>
        <NumberedList items={items} />
      </View>
    );
  }

  function renderSpeakerEditor() {
    if (!speakerLabels.length) return null;
    return (
      <View style={styles.contentCard}>
        <Text style={styles.cardTitle}>发言人姓名与备注</Text>
        {speakerLabels.map((speakerLabel) => (
          <View key={speakerLabel} style={styles.speakerEditor}>
            <Text style={styles.speakerLabel}>{displaySpeaker(speakerLabel)}</Text>
            <TextInput
              value={speakerNameDrafts[speakerLabel] || ''}
              onChangeText={(value) => setSpeakerNameDrafts((current) => ({ ...current, [speakerLabel]: value }))}
              placeholder="输入真实姓名"
              placeholderTextColor="#aeb6c5"
              style={styles.speakerInput}
            />
            <TextInput
              value={speakerNoteDrafts[speakerLabel] || ''}
              onChangeText={(value) => setSpeakerNoteDrafts((current) => ({ ...current, [speakerLabel]: value }))}
              placeholder="备注，如部门、角色、项目职责"
              placeholderTextColor="#aeb6c5"
              multiline
              style={[styles.speakerInput, styles.speakerNoteInput]}
            />
            <Pressable onPress={() => saveSpeaker(speakerLabel)} style={styles.saveSpeakerButton}>
              <Text style={styles.saveSpeakerText}>{savingSpeaker === speakerLabel ? '保存中' : '保存'}</Text>
            </Pressable>
          </View>
        ))}
      </View>
    );
  }

  function renderSummary() {
    const agendaRows = (summary?.meeting_agenda?.length ? summary.meeting_agenda : summary?.agenda || []).map((item) =>
      textValue(item, ['item', 'summary', 'status']),
    );
    const decisionRows = decisions.map((item) => textValue(item, ['conclusion', 'decision', 'title', 'summary', 'reason']));
    const issueRows = (summary?.unresolved_issues?.length ? summary.unresolved_issues : summary?.open_questions || []).map((item) =>
      textValue(item, ['issue', 'question', 'reason', 'blocker', 'source_text', 'source']),
    );
    const actionRows = actionItems.map((item) =>
      textValue(item as Record<string, unknown>, ['task', 'owner_name', 'owner', 'deadline', 'due_date', 'source_text', 'source']),
    );
    const riskRows = (summary?.risks_and_focus?.length ? summary.risks_and_focus : summary?.risks || []).map((item) =>
      textValue(item, ['risk', 'impact', 'focus_area', 'mitigation', 'source_text']),
    );
    const transcriptPreview = (meeting?.transcript_segments || [])
      .slice(0, 5)
      .map((segment) => segment.text)
      .join(' ');
    const overview =
      replaceSpeakerLabels(cleanSummaryText(summary?.meeting_summary || summary?.overview || fallbackOutput?.summary || transcriptPreview)) ||
      '暂无会议纪要。';

    return (
      <>
        <View style={styles.summaryHero}>
          <View style={styles.summaryHeroHeader}>
            <View>
              <Text style={styles.summaryHeroTitle}>会议总结</Text>
            </View>
            <View style={styles.statusPill}>
              <Text style={styles.statusPillText}>{statusText(meeting?.status || '')}</Text>
            </View>
          </View>
          <View style={styles.sourcePill}>
            <Text style={styles.sourcePillText}>result_source={summary?.metadata?.result_source || 'unknown'}</Text>
            <Text style={styles.sourceHintText}>{resultSourceText(summary)}</Text>
          </View>
          <Text style={styles.summaryLead}>{overview}</Text>
          <View style={styles.metricGrid}>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{speakerLabels.length}</Text>
              <Text style={styles.metricLabel}>参会人</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{decisions.length}</Text>
              <Text style={styles.metricLabel}>决议</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricValue}>{actionItems.length}</Text>
              <Text style={styles.metricLabel}>待办</Text>
            </View>
          </View>
          <Text style={styles.exportTitle}>导出结构化会议纪要</Text>
          {renderExportButtons('summary')}
        </View>
        {renderListSection('会议议程', agendaRows)}
        {renderListSection('核心结论', decisionRows)}
        {renderListSection('遗留问题', issueRows)}
        {renderListSection('待办与后续安排', actionRows)}
        {renderListSection('风险与关注点', riskRows)}
      </>
    );
  }

  function renderTranscript() {
    return (
      <>
        <View style={styles.contentCard}>
          <Text style={styles.cardTitle}>导出原始分人转写文稿</Text>
          {renderExportButtons('transcript')}
        </View>
        {speakerDurations.length ? (
          <View style={styles.durationStrip}>
            {speakerDurations.map(([speaker, meta]) => {
              return (
                <View key={speaker} style={styles.durationChip}>
                  <Text style={styles.durationName}>{speaker}</Text>
                  <Text style={styles.durationValue}>{formatClock(meta.seconds)}</Text>
                </View>
              );
            })}
          </View>
        ) : null}

        <View style={styles.contentCard}>
          <Text style={styles.cardTitle}>全文记录</Text>
          {filteredTranscriptSegments.length ? (
            filteredTranscriptSegments.map((segment) => {
              const speaker = displaySpeaker(segment.speaker_label);
              return (
                <View key={segment.id} style={styles.segment}>
                  <Text style={styles.timeText}>{formatSegmentTime(segment.start_time)}</Text>
                  <View style={styles.segmentBody}>
                    <View style={styles.transcriptSpeakerLine}>
                      <Text style={styles.speakerName}>{speaker}</Text>
                      <Text style={styles.segmentSeconds}>{formatClock(segment.end_time - segment.start_time)}</Text>
                      <Pressable
                        onPress={() => toggleAudioPlayback(segment.start_time, segment.end_time, segment.id)}
                        style={styles.segmentPlayButton}
                      >
                        <Text style={styles.segmentPlayText}>{playingSegmentId === segment.id ? 'Ⅱ' : '▶'}</Text>
                      </Pressable>
                    </View>
                    <Text style={styles.paragraph}>{replaceSpeakerLabels(segment.text)}</Text>
                  </View>
                </View>
              );
            })
          ) : fallbackOutput?.raw_transcript ? (
            <Text style={styles.paragraph}>{replaceSpeakerLabels(fallbackOutput.raw_transcript)}</Text>
          ) : (
            <Text style={styles.empty}>暂无转写文本。</Text>
          )}
        </View>
      </>
    );
  }

  function renderActions() {
    const actionRows = actionItems.map((item) =>
      textValue(item as Record<string, unknown>, ['task', 'owner_name', 'owner', 'deadline', 'due_date', 'source_text', 'source']),
    );
    return renderListSection('待办与后续安排', actionRows);
  }

  function renderDecisions() {
    return renderListSection(
      '核心结论',
      decisions.map((item) => textValue(item, ['conclusion', 'decision', 'title', 'summary', 'reason'])),
    );
  }

  function renderQuestions() {
    const questionRows = (summary?.unresolved_issues?.length ? summary.unresolved_issues : summary?.open_questions || []).map((item) =>
      textValue(item, ['issue', 'question', 'reason', 'blocker', 'source_text', 'source']),
    );
    return renderListSection('遗留问题', questionRows);
  }

  function renderRisks() {
    const riskRows = (summary?.risks_and_focus?.length ? summary.risks_and_focus : summary?.risks || []).map((item) =>
      textValue(item, ['risk', 'impact', 'focus_area', 'mitigation', 'source_text']),
    );
    return renderListSection('风险与关注点', riskRows);
  }

  return (
    <>
    <ScrollView contentContainerStyle={styles.container}>
      {loading ? <ActivityIndicator color="#6657ff" /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {meeting ? (
        <>
          <View style={styles.topCard}>
            <View style={styles.topHeader}>
              <View style={styles.titleBlock}>
                <Text style={styles.meetingTitle}>{meeting.title}</Text>
                <Text style={styles.meetingMeta}>
                  {statusText(meeting.status)} · {new Date(meeting.created_at).toLocaleDateString()}
                </Text>
              </View>
              <Pressable onPress={() => onOpenAudioPlayer(meeting.id)} style={styles.audioIconButton}>
                <Text style={styles.audioIconText}>▶</Text>
              </Pressable>
            </View>

            <View style={styles.infoGrid}>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>会议时长</Text>
                <Text style={styles.infoValue}>{meetingDuration(meeting)}</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>参会人员</Text>
                {speakerLabels.length ? (
                  <View style={styles.participantList}>
                    {speakerLabels.map((speakerLabel) => (
                      <View key={speakerLabel} style={styles.participantChip}>
                        <Pressable onPress={() => openSpeakerEditor(speakerLabel)} style={styles.participantEditButton}>
                          <LucideIcon name="pencil-line" color="#6657ff" size={13} strokeWidth={2.2} />
                        </Pressable>
                        <Text style={styles.participantName}>{displaySpeaker(speakerLabel)}</Text>
                      </View>
                    ))}
                  </View>
                ) : (
                  <Text style={styles.infoValue}>{participants}</Text>
                )}
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>开始时间</Text>
                <Text style={styles.infoValue}>{formatDateTime(meeting.created_at)} 开始</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>结束时间</Text>
                <Text style={styles.infoValue}>{formatDateTime(meeting.end_at)} 结束</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>会议地址</Text>
                <Text style={styles.infoValue}>{meeting.location || '未填写'}</Text>
              </View>
            </View>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs}>
            {tabs.map((tab) => {
              const isActive = activeTab === tab.key;
              return (
                <Pressable key={tab.key} onPress={() => setActiveTab(tab.key)} style={styles.tabButton}>
                  <Text style={[styles.tabText, isActive ? styles.tabTextActive : null]}>{tab.label}</Text>
                  {isActive ? <View style={styles.tabLine} /> : null}
                </Pressable>
              );
            })}
          </ScrollView>

          {activeTab === 'summary' ? renderSummary() : null}
          {activeTab === 'transcript' ? renderTranscript() : null}
          {activeTab === 'actions' ? renderActions() : null}
          {activeTab === 'decisions' ? renderDecisions() : null}
          {activeTab === 'questions' ? renderQuestions() : null}
          {activeTab === 'risks' ? renderRisks() : null}
        </>
      ) : null}
    </ScrollView>
    <Modal transparent visible={!!editingSpeakerLabel} animationType="fade" onRequestClose={() => setEditingSpeakerLabel(null)}>
      <View style={styles.modalOverlay}>
        <View style={styles.speakerModal}>
          <Text style={styles.speakerModalTitle}>编辑发言人名称</Text>
          <Text style={styles.speakerModalSub}>{editingSpeakerLabel ? displaySpeaker(editingSpeakerLabel) : ''}</Text>
          <TextInput
            value={editingSpeakerLabel ? speakerNameDrafts[editingSpeakerLabel] || '' : ''}
            onChangeText={(value) => {
              if (!editingSpeakerLabel) return;
              setSpeakerNameDrafts((current) => ({ ...current, [editingSpeakerLabel]: value }));
            }}
            placeholder="请输入发言人名称"
            placeholderTextColor="#aeb6c5"
            style={styles.speakerModalInput}
          />
          <View style={styles.speakerModalActions}>
            <Pressable onPress={() => setEditingSpeakerLabel(null)} style={[styles.speakerModalButton, styles.speakerModalCancel]}>
              <Text style={styles.speakerModalCancelText}>取消</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                if (editingSpeakerLabel) saveSpeaker(editingSpeakerLabel);
              }}
              style={[styles.speakerModalButton, styles.speakerModalSave]}
            >
              <Text style={styles.speakerModalSaveText}>{savingSpeaker === editingSpeakerLabel ? '保存中' : '保存'}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 12,
    paddingBottom: 88,
    paddingHorizontal: 18,
    paddingTop: 4,
  },
  topCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    gap: 14,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  topHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  titleBlock: {
    flex: 1,
  },
  meetingTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  meetingMeta: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 4,
  },
  infoGrid: {
    gap: 10,
  },
  audioIconButton: {
    alignItems: 'center',
    backgroundColor: '#f0efff',
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  audioIconText: {
    color: '#6657ff',
    fontSize: 13,
    fontWeight: '900',
  },
  infoItem: {
    backgroundColor: '#f8f9ff',
    borderRadius: 14,
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  infoLabel: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
  },
  infoValue: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 20,
  },
  participantList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 2,
  },
  participantChip: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 5,
    minHeight: 30,
    paddingLeft: 7,
    paddingRight: 10,
  },
  participantEditButton: {
    alignItems: 'center',
    backgroundColor: '#f0efff',
    borderRadius: 999,
    height: 22,
    justifyContent: 'center',
    width: 22,
  },
  participantName: {
    color: '#111827',
    fontSize: 12,
    fontWeight: '900',
  },
  tabs: {
    alignItems: 'center',
    gap: 10,
    paddingBottom: 4,
    paddingTop: 8,
  },
  tabButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 14,
    borderWidth: 1,
    gap: 4,
    justifyContent: 'center',
    minHeight: 38,
    minWidth: 64,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tabText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
  },
  tabTextActive: {
    color: '#6657ff',
  },
  tabLine: {
    backgroundColor: '#6657ff',
    borderRadius: 2,
    height: 2,
    width: 20,
  },
  summaryHero: {
    backgroundColor: '#ffffff',
    borderColor: '#ebeef8',
    borderRadius: 22,
    borderWidth: 1,
    gap: 14,
    padding: 18,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 22,
    elevation: 4,
  },
  summaryHeroHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  summaryHeroTitle: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
    marginTop: 4,
  },
  statusPill: {
    backgroundColor: '#ecfdf3',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusPillText: {
    color: '#16a34a',
    fontSize: 12,
    fontWeight: '900',
  },
  sourcePill: {
    alignSelf: 'flex-start',
    backgroundColor: '#f8fafc',
    borderColor: '#dbe3ef',
    borderRadius: 8,
    borderWidth: 1,
    gap: 2,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  sourcePillText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '900',
  },
  sourceHintText: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: '700',
  },
  summaryLead: {
    color: '#374151',
    fontSize: 14,
    lineHeight: 24,
  },
  metricGrid: {
    flexDirection: 'row',
    gap: 8,
  },
  metricCard: {
    backgroundColor: '#f7f8ff',
    borderRadius: 16,
    flex: 1,
    paddingVertical: 12,
  },
  metricValue: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  metricLabel: {
    color: '#8b95a7',
    fontSize: 11,
    fontWeight: '800',
    marginTop: 3,
    textAlign: 'center',
  },
  contentCard: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 20,
    borderWidth: 1,
    gap: 12,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.05,
    shadowRadius: 18,
    elevation: 2,
  },
  cardTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  exportTitle: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
  },
  exportRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  exportButton: {
    backgroundColor: '#f0efff',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  exportText: {
    color: '#6657ff',
    fontSize: 12,
    fontWeight: '900',
  },
  orderedListRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 2,
  },
  orderedListIndex: {
    color: '#6657ff',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 22,
    minWidth: 24,
  },
  cleanBulletText: {
    color: '#374151',
    flex: 1,
    fontSize: 13,
    lineHeight: 22,
  },
  searchBox: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    minHeight: 44,
    paddingHorizontal: 13,
  },
  searchIcon: {
    color: '#9ca3af',
    fontSize: 16,
    fontWeight: '900',
  },
  searchInput: {
    color: '#111827',
    flex: 1,
    fontSize: 13,
    minHeight: 42,
  },
  durationStrip: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  durationChip: {
    alignItems: 'center',
    backgroundColor: '#f8f9ff',
    borderColor: '#eef0f6',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  durationName: {
    color: '#111827',
    fontSize: 12,
    fontWeight: '900',
  },
  durationValue: {
    color: '#8b95a7',
    fontSize: 11,
    fontWeight: '800',
  },
  paragraph: {
    color: '#374151',
    fontSize: 13,
    lineHeight: 22,
  },
  empty: {
    color: '#8b95a7',
    fontSize: 13,
    lineHeight: 22,
  },
  speakerEditor: {
    backgroundColor: '#f8f9ff',
    borderRadius: 16,
    gap: 8,
    padding: 10,
  },
  speakerLabel: {
    color: '#6657ff',
    fontSize: 12,
    fontWeight: '900',
  },
  speakerInput: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 12,
    borderWidth: 1,
    color: '#111827',
    minHeight: 38,
    paddingHorizontal: 10,
  },
  speakerNoteInput: {
    minHeight: 64,
    paddingTop: 9,
    textAlignVertical: 'top',
  },
  saveSpeakerButton: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 12,
    paddingHorizontal: 11,
    paddingVertical: 10,
  },
  saveSpeakerText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '900',
  },
  modalOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.35)',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  speakerModal: {
    backgroundColor: '#ffffff',
    borderRadius: 22,
    padding: 18,
    width: '100%',
  },
  speakerModalTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  speakerModalSub: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
    marginTop: 6,
  },
  speakerModalInput: {
    backgroundColor: '#f8f9ff',
    borderColor: '#eef0f6',
    borderRadius: 14,
    borderWidth: 1,
    color: '#111827',
    fontSize: 15,
    fontWeight: '800',
    marginTop: 14,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  speakerModalActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  speakerModalButton: {
    alignItems: 'center',
    borderRadius: 14,
    flex: 1,
    minHeight: 44,
    justifyContent: 'center',
  },
  speakerModalCancel: {
    backgroundColor: '#f3f4f6',
  },
  speakerModalSave: {
    backgroundColor: '#6657ff',
  },
  speakerModalCancelText: {
    color: '#6b7280',
    fontSize: 14,
    fontWeight: '900',
  },
  speakerModalSaveText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '900',
  },
  segment: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 8,
  },
  timeText: {
    color: '#9ca3af',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 19,
    paddingTop: 0,
    width: 54,
  },
  segmentBody: {
    flex: 1,
    gap: 5,
  },
  transcriptSpeakerLine: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 7,
  },
  speakerName: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 19,
  },
  segmentSeconds: {
    color: '#9ca3af',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 19,
  },
  segmentPlayButton: {
    alignItems: 'center',
    backgroundColor: '#f0efff',
    borderRadius: 15,
    height: 30,
    justifyContent: 'center',
    marginLeft: 'auto',
    width: 30,
  },
  segmentPlayText: {
    color: '#6657ff',
    fontSize: 12,
    fontWeight: '900',
  },
  todoCard: {
    alignItems: 'flex-start',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    padding: 14,
  },
  checkbox: {
    alignItems: 'center',
    borderColor: '#6657ff',
    borderRadius: 4,
    borderWidth: 1,
    height: 16,
    justifyContent: 'center',
    marginTop: 2,
    width: 16,
  },
  checkboxCompleted: {
    backgroundColor: '#6657ff',
  },
  checkboxCheck: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 13,
  },
  todoBody: {
    flex: 1,
  },
  todoTitle: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
  },
  todoTitleCompleted: {
    color: '#9ca3af',
    textDecorationLine: 'line-through',
  },
  todoMeta: {
    color: '#8b95a7',
    fontSize: 12,
  },
  error: {
    color: '#ef4444',
  },
});
