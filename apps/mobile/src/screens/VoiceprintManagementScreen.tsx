import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

type Props = {
  onBack: () => void;
  onAddVoiceprint: () => void;
};

export function VoiceprintManagementScreen({ onBack, onAddVoiceprint }: Props) {
  const voiceprintEnabled = false;

  function showPendingApi() {
    Alert.alert('待接入接口', '当前版本还没有正式声纹注册和身份匹配接口，不能编辑或展示已录入声纹。');
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.headerButton}>
          <LucideIcon name="chevron-left" color="#111827" size={24} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.headerTitle}>声纹管理</Text>
        <Pressable onPress={onAddVoiceprint} hitSlop={10} style={styles.headerButton}>
          <LucideIcon name="plus" color="#111827" size={24} strokeWidth={2.3} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.switchCard}>
          <View style={styles.switchTopRow}>
            <View style={styles.switchTitleRow}>
              <View style={styles.switchIcon}>
                <LucideIcon name="mic" color="#2B6CFF" size={20} strokeWidth={2.2} />
              </View>
              <View>
                <Text style={styles.cardTitle}>声纹识别</Text>
                <Text style={styles.statusText}>未开放</Text>
              </View>
            </View>
            <Switch
              disabled
              value={voiceprintEnabled}
              trackColor={{ false: '#e5e7eb', true: '#2B6CFF' }}
              thumbColor="#ffffff"
            />
          </View>
          <Text style={styles.description}>开启后，系统自动识别并标注不同说话人</Text>
        </View>

        <View style={styles.listCard}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>已录入声纹</Text>
            <Text style={styles.sectionStatus}>待接入接口</Text>
          </View>
          <View style={styles.emptyState}>
            <View style={styles.emptyAvatar}>
              <LucideIcon name="user-round" color="#8b95a7" size={26} strokeWidth={2.1} />
            </View>
            <Text style={styles.emptyTitle}>暂无已录入声纹</Text>
            <Text style={styles.emptyText}>当前项目没有正式声纹样本接口，因此不展示原型中的示例用户，也不会伪造录入状态。</Text>
          </View>
        </View>

        <Pressable onPress={onAddVoiceprint} style={styles.addButton}>
          <LucideIcon name="mic" color="#ffffff" size={19} strokeWidth={2.4} />
          <Text style={styles.addButtonText}>录入声纹样本</Text>
        </Pressable>

        <Pressable onPress={showPendingApi} style={styles.pendingNote}>
          <Text style={styles.pendingTitle}>能力边界</Text>
          <Text style={styles.pendingText}>声纹录音仅用于未来 Speaker Diarization 身份辅助，不会进入会议转写、AI纪要或 Agent 分析流程。</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#f6f7fb',
    flex: 1,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 58,
    paddingHorizontal: 16,
    paddingVertical: 9,
  },
  headerButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  headerTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 0,
  },
  content: {
    paddingBottom: 32,
    paddingHorizontal: 16,
    paddingTop: 6,
  },
  switchCard: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    marginBottom: 14,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  switchTopRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  switchTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flex: 1,
    minWidth: 0,
  },
  switchIcon: {
    alignItems: 'center',
    backgroundColor: '#edf4ff',
    borderRadius: 18,
    height: 36,
    justifyContent: 'center',
    marginRight: 12,
    width: 36,
  },
  cardTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  statusText: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '800',
    marginTop: 3,
  },
  description: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 12,
  },
  listCard: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    marginBottom: 24,
    overflow: 'hidden',
    paddingHorizontal: 16,
    paddingTop: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  sectionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  sectionStatus: {
    backgroundColor: '#f3f4f6',
    borderRadius: 999,
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  emptyState: {
    alignItems: 'center',
    paddingBottom: 28,
    paddingHorizontal: 18,
    paddingTop: 28,
  },
  emptyAvatar: {
    alignItems: 'center',
    backgroundColor: '#f1f4f8',
    borderRadius: 26,
    height: 52,
    justifyContent: 'center',
    marginBottom: 12,
    width: 52,
  },
  emptyTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  emptyText: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 8,
    textAlign: 'center',
  },
  addButton: {
    alignItems: 'center',
    backgroundColor: '#2B6CFF',
    borderRadius: 14,
    flexDirection: 'row',
    gap: 7,
    justifyContent: 'center',
    minHeight: 50,
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 4,
  },
  addButtonText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
  },
  pendingNote: {
    backgroundColor: '#eef3ff',
    borderColor: '#dbe7ff',
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 16,
    padding: 14,
  },
  pendingTitle: {
    color: '#2B6CFF',
    fontSize: 13,
    fontWeight: '900',
  },
  pendingText: {
    color: '#4b5563',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
    marginTop: 6,
  },
});
