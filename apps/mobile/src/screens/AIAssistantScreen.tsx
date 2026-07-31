import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  AgentReviewChange,
  AgentReviewOverview,
  AgentReviewProposalCard,
  AgentReviewRecord,
  AgentReviewRecordDetail,
  approveAgentProposal,
  getAgentReviewOverview,
  getAgentReviewRecord,
  getAgentAuthToken,
  isApiRequestError,
  isAgentStorageError,
  listAgentReviewRecords,
  loadStoredAgentSession,
  loginAgentSession,
  rejectAgentProposal,
} from '../api';
import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

type Props = {
  onOpenRecords: () => void;
  onOpenRecordDetail: (recordId: string) => void;
};

type RecordsProps = {
  onBack: () => void;
  onOpenRecordDetail: (recordId: string) => void;
};

type DetailProps = {
  recordId: string;
  onBack: () => void;
};

type RecordStatusFilter = 'all' | 'pending_effective' | 'succeeded' | 'rejected' | 'rolled_back' | 'expired';
type SortFilter = 'latest' | 'oldest';
type AssistantViewState = 'loading' | 'unauthenticated' | 'forbidden' | 'empty' | 'data' | 'error';
const STORAGE_UNAVAILABLE_MESSAGE = '本地登录存储不可用，请重启应用';

const statusFilters: Array<{ label: string; value: RecordStatusFilter }> = [
  { label: '全部状态', value: 'all' },
  { label: '待生效', value: 'pending_effective' },
  { label: '已生效', value: 'succeeded' },
  { label: '已拒绝', value: 'rejected' },
  { label: '已撤销', value: 'rolled_back' },
  { label: '已过期', value: 'expired' },
];

const sortFilters: Array<{ label: string; value: SortFilter }> = [
  { label: '按时间排序', value: 'latest' },
  { label: '最早优先', value: 'oldest' },
];

