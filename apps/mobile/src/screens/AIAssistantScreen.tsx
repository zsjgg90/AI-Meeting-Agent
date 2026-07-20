import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  AgentActionProposal,
  AgentAuditRecord,
  AgentCommandDryRunResult,
  AgentProposalStatus,
  ControlledWriteCommand,
  approveAgentProposal,
  dryRunAgentCommand,
  getAgentProposal,
  listAgentCommandAudits,
  listAgentCommands,
  listAgentProposals,
  rejectAgentProposal,
} from '../api';

const proposalStatuses: AgentProposalStatus[] = ['pending', 'approved', 'rejected', 'expired', 'conflict', 'duplicate', 'ready'];

function formatJson(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'string') return value || '-';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function statusTone(status: string): 'neutral' | 'good' | 'bad' | 'warn' {
  if (['approved', 'ready', 'dry_run', 'duplicate'].includes(status)) return 'good';
  if (['rejected', 'conflict', 'expired'].includes(status)) return 'bad';
  if (status === 'pending') return 'warn';
  return 'neutral';
}

export function AIAssistantScreen() {
  const [status, setStatus] = useState<AgentProposalStatus>('pending');
  const [proposals, setProposals] = useState<AgentActionProposal[]>([]);
  const [selectedProposal, setSelectedProposal] = useState<AgentActionProposal | null>(null);
  const [commands, setCommands] = useState<ControlledWriteCommand[]>([]);
  const [selectedCommand, setSelectedCommand] = useState<ControlledWriteCommand | null>(null);
  const [audits, setAudits] = useState<AgentAuditRecord[]>([]);
  const [dryRunResult, setDryRunResult] = useState<AgentCommandDryRunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedReadyCommand = useMemo(() => {
    if (selectedCommand) return selectedCommand;
    if (!selectedProposal) return null;
    return commands.find((command) => command.proposal_id === selectedProposal.id) || null;
  }, [commands, selectedCommand, selectedProposal]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextProposals, nextCommands] = await Promise.all([listAgentProposals(status), listAgentCommands('ready')]);
      setProposals(nextProposals);
      setCommands(nextCommands);
      if (selectedProposal) {
        const refreshed = nextProposals.find((item) => item.id === selectedProposal.id);
        setSelectedProposal(refreshed ?? (await getAgentProposal(selectedProposal.id)));
      } else if (nextProposals.length > 0) {
        setSelectedProposal(nextProposals[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Agent proposals.');
    } finally {
      setLoading(false);
    }
  }, [selectedProposal, status]);

  const loadAudits = useCallback(async (commandId: string) => {
    try {
      setAudits(await listAgentCommandAudits(commandId));
    } catch {
      setAudits([]);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (selectedReadyCommand) {
      loadAudits(selectedReadyCommand.id);
    } else {
      setAudits([]);
    }
  }, [loadAudits, selectedReadyCommand]);

  function confirmApprove() {
    if (!selectedProposal) return;
    Alert.alert('Approve proposal?', 'This creates a ready command only. Formal writes remain blocked.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Approve',
        style: 'default',
        onPress: async () => {
          setLoading(true);
          setError(null);
          try {
            const decision = await approveAgentProposal(selectedProposal.id, 'Approved in mobile review UI.');
            setSelectedProposal(decision.proposal);
            if (decision.command) {
              setSelectedCommand(decision.command);
            }
            await refresh();
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Approve failed.');
          } finally {
            setLoading(false);
          }
        },
      },
    ]);
  }

  function confirmReject() {
    if (!selectedProposal) return;
    Alert.alert('Reject proposal?', 'Rejected proposals cannot be approved later.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Reject',
        style: 'destructive',
        onPress: async () => {
          setLoading(true);
          setError(null);
          try {
            const decision = await rejectAgentProposal(selectedProposal.id, 'Rejected in mobile review UI.');
            setSelectedProposal(decision.proposal);
            setSelectedCommand(null);
            await refresh();
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Reject failed.');
          } finally {
            setLoading(false);
          }
        },
      },
    ]);
  }

  async function runDryRun() {
    const command = selectedReadyCommand;
    if (!command) return;
    setLoading(true);
    setError(null);
    try {
      const result = await dryRunAgentCommand(command.id);
      setDryRunResult(result);
      setSelectedCommand(result.command);
      await loadAudits(command.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Dry-run failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.title}>Agent Review</Text>
          <Text style={styles.subtitle}>Human confirmation and dry-run sandbox</Text>
        </View>
        <Pressable style={styles.refreshButton} onPress={refresh} disabled={loading}>
          <Text style={styles.refreshText}>Refresh</Text>
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.statusTabs}>
        {proposalStatuses.map((item) => (
          <Pressable
            key={item}
            style={[styles.statusTab, status === item ? styles.statusTabActive : null]}
            onPress={() => {
              setStatus(item);
              setSelectedProposal(null);
              setSelectedCommand(null);
              setDryRunResult(null);
            }}
          >
            <Text style={[styles.statusTabText, status === item ? styles.statusTabTextActive : null]}>{item}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {loading ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator color="#6657ff" />
          <Text style={styles.loadingText}>Loading</Text>
        </View>
      ) : null}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Pending Proposals</Text>
        {proposals.length === 0 ? <Text style={styles.emptyText}>No proposals in this state.</Text> : null}
        {proposals.map((proposal) => {
          const active = selectedProposal?.id === proposal.id;
          return (
            <Pressable
              key={proposal.id}
              style={[styles.proposalRow, active ? styles.proposalRowActive : null]}
              onPress={() => {
                setSelectedProposal(proposal);
                setSelectedCommand(commands.find((command) => command.proposal_id === proposal.id) || null);
                setDryRunResult(null);
              }}
            >
              <View style={styles.rowTop}>
                <Text style={styles.proposalTitle}>{proposal.title || proposal.id}</Text>
                <Text style={[styles.badge, styles[`badge_${statusTone(proposal.status)}`]]}>{proposal.status}</Text>
              </View>
              <Text style={styles.metaText}>
                {proposal.target_object_type} / {proposal.target_object_id || 'new object'}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {selectedProposal ? (
        <View style={styles.section}>
          <View style={styles.rowTop}>
            <Text style={styles.sectionTitle}>Proposal Detail</Text>
            <Text style={[styles.badge, styles[`badge_${statusTone(selectedProposal.risk_level)}`]]}>
              risk: {selectedProposal.risk_level}
            </Text>
          </View>
          <Field label="Target object" value={`${selectedProposal.target_object_type} / ${selectedProposal.target_object_id || 'new object'}`} />
          <Field label="Current status" value={selectedProposal.status} />
          <Field label="Suggested changes" value={formatJson(selectedProposal.proposed_changes)} mono />
          <Field label="Evidence" value={formatJson(selectedProposal.evidence)} mono />
          <Field label="Confidence" value={selectedProposal.confidence === null ? '-' : String(selectedProposal.confidence)} />
          <Field label="Requires confirmation" value={selectedProposal.requires_confirmation ? 'yes' : 'no'} />
          <Field label="Version / stale state" value={selectedProposal.expected_object_version || 'new object or unavailable'} />
          <Field label="Reason" value={selectedProposal.reason || '-'} />

          <View style={styles.actionRow}>
            <Pressable
              style={[styles.actionButton, styles.approveButton]}
              onPress={confirmApprove}
              disabled={selectedProposal.status !== 'pending' || loading}
            >
              <Text style={styles.actionText}>Approve</Text>
            </Pressable>
            <Pressable
              style={[styles.actionButton, styles.rejectButton]}
              onPress={confirmReject}
              disabled={selectedProposal.status !== 'pending' || loading}
            >
              <Text style={styles.actionText}>Reject</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Ready Commands</Text>
        {commands.length === 0 ? <Text style={styles.emptyText}>No ready command.</Text> : null}
        {commands.map((command) => {
          const active = selectedReadyCommand?.id === command.id;
          return (
            <Pressable
              key={command.id}
              style={[styles.commandRow, active ? styles.proposalRowActive : null]}
              onPress={() => {
                setSelectedCommand(command);
                loadAudits(command.id);
              }}
            >
              <Text style={styles.proposalTitle}>{command.operation} {command.target_object_type}</Text>
              <Text style={styles.metaText}>{command.target_object_id} / {command.status}</Text>
            </Pressable>
          );
        })}
        <Pressable
          style={[styles.dryRunButton, !selectedReadyCommand || loading ? styles.disabledButton : null]}
          onPress={runDryRun}
          disabled={!selectedReadyCommand || loading}
        >
          <Text style={styles.dryRunText}>Dry-run selected command</Text>
        </Pressable>
      </View>

      {dryRunResult ? (
        <View style={styles.section}>
          <View style={styles.rowTop}>
            <Text style={styles.sectionTitle}>Execution Result</Text>
            <Text style={[styles.badge, styles[`badge_${statusTone(dryRunResult.status)}`]]}>{dryRunResult.status}</Text>
          </View>
          <Field label="Expected changes" value={formatJson(dryRunResult.expected_changes)} mono />
          <Field label="Rollback preview" value={formatJson(dryRunResult.rollback_preview)} mono />
          <Field label="Authoritative state" value={formatJson(dryRunResult.authoritative_state)} mono />
          <Field label="Writes performed" value={dryRunResult.writes_performed ? 'yes' : 'no'} />
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Audit Records</Text>
        {audits.length === 0 ? <Text style={styles.emptyText}>No audit for the selected command.</Text> : null}
        {audits.map((audit) => (
          <View key={audit.id} style={styles.auditRow}>
            <View style={styles.rowTop}>
              <Text style={styles.proposalTitle}>{audit.result}</Text>
              <Text style={styles.metaText}>{audit.created_at}</Text>
            </View>
            <Field label="Reasons" value={audit.reasons.length ? audit.reasons.join(', ') : '-'} />
            <Field label="Rollback" value={formatJson(audit.audit_context?.rollback_preview)} mono />
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={[styles.fieldValue, mono ? styles.mono : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    gap: 14,
    padding: 16,
    paddingBottom: 96,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  title: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '900',
  },
  subtitle: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '700',
    marginTop: 4,
  },
  refreshButton: {
    backgroundColor: '#111827',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  refreshText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '900',
  },
  statusTabs: {
    gap: 8,
    paddingVertical: 2,
  },
  statusTab: {
    backgroundColor: '#ffffff',
    borderColor: '#e5e7eb',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  statusTabActive: {
    backgroundColor: '#111827',
    borderColor: '#111827',
  },
  statusTabText: {
    color: '#4b5563',
    fontSize: 12,
    fontWeight: '900',
  },
  statusTabTextActive: {
    color: '#ffffff',
  },
  loadingRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  loadingText: {
    color: '#4b5563',
    fontWeight: '800',
  },
  errorText: {
    backgroundColor: '#fef2f2',
    borderColor: '#fecaca',
    borderRadius: 8,
    borderWidth: 1,
    color: '#991b1b',
    fontSize: 12,
    fontWeight: '800',
    padding: 10,
  },
  section: {
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
    padding: 12,
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  emptyText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '700',
  },
  proposalRow: {
    borderColor: '#eef0f6',
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
    padding: 10,
  },
  proposalRowActive: {
    borderColor: '#6657ff',
    backgroundColor: '#f7f6ff',
  },
  commandRow: {
    borderColor: '#eef0f6',
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
    padding: 10,
  },
  auditRow: {
    borderTopColor: '#eef0f6',
    borderTopWidth: 1,
    gap: 8,
    paddingTop: 10,
  },
  rowTop: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  proposalTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 13,
    fontWeight: '900',
  },
  metaText: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
  },
  badge: {
    borderRadius: 999,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badge_neutral: {
    backgroundColor: '#f3f4f6',
    color: '#4b5563',
  },
  badge_good: {
    backgroundColor: '#ecfdf5',
    color: '#047857',
  },
  badge_bad: {
    backgroundColor: '#fef2f2',
    color: '#b91c1c',
  },
  badge_warn: {
    backgroundColor: '#fffbeb',
    color: '#b45309',
  },
  field: {
    gap: 4,
  },
  fieldLabel: {
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  fieldValue: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 19,
  },
  mono: {
    backgroundColor: '#f9fafb',
    borderRadius: 6,
    color: '#374151',
    fontFamily: 'Courier',
    fontSize: 11,
    padding: 8,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionButton: {
    alignItems: 'center',
    borderRadius: 8,
    flex: 1,
    paddingVertical: 11,
  },
  approveButton: {
    backgroundColor: '#059669',
  },
  rejectButton: {
    backgroundColor: '#dc2626',
  },
  actionText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
  },
  dryRunButton: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 8,
    paddingVertical: 12,
  },
  disabledButton: {
    opacity: 0.45,
  },
  dryRunText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '900',
  },
});
