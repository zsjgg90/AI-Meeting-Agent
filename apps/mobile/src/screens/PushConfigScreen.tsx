import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

type Props = {
  onBack: () => void;
};

type ChannelRow = {
  label: string;
  value: string;
  chevron?: boolean;
};

type ChannelCard = {
  title: string;
  description: string;
  icon: LucideIconName;
  iconColor: string;
  iconBackground: string;
  status: string;
  rows: ChannelRow[];
};

const channels: ChannelCard[] = [
  {
    title: '飞书推送',
    description: '连接后自动同步会议纪要和任务',
    icon: 'send',
    iconColor: '#2B6CFF',
    iconBackground: '#edf4ff',
    status: '未配置',
    rows: [
      { label: '推送内容', value: '会议纪要、任务', chevron: true },
      { label: '连接状态', value: '待接入' },
    ],
  },
  {
    title: '邮箱推送',
    description: '会议结束后推送结构化会议成果',
    icon: 'mail',
    iconColor: '#7c3aed',
    iconBackground: '#f4efff',
    status: '未配置',
    rows: [
      { label: '邮箱地址', value: '未配置', chevron: true },
      { label: '推送内容', value: '暂未开放' },
    ],
  },
  {
    title: '短信提醒',
    description: '只用于重要提醒，不发送普通纪要',
    icon: 'phone',
    iconColor: '#f97316',
    iconBackground: '#fff3e8',
    status: '未配置',
    rows: [
      { label: '手机号', value: '未配置', chevron: true },
      { label: '提醒内容', value: '高优先级任务、风险事项、截止提醒' },
    ],
  },
];

function showPendingCapability(title: string) {
  Alert.alert(title, '当前版本暂未接入真实推送接口，不能保存配置或执行发送。');
}

function ChannelCardView({ channel }: { channel: ChannelCard }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={[styles.iconBox, { backgroundColor: channel.iconBackground }]}>
          <LucideIcon name={channel.icon} color={channel.iconColor} size={22} strokeWidth={2.3} />
        </View>
        <View style={styles.channelTitleBlock}>
          <Text style={styles.channelTitle}>{channel.title}</Text>
          <Text style={styles.channelDescription}>{channel.description}</Text>
        </View>
        <View style={styles.switchBlock}>
          <Switch
            disabled
            value={false}
            trackColor={{ false: '#e5e7eb', true: '#2B6CFF' }}
            thumbColor="#ffffff"
          />
          <Text style={styles.statusText}>{channel.status}</Text>
        </View>
      </View>

      <View style={styles.divider} />

      {channel.rows.map((row, index) => (
        <Pressable
          key={`${channel.title}-${row.label}`}
          disabled={!row.chevron}
          onPress={() => showPendingCapability(row.label)}
          style={[styles.row, index < channel.rows.length - 1 ? styles.rowDivider : null]}
        >
          <Text style={styles.rowLabel}>{row.label}</Text>
          <Text style={styles.rowValue} numberOfLines={2}>
            {row.value}
          </Text>
          {row.chevron ? <LucideIcon name="chevron-right" color="#c4cad6" size={20} strokeWidth={2.1} /> : null}
        </Pressable>
      ))}
    </View>
  );
}

export function PushConfigScreen({ onBack }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.headerButton}>
          <LucideIcon name="chevron-left" color="#111827" size={24} strokeWidth={2.3} />
        </Pressable>
        <Text style={styles.headerTitle}>推送配置</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.subtitleRow}>
          <LucideIcon name="sparkles" color="#9ca3af" size={14} strokeWidth={2.1} />
          <Text style={styles.subtitle}>让 AI 自动分发会议纪要、任务和提醒</Text>
        </View>

        {channels.map((channel) => (
          <ChannelCardView key={channel.title} channel={channel} />
        ))}

        <View style={styles.boundaryNote}>
          <Text style={styles.boundaryTitle}>当前支持能力</Text>
          <Text style={styles.boundaryText}>本页仅展示推送渠道配置入口和待接入状态。</Text>
          <Text style={styles.boundaryTitle}>未开放能力</Text>
          <Text style={styles.boundaryText}>飞书连接、邮箱发送、短信发送、推送历史记录暂未开放。</Text>
        </View>
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
    paddingBottom: 126,
    paddingHorizontal: 16,
    paddingTop: 6,
  },
  subtitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'center',
    marginBottom: 22,
    marginTop: 2,
  },
  subtitle: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    marginBottom: 14,
    overflow: 'hidden',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  cardHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    paddingBottom: 12,
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  iconBox: {
    alignItems: 'center',
    borderRadius: 14,
    height: 42,
    justifyContent: 'center',
    marginRight: 12,
    width: 42,
  },
  channelTitleBlock: {
    flex: 1,
    minWidth: 0,
  },
  channelTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  channelDescription: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 4,
  },
  switchBlock: {
    alignItems: 'center',
    marginLeft: 10,
  },
  statusText: {
    color: '#9ca3af',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 2,
  },
  divider: {
    backgroundColor: '#f1f3f7',
    height: 1,
    marginHorizontal: 16,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 48,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  rowDivider: {
    borderBottomColor: '#f5f6fa',
    borderBottomWidth: 1,
  },
  rowLabel: {
    color: '#111827',
    flex: 1,
    fontSize: 15,
    fontWeight: '800',
  },
  rowValue: {
    color: '#8b95a7',
    flexShrink: 1,
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 18,
    marginLeft: 12,
    maxWidth: 190,
    textAlign: 'right',
  },
  boundaryNote: {
    backgroundColor: '#eef3ff',
    borderColor: '#dbe7ff',
    borderRadius: 16,
    borderWidth: 1,
    marginTop: 2,
    padding: 14,
  },
  boundaryTitle: {
    color: '#2B6CFF',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  boundaryText: {
    color: '#4b5563',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
    marginBottom: 8,
    marginTop: 5,
  },
});