export function AIAssistantScreen({ onOpenRecords, onOpenRecordDetail }: Props) {
  const [overview, setOverview] = useState<AgentReviewOverview | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<AgentReviewProposalCard | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewState, setViewState] = useState<AssistantViewState>('loading');
  const [loggingIn, setLoggingIn] = useState(false);

  const refresh = useCallback(async () => {
    setViewState('loading');
    setError(null);
    try {
      try {
        await loadStoredAgentSession();
      } catch (storageError) {
        if (isAgentStorageError(storageError)) {
          setError(storageError.message || STORAGE_UNAVAILABLE_MESSAGE);
          if (!getAgentAuthToken()) {
            setViewState('error');
            return;
          }
        } else {
          throw storageError;
        }
      }
      const next = await getAgentReviewOverview();
      setOverview(next);
      setExpandedId((current) => current || next.pending_proposals[0]?.id || null);
      setViewState(next.pending_proposals.length > 0 || next.recent_records.length > 0 ? 'data' : 'empty');
    } catch (err) {
      if (isApiRequestError(err, 401)) {
        setViewState('unauthenticated');
        setOverview(null);
        setError(null);
      } else if (isApiRequestError(err, 403)) {
        setViewState('forbidden');
        setOverview(null);
        setError(null);
      } else {
        setViewState('error');
        setError(errorMessage(err));
      }
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function approve(proposal: AgentReviewProposalCard) {
    if (submittingId) return;
    setSubmittingId(proposal.id);
    setError(null);
    setNotice(null);
    try {
      const result = await approveAgentProposal(proposal.id, '移动端采纳建议');
      setNotice(result.command?.status === 'ready' ? '建议已采纳，等待执行' : '建议已采纳');
      await refresh();
    } catch (err) {
      if (isApiRequestError(err, 401)) {
        setViewState('unauthenticated');
      } else if (isApiRequestError(err, 403)) {
        setViewState('forbidden');
      }
      setError(errorMessage(err));
    } finally {
      setSubmittingId(null);
    }
  }

  async function reject() {
    const proposal = rejecting;
    if (!proposal || submittingId) return;
    setSubmittingId(proposal.id);
    setError(null);
    setNotice(null);
    try {
      await rejectAgentProposal(proposal.id, rejectReason.trim());
      setRejecting(null);
      setRejectReason('');
      setNotice('已不采纳这条建议');
      await refresh();
    } catch (err) {
      if (isApiRequestError(err, 401)) {
        setViewState('unauthenticated');
      } else if (isApiRequestError(err, 403)) {
        setViewState('forbidden');
      }
      setError(errorMessage(err));
    } finally {
      setSubmittingId(null);
    }
  }

  function confirmApprove(proposal: AgentReviewProposalCard) {
    Alert.alert('确认采纳这条建议？', '采纳后系统会生成待执行命令，不会直接修改数据。', [
      { text: '取消', style: 'cancel' },
      { text: '采纳建议', onPress: () => approve(proposal) },
    ]);
  }

  async function login() {
    if (loggingIn) return;
    setLoggingIn(true);
    setError(null);
    try {
      await loginAgentSession('本地验收用户');
      setNotice('登录成功');
      await refresh();
    } catch (err) {
      if (isAgentStorageError(err) && getAgentAuthToken()) {
        setError(err.message || STORAGE_UNAVAILABLE_MESSAGE);
        await refresh();
      } else {
        setViewState(isApiRequestError(err, 403) ? 'forbidden' : 'error');
        setError(errorMessage(err));
      }
    } finally {
      setLoggingIn(false);
    }
  }

  const pending = overview?.pending_proposals || [];
  const records = overview?.recent_records || [];
  const loading = viewState === 'loading';
  const canShowSections = viewState === 'data' || viewState === 'empty';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.homeContent}>
      <AssistantHeader />
      <SafetyBanner />
      {notice ? <Message tone="good" text={notice} /> : null}
      {error && viewState !== 'unauthenticated' && viewState !== 'forbidden' ? <Message tone="bad" text={error} /> : null}
      {loading ? <SkeletonList /> : null}
      {viewState === 'unauthenticated' ? (
        <ActionState
          title="登录状态已失效，请重新登录"
          text="登录后才能查看和确认 AI 修改建议。"
          action={loggingIn ? '登录中...' : '重新登录'}
          disabled={loggingIn}
          onPress={login}
        />
      ) : null}
      {viewState === 'forbidden' ? (
        <ActionState title="暂无权限查看 AI 建议" text="请使用具备 Agent 审核权限的账号登录。" action="重新登录" disabled={loggingIn} onPress={login} />
      ) : null}
      {viewState === 'error' ? (
        <ActionState title="AI 建议加载失败" text={error || '网络错误，请稍后重试'} action="重试" onPress={refresh} />
      ) : null}

      {canShowSections ? (
        <View style={styles.section}>
          <SectionTitle title={`待你确认的建议 ${overview?.pending_count || 0}`} action="全部建议" onPress={onOpenRecords} />
          {pending.length === 0 ? <EmptyState title="暂无建议" text="当前没有需要你确认的修改建议。" /> : null}
          {pending.map((proposal, index) => (
            <PendingProposalCard
              key={proposal.id}
              proposal={proposal}
              expanded={expandedId === proposal.id || (!expandedId && index === 0)}
              submitting={submittingId === proposal.id}
              onToggle={() => setExpandedId(expandedId === proposal.id ? null : proposal.id)}
              onApprove={() => confirmApprove(proposal)}
              onReject={() => setRejecting(proposal)}
            />
          ))}
        </View>
      ) : null}

      {canShowSections ? (
        <View style={styles.section}>
          <SectionTitle title="最近处理" action="全部记录" onPress={onOpenRecords} />
          {records.length === 0 ? <EmptyState title="暂无处理记录" text="采纳或不采纳建议后会显示在这里。" /> : null}
          {records.map((record) => (
            <RecentRecordItem key={record.id} record={record} onPress={() => onOpenRecordDetail(record.id)} />
          ))}
        </View>
      ) : null}

      <RejectModal
        visible={Boolean(rejecting)}
        reason={rejectReason}
        submitting={Boolean(rejecting && submittingId === rejecting.id)}
        onChangeReason={setRejectReason}
        onCancel={() => {
          setRejecting(null);
          setRejectReason('');
        }}
        onConfirm={reject}
      />
    </ScrollView>
  );
}

export function AllAgentRecordsScreen({ onBack, onOpenRecordDetail }: RecordsProps) {
  const [status, setStatus] = useState<RecordStatusFilter>('all');
  const [sort, setSort] = useState<SortFilter>('latest');
  const [items, setItems] = useState<AgentReviewRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextPage: number, append = false) => {
    append ? setLoadingMore(true) : setLoading(true);
    setError(null);
    try {
      const response = await listAgentReviewRecords({ status, sort, page: nextPage, page_size: 10 });
      setItems((current) => (append ? [...current, ...response.items] : response.items));
      setTotal(response.total);
      setPage(response.page);
      setHasMore(response.has_more);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [sort, status]);

  useEffect(() => {
    load(1);
  }, [load]);

  return (
    <View style={styles.container}>
      <View style={styles.recordsHeader}>
        <IconButton icon="chevron-left" onPress={onBack} />
        <Text style={styles.recordsTitle}>全部记录</Text>
        <View style={styles.headerIcon}>
          <LucideIcon name="filter" color="#374151" size={24} strokeWidth={2.2} />
        </View>
      </View>
      <RecordFilterBar status={status} sort={sort} onStatus={setStatus} onSort={setSort} />
      <ScrollView style={styles.recordsScroll} contentContainerStyle={styles.recordsContent}>
        <Text style={styles.totalText}>共 {total} 条记录</Text>
        {error ? <Message tone="bad" text={error} /> : null}
        {loading ? <SkeletonList /> : null}
        {!loading && items.length === 0 ? <EmptyState title="暂无记录" text="换个筛选条件试试。" /> : null}
        {!loading ? items.map((record) => <RecordCard key={record.id} record={record} onPress={() => onOpenRecordDetail(record.id)} />) : null}
        {hasMore ? (
          <Pressable style={[styles.loadMoreButton, loadingMore ? styles.disabled : null]} onPress={() => load(page + 1, true)} disabled={loadingMore}>
            {loadingMore ? <ActivityIndicator color="#6657ff" /> : <Text style={styles.loadMoreText}>加载更多</Text>}
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

export function AgentRecordDetailScreen({ recordId, onBack }: DetailProps) {
  const [detail, setDetail] = useState<AgentReviewRecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAgentReviewRecord(recordId)
      .then((next) => {
        if (!cancelled) setDetail(next);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  return (
    <View style={styles.container}>
      <View style={styles.recordsHeader}>
        <IconButton icon="chevron-left" onPress={onBack} />
        <Text style={styles.recordsTitle}>记录详情</Text>
        <View style={styles.headerIcon} />
      </View>
      <ScrollView style={styles.recordsScroll} contentContainerStyle={styles.detailContent}>
        {loading ? <SkeletonList /> : null}
        {error ? <Message tone="bad" text={error} /> : null}
        {detail ? (
          <>
            <View style={styles.detailHero}>
              <Text style={styles.detailTitle}>{detail.proposal.action_label}：{detail.proposal.target_title}</Text>
              <StatusPill status={detail.proposal.status_label} rawStatus={detail.proposal.status} />
            </View>
            <DetailSection title="Proposal">
              <Field label="建议类型" value={detail.proposal.action_label} />
              <Field label="目标对象" value={detail.proposal.target_title} />
              <Field label="风险等级" value={detail.proposal.risk_label} />
              <Field label="是否真实写入" value={detail.writes_performed ? '是' : '否'} />
            </DetailSection>
            <DetailSection title="before / after">
              <ProposalChangeComparison changes={detail.before_after} />
              <Field label="对象版本变化" value={`${detail.object_version_before || '未知'} -> ${detail.object_version_after || '未变化'}`} />
            </DetailSection>
            <DetailSection title="Evidence">
              <EvidenceBlock evidence={detail.evidence} />
            </DetailSection>
            <DetailSection title="Confirmation">
              <Field label="Reviewer" value={detail.reviewer || '未记录'} />
              <Field label="确认结果" value={detail.confirmation?.decision || '未确认'} />
              <Field label="Reject / rollback 原因" value={detail.reject_reason || detail.rollback_reason || '无'} />
            </DetailSection>
            <DetailSection title="Command">
              <Field label="Command" value={detail.command?.id || '未生成'} />
              <Field label="Executor" value={detail.executor || '未执行'} />
              <Field label="当前状态" value={detail.command?.status || detail.proposal.status} />
            </DetailSection>
            <DetailSection title="Audit 时间线">
              {detail.audit_timeline.length === 0 ? <Text style={styles.emptyText}>暂无审计记录</Text> : null}
              {detail.audit_timeline.map((item) => (
                <View key={item.id} style={styles.timelineItem}>
                  <Text style={styles.timelineTitle}>{item.result_label}</Text>
                  <Text style={styles.timelineText}>{formatTime(item.created_at)} · {item.reviewer || '系统'}</Text>
                  {item.reasons.length ? <Text style={styles.timelineText}>{item.reasons.join('；')}</Text> : null}
                </View>
              ))}
            </DetailSection>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

function AssistantHeader() {
  return (
    <View style={styles.assistantHeader}>
      <View style={styles.titleRow}>
        <Text style={styles.mainTitle}>AI 助手</Text>
        <LucideIcon name="sparkles" color="#6657ff" size={28} strokeWidth={2.4} />
      </View>
      <Text style={styles.mainSubtitle}>AI 根据会议内容提出修改建议，需要你的确认</Text>
    </View>
  );
}

function SafetyBanner() {
  return (
    <View style={styles.safetyBanner}>
      <View style={styles.safetyIcon}>
        <LucideIcon name="circle-check-big" color="#6657ff" size={28} strokeWidth={2.4} />
      </View>
      <View style={styles.safetyTextWrap}>
        <Text style={styles.safetyTitle}>你控制节奏，数据安全有保障</Text>
        <Text style={styles.safetyText}>所有修改都需要你确认后才会生效</Text>
      </View>
    </View>
  );
}

function SectionTitle({ title, action, onPress }: { title: string; action: string; onPress: () => void }) {
  return (
    <View style={styles.sectionTitleRow}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Pressable style={styles.linkButton} onPress={onPress}>
        <Text style={styles.linkText}>{action}</Text>
        <LucideIcon name="chevron-right" color="#6b7280" size={18} strokeWidth={2.2} />
      </Pressable>
    </View>
  );
}

function PendingProposalCard({ proposal, expanded, submitting, onToggle, onApprove, onReject }: {
  proposal: AgentReviewProposalCard;
  expanded: boolean;
  submitting: boolean;
  onToggle: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <Pressable style={styles.proposalCard} onPress={onToggle}>
      <View style={styles.proposalTop}>
        <View style={styles.cardIcon}>
          <LucideIcon name={proposal.action_type === 'complete' ? 'flag' : 'square-check-big'} color="#6657ff" size={26} strokeWidth={2.4} />
        </View>
        <View style={styles.proposalMain}>
          <Text style={styles.proposalTitle}>{proposal.action_label}：{proposal.target_title}</Text>
          <Text style={styles.proposalMeta}>来自会议：{proposal.source_meeting_title || '未知会议'} · {formatTime(proposal.source_meeting_time)}</Text>
        </View>
        <View style={styles.cardRightStack}>
          <RiskPill level={proposal.risk_level} label={proposal.risk_label} />
          <LucideIcon name={expanded ? 'chevron-down' : 'chevron-right'} color="#8b95a7" size={18} strokeWidth={2.2} />
        </View>
      </View>
      {expanded ? (
        <>
          <ProposalChangeComparison changes={proposal.changes} />
          <EvidenceBlock evidence={proposal.evidence} />
          <View style={styles.actionRow}>
            <Pressable style={[styles.rejectButton, submitting ? styles.disabled : null]} onPress={onReject} disabled={submitting}>
              <LucideIcon name="circle-help" color="#6b7280" size={18} strokeWidth={2.2} />
              <Text style={styles.rejectText}>不采纳</Text>
            </Pressable>
            <Pressable style={[styles.approveButton, submitting ? styles.disabled : null]} onPress={onApprove} disabled={submitting}>
              {submitting ? <ActivityIndicator color="#ffffff" /> : <LucideIcon name="circle-check-big" color="#ffffff" size={18} strokeWidth={2.2} />}
              <Text style={styles.approveText}>采纳建议</Text>
            </Pressable>
          </View>
        </>
      ) : null}
    </Pressable>
  );
}

function ProposalChangeComparison({ changes }: { changes: AgentReviewChange[] }) {
  const shown = changes.length ? changes : [{ field: 'none', label: '修改内容', before: '未记录', after: '未记录' }];
  return (
    <View style={styles.comparisonRow}>
      <View style={styles.compareBox}>
        <Text style={styles.compareBeforeTitle}>修改前</Text>
        {shown.map((change) => <ChangeLine key={`before-${change.field}`} label={change.label} value={change.before || '未设置'} />)}
      </View>
      <Text style={styles.arrowText}>{'->'}</Text>
      <View style={styles.compareBox}>
        <Text style={styles.compareAfterTitle}>修改后（建议）</Text>
        {shown.map((change) => <ChangeLine key={`after-${change.field}`} label={change.label} value={change.after || '未设置'} accent />)}
      </View>
    </View>
  );
}

function ChangeLine({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  const icon: LucideIconName = label.includes('负责人') ? 'user' : label.includes('时间') ? 'calendar-days' : label.includes('状态') ? 'circle-check-big' : 'file-text';
  return (
    <View style={styles.changeLine}>
      <LucideIcon name={icon} color="#6b7280" size={15} strokeWidth={2.2} />
      <Text style={styles.changeLabel}>{label}：</Text>
      <Text style={[styles.changeValue, accent ? styles.changeValueAccent : null]} numberOfLines={1}>{value}</Text>
    </View>
  );
}

function EvidenceBlock({ evidence }: { evidence: AgentReviewProposalCard['evidence'] }) {
  const [expanded, setExpanded] = useState(false);
  if (!evidence?.source_text) {
    return <Text style={styles.emptyText}>暂无会议原话证据</Text>;
  }
  const long = evidence.source_text.length > 72;
  return (
    <Pressable style={styles.evidenceBox} onPress={() => setExpanded(!expanded)}>
      <Text style={styles.quoteIcon}>“</Text>
      <Text style={styles.evidenceText} numberOfLines={expanded || !long ? undefined : 2}>
        {evidence.source_text}
        {evidence.speaker ? `  — ${evidence.speaker}` : ''}
      </Text>
    </Pressable>
  );
}

function RecentRecordItem({ record, onPress }: { record: AgentReviewRecord; onPress: () => void }) {
  return (
    <Pressable style={styles.recentRow} onPress={onPress}>
      <RecordIcon status={record.status} />
      <View style={styles.recentMain}>
        <Text style={styles.recentTitle} numberOfLines={1}>{record.action_label}</Text>
        <Text style={styles.recentSummary} numberOfLines={1}>{record.status === 'rejected' ? `理由：${record.reason_preview || '未填写'}` : record.change_summary}</Text>
      </View>
      <Text style={styles.recentTime}>{formatTime(record.handled_at)}</Text>
      <StatusPill status={record.status_label} rawStatus={record.status} />
      <LucideIcon name="chevron-right" color="#8b95a7" size={18} strokeWidth={2.2} />
    </Pressable>
  );
}

function RecordFilterBar({ status, sort, onStatus, onSort }: {
  status: RecordStatusFilter;
  sort: SortFilter;
  onStatus: (value: RecordStatusFilter) => void;
  onSort: (value: SortFilter) => void;
}) {
  return (
    <View style={styles.filterWrap}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterScroller}>
        {statusFilters.map((item) => (
          <Pressable key={item.value} style={[styles.filterChip, status === item.value ? styles.filterChipActive : null]} onPress={() => onStatus(item.value)}>
            <Text style={[styles.filterText, status === item.value ? styles.filterTextActive : null]}>{item.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <View style={styles.sortRow}>
        {sortFilters.map((item) => (
          <Pressable key={item.value} style={[styles.sortChip, sort === item.value ? styles.sortChipActive : null]} onPress={() => onSort(item.value)}>
            <Text style={[styles.sortText, sort === item.value ? styles.sortTextActive : null]}>{item.label}</Text>
            <LucideIcon name="chevron-down" color={sort === item.value ? '#6657ff' : '#8b95a7'} size={16} strokeWidth={2.1} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function RecordCard({ record, onPress }: { record: AgentReviewRecord; onPress: () => void }) {
  const reasonOnly = record.status === 'rejected' || record.status === 'rolled_back';
  return (
    <Pressable style={styles.recordCard} onPress={onPress}>
      <RecordIcon status={record.status} large />
      <View style={styles.recordMain}>
        <Text style={styles.recordTitle}>{record.action_label}</Text>
        <Text style={styles.recordSummary}>{reasonOnly ? '查看原因 >' : record.change_summary}</Text>
        <Text style={styles.recordTime}>{formatTime(record.handled_at)}</Text>
      </View>
      <StatusPill status={record.status_label} rawStatus={record.status} />
      <LucideIcon name="chevron-right" color="#6b7280" size={20} strokeWidth={2.2} />
    </Pressable>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.detailSection}>
      <Text style={styles.detailSectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fieldRow}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{value || '无'}</Text>
    </View>
  );
}

function RiskPill({ level, label }: { level: string; label: string }) {
  const tone = level === 'low' ? styles.riskLow : level === 'high' || level === 'critical' ? styles.riskHigh : styles.riskMedium;
  const textTone = level === 'low' ? styles.riskLowText : level === 'high' || level === 'critical' ? styles.riskHighText : styles.riskMediumText;
  return <Text style={[styles.riskPill, tone, textTone]}>{label}</Text>;
}

function StatusPill({ status, rawStatus }: { status: string; rawStatus: string }) {
  const tone = rawStatus === 'succeeded' || status === '已生效'
    ? styles.statusGood
    : rawStatus === 'rejected' || status === '已拒绝'
      ? styles.statusBad
      : rawStatus === 'rolled_back' || status === '已撤销'
        ? styles.statusOrange
        : styles.statusNeutral;
  return <Text style={[styles.statusPill, tone]}>{status}</Text>;
}

function RecordIcon({ status, large = false }: { status: string; large?: boolean }) {
  const icon = status === 'rolled_back' ? 'rotate-ccw' : status === 'rejected' ? 'circle-help' : status === 'expired' ? 'calendar-days' : status === 'succeeded' ? 'circle-check-big' : 'square-check-big';
  const color = status === 'rolled_back' ? '#f97316' : status === 'rejected' ? '#ef4444' : status === 'expired' ? '#6b7280' : status === 'succeeded' ? '#22c55e' : '#6657ff';
  return (
    <View style={[styles.recordIcon, large ? styles.recordIconLarge : null, { backgroundColor: iconBg(status) }]}>
      <LucideIcon name={icon} color={color} size={large ? 28 : 22} strokeWidth={2.6} />
    </View>
  );
}

function IconButton({ icon, onPress }: { icon: LucideIconName; onPress: () => void }) {
  return (
    <Pressable style={styles.headerIcon} onPress={onPress}>
      <LucideIcon name={icon} color="#374151" size={26} strokeWidth={2.2} />
    </Pressable>
  );
}

function Message({ tone, text }: { tone: 'good' | 'bad'; text: string }) {
  return <Text style={[styles.message, tone === 'good' ? styles.messageGood : styles.messageBad]}>{text}</Text>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <View style={styles.emptyBox}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

function ActionState({ title, text, action, disabled = false, onPress }: {
  title: string;
  text: string;
  action: string;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <View style={styles.actionStateBox}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyText}>{text}</Text>
      <Pressable style={[styles.stateActionButton, disabled ? styles.disabled : null]} onPress={onPress} disabled={disabled}>
        {disabled ? <ActivityIndicator color="#ffffff" /> : null}
        <Text style={styles.stateActionText}>{action}</Text>
      </Pressable>
    </View>
  );
}

function SkeletonList() {
  return (
    <View style={styles.skeletonWrap}>
      {[0, 1, 2].map((item) => <View key={item} style={styles.skeletonCard} />)}
    </View>
  );
}

function RejectModal({ visible, reason, submitting, onChangeReason, onCancel, onConfirm }: {
  visible: boolean;
  reason: string;
  submitting: boolean;
  onChangeReason: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.modalBackdrop}>
        <View style={styles.modalCard}>
          <Text style={styles.modalTitle}>确认不采纳这条建议？</Text>
          <TextInput
            value={reason}
            onChangeText={onChangeReason}
            placeholder="可选：填写原因"
            placeholderTextColor="#9ca3af"
            multiline
            style={styles.reasonInput}
          />
          <View style={styles.modalActions}>
            <Pressable style={styles.modalCancel} onPress={onCancel} disabled={submitting}>
              <Text style={styles.modalCancelText}>取消</Text>
            </Pressable>
            <Pressable style={[styles.modalConfirm, submitting ? styles.disabled : null]} onPress={onConfirm} disabled={submitting}>
              <Text style={styles.modalConfirmText}>确认不采纳</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

function iconBg(status: string): string {
  if (status === 'rolled_back') return '#fff7ed';
  if (status === 'rejected') return '#fef2f2';
  if (status === 'expired') return '#f3f4f6';
  if (status === 'succeeded') return '#ecfdf5';
  return '#f0efff';
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : '网络错误，请稍后重试';
}

function formatTime(value: string | null): string {
  if (!value) return '时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  if (startDate === startToday) return `今天 ${hh}:${mm}`;
  if (startDate === startToday - 24 * 60 * 60 * 1000) return `昨天 ${hh}:${mm}`;
  return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${hh}:${mm}`;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f7f8fc' },
  homeContent: { gap: 14, padding: 16, paddingBottom: 100 },
  assistantHeader: { gap: 8, paddingTop: 8 },
  titleRow: { alignItems: 'center', flexDirection: 'row', gap: 8 },
  mainTitle: { color: '#111827', fontSize: 34, fontWeight: '900', letterSpacing: 0 },
  mainSubtitle: { color: '#667085', fontSize: 15, fontWeight: '700', lineHeight: 21 },
  safetyBanner: {
    alignItems: 'center',
    backgroundColor: '#fbfaff',
    borderColor: '#d8d2ff',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 14,
    padding: 16,
  },
  safetyIcon: { alignItems: 'center', backgroundColor: '#f0efff', borderRadius: 8, height: 48, justifyContent: 'center', width: 48 },
  safetyTextWrap: { flex: 1, gap: 5 },
  safetyTitle: { color: '#111827', fontSize: 18, fontWeight: '900', lineHeight: 24 },
  safetyText: { color: '#667085', fontSize: 15, fontWeight: '700', lineHeight: 21 },
  section: { backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 8, borderWidth: 1, gap: 12, padding: 12 },
  sectionTitleRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  sectionTitle: { color: '#111827', fontSize: 20, fontWeight: '900', letterSpacing: 0 },
  linkButton: { alignItems: 'center', flexDirection: 'row', gap: 4, minHeight: 34 },
  linkText: { color: '#667085', fontSize: 14, fontWeight: '800' },
  proposalCard: { borderColor: '#e5e7ef', borderRadius: 8, borderWidth: 1, gap: 12, padding: 12 },
  proposalTop: { alignItems: 'flex-start', flexDirection: 'row', gap: 12 },
  cardIcon: { alignItems: 'center', backgroundColor: '#f0efff', borderRadius: 8, height: 44, justifyContent: 'center', width: 44 },
  proposalMain: { flex: 1, gap: 5 },
  proposalTitle: { color: '#111827', fontSize: 16, fontWeight: '900', lineHeight: 22 },
  proposalMeta: { color: '#667085', fontSize: 13, fontWeight: '700', lineHeight: 18 },
  cardRightStack: { alignItems: 'flex-end', gap: 10 },
  riskPill: { borderRadius: 6, fontSize: 12, fontWeight: '900', overflow: 'hidden', paddingHorizontal: 8, paddingVertical: 5 },
  riskLow: { backgroundColor: '#eaf8ef' },
  riskLowText: { color: '#16a34a' },
  riskMedium: { backgroundColor: '#fff7ed' },
  riskMediumText: { color: '#f97316' },
  riskHigh: { backgroundColor: '#fef2f2' },
  riskHighText: { color: '#ef4444' },
  comparisonRow: { alignItems: 'center', flexDirection: 'row', gap: 8 },
  compareBox: { backgroundColor: '#f9fafc', borderRadius: 8, flex: 1, gap: 8, minHeight: 94, padding: 12 },
  compareBeforeTitle: { color: '#667085', fontSize: 13, fontWeight: '900' },
  compareAfterTitle: { color: '#16a34a', fontSize: 13, fontWeight: '900' },
  arrowText: { color: '#6b7280', fontSize: 18, fontWeight: '900' },
  changeLine: { alignItems: 'center', flexDirection: 'row', gap: 5 },
  changeLabel: { color: '#667085', fontSize: 12, fontWeight: '800' },
  changeValue: { color: '#111827', flex: 1, fontSize: 13, fontWeight: '900' },
  changeValueAccent: { color: '#4f46e5' },
  evidenceBox: { alignItems: 'flex-start', backgroundColor: '#f9fafc', borderRadius: 8, flexDirection: 'row', gap: 8, padding: 10 },
  quoteIcon: { color: '#667085', fontSize: 24, fontWeight: '900', lineHeight: 24 },
  evidenceText: { color: '#667085', flex: 1, fontSize: 13, fontWeight: '700', lineHeight: 20 },
  actionRow: { flexDirection: 'row', gap: 10 },
  rejectButton: { alignItems: 'center', borderColor: '#e5e7eb', borderRadius: 8, borderWidth: 1, flex: 1, flexDirection: 'row', gap: 8, justifyContent: 'center', minHeight: 48 },
  approveButton: { alignItems: 'center', backgroundColor: '#4f46e5', borderRadius: 8, flex: 1, flexDirection: 'row', gap: 8, justifyContent: 'center', minHeight: 48 },
  rejectText: { color: '#111827', fontSize: 16, fontWeight: '900' },
  approveText: { color: '#ffffff', fontSize: 16, fontWeight: '900' },
  recentRow: { alignItems: 'center', borderTopColor: '#eef0f6', borderTopWidth: 1, flexDirection: 'row', gap: 10, minHeight: 62, paddingTop: 10 },
  recentMain: { flex: 1, gap: 4 },
  recentTitle: { color: '#111827', fontSize: 14, fontWeight: '900' },
  recentSummary: { color: '#667085', fontSize: 12, fontWeight: '700' },
  recentTime: { color: '#667085', fontSize: 12, fontWeight: '700' },
  recordIcon: { alignItems: 'center', borderRadius: 8, height: 38, justifyContent: 'center', width: 38 },
  recordIconLarge: { height: 58, width: 58 },
  statusPill: { borderRadius: 6, fontSize: 12, fontWeight: '900', overflow: 'hidden', paddingHorizontal: 8, paddingVertical: 5 },
  statusGood: { backgroundColor: '#eaf8ef', color: '#16a34a' },
  statusBad: { backgroundColor: '#fef2f2', color: '#ef4444' },
  statusOrange: { backgroundColor: '#fff7ed', color: '#f97316' },
  statusNeutral: { backgroundColor: '#f3f4f6', color: '#667085' },
  recordsHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 18, paddingTop: 14 },
  recordsTitle: { color: '#111827', fontSize: 28, fontWeight: '900', letterSpacing: 0 },
  headerIcon: { alignItems: 'center', height: 44, justifyContent: 'center', width: 44 },
  filterWrap: { gap: 12, paddingHorizontal: 16, paddingTop: 20 },
  filterScroller: { gap: 8 },
  filterChip: { backgroundColor: '#ffffff', borderColor: '#e0e5ef', borderRadius: 8, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 10 },
  filterChipActive: { borderColor: '#6657ff', backgroundColor: '#f0efff' },
  filterText: { color: '#667085', fontSize: 14, fontWeight: '800' },
  filterTextActive: { color: '#4f46e5' },
  sortRow: { flexDirection: 'row', gap: 12 },
  sortChip: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#e0e5ef', borderRadius: 8, borderWidth: 1, flex: 1, flexDirection: 'row', justifyContent: 'space-between', minHeight: 52, paddingHorizontal: 14 },
  sortChipActive: { borderColor: '#d8d2ff' },
  sortText: { color: '#667085', fontSize: 15, fontWeight: '800' },
  sortTextActive: { color: '#111827' },
  recordsScroll: { flex: 1 },
  recordsContent: { gap: 12, padding: 16, paddingBottom: 100 },
  totalText: { color: '#8b95a7', fontSize: 16, fontWeight: '800', marginVertical: 4 },
  recordCard: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 8, borderWidth: 1, flexDirection: 'row', gap: 14, minHeight: 116, padding: 16 },
  recordMain: { flex: 1, gap: 8 },
  recordTitle: { color: '#111827', fontSize: 18, fontWeight: '900', lineHeight: 24 },
  recordSummary: { color: '#667085', fontSize: 15, fontWeight: '700', lineHeight: 21 },
  recordTime: { color: '#667085', fontSize: 14, fontWeight: '700' },
  loadMoreButton: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#e5e7ef', borderRadius: 8, borderWidth: 1, minHeight: 46, justifyContent: 'center' },
  loadMoreText: { color: '#6657ff', fontSize: 14, fontWeight: '900' },
  detailContent: { gap: 12, padding: 16, paddingBottom: 100 },
  detailHero: { backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 8, borderWidth: 1, gap: 12, padding: 16 },
  detailTitle: { color: '#111827', fontSize: 20, fontWeight: '900', lineHeight: 28 },
  detailSection: { backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 8, borderWidth: 1, gap: 10, padding: 14 },
  detailSectionTitle: { color: '#111827', fontSize: 16, fontWeight: '900' },
  fieldRow: { gap: 4 },
  fieldLabel: { color: '#8b95a7', fontSize: 12, fontWeight: '900' },
  fieldValue: { color: '#111827', fontSize: 14, fontWeight: '700', lineHeight: 20 },
  timelineItem: { borderTopColor: '#eef0f6', borderTopWidth: 1, gap: 4, paddingTop: 10 },
  timelineTitle: { color: '#111827', fontSize: 14, fontWeight: '900' },
  timelineText: { color: '#667085', fontSize: 13, fontWeight: '700', lineHeight: 19 },
  message: { borderRadius: 8, fontSize: 13, fontWeight: '800', lineHeight: 19, padding: 10 },
  messageGood: { backgroundColor: '#ecfdf5', color: '#047857' },
  messageBad: { backgroundColor: '#fef2f2', color: '#b91c1c' },
  emptyBox: { alignItems: 'center', gap: 6, padding: 18 },
  actionStateBox: { alignItems: 'center', backgroundColor: '#ffffff', borderColor: '#edf0f7', borderRadius: 8, borderWidth: 1, gap: 10, padding: 18 },
  emptyTitle: { color: '#111827', fontSize: 16, fontWeight: '900' },
  emptyText: { color: '#8b95a7', fontSize: 13, fontWeight: '700', lineHeight: 19 },
  stateActionButton: { alignItems: 'center', backgroundColor: '#4f46e5', borderRadius: 8, flexDirection: 'row', gap: 8, justifyContent: 'center', minHeight: 44, minWidth: 120, paddingHorizontal: 18 },
  stateActionText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
  skeletonWrap: { gap: 10 },
  skeletonCard: { backgroundColor: '#eef0f6', borderRadius: 8, height: 104, opacity: 0.8 },
  modalBackdrop: { alignItems: 'center', backgroundColor: 'rgba(17,24,39,0.38)', flex: 1, justifyContent: 'center', padding: 24 },
  modalCard: { backgroundColor: '#ffffff', borderRadius: 8, gap: 14, padding: 18, width: '100%' },
  modalTitle: { color: '#111827', fontSize: 18, fontWeight: '900' },
  reasonInput: { borderColor: '#e5e7eb', borderRadius: 8, borderWidth: 1, color: '#111827', fontSize: 14, minHeight: 86, padding: 12, textAlignVertical: 'top' },
  modalActions: { flexDirection: 'row', gap: 10 },
  modalCancel: { alignItems: 'center', borderColor: '#e5e7eb', borderRadius: 8, borderWidth: 1, flex: 1, minHeight: 44, justifyContent: 'center' },
  modalConfirm: { alignItems: 'center', backgroundColor: '#ef4444', borderRadius: 8, flex: 1, minHeight: 44, justifyContent: 'center' },
  modalCancelText: { color: '#374151', fontSize: 14, fontWeight: '900' },
  modalConfirmText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
  disabled: { opacity: 0.5 },
});
