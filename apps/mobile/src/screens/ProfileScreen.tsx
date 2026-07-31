import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CartoonAvatar } from '../components/CartoonAvatar';
import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

type Props = {
  onEditProfile: () => void;
  onVoiceprintManagement: () => void;
  onPushConfig: () => void;
  onHelpFeedback: () => void;
  onAbout: () => void;
  onSettings: () => void;
};

type MenuItem = {
  title: string;
  icon: LucideIconName;
  onPress: () => void;
  accent?: boolean;
};

function showUnavailable(title: string) {
  Alert.alert(title, '当前版本暂未开放该功能。');
}

function ProfileMenuRow({ item, isLast }: { item: MenuItem; isLast: boolean }) {
  return (
    <Pressable onPress={item.onPress} style={[styles.menuRow, !isLast ? styles.menuDivider : null]}>
      <View style={styles.menuIcon}>
        <LucideIcon name={item.icon} color="#111827" size={22} strokeWidth={2.1} />
      </View>
      <Text style={styles.menuTitle}>{item.title}</Text>
      <LucideIcon name="chevron-right" color="#c4cad6" size={20} strokeWidth={2.1} />
    </Pressable>
  );
}

export function ProfileScreen({ onEditProfile, onVoiceprintManagement, onPushConfig, onHelpFeedback, onAbout, onSettings }: Props) {
  const menuItems: MenuItem[] = [
    { title: '我的记忆', icon: 'book-open', onPress: () => showUnavailable('我的记忆') },
    { title: '声纹管理', icon: 'mic', onPress: onVoiceprintManagement },
    { title: '推送配置', icon: 'bell', onPress: onPushConfig },
    { title: '帮助与反馈', icon: 'message-square', onPress: onHelpFeedback },
    { title: '关于 MeetMind AI', icon: 'info', onPress: onAbout },
  ];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.header}>
        <View style={styles.headerSpacer} />
        <Text style={styles.title}>我的</Text>
        <Pressable onPress={onSettings} hitSlop={10} style={styles.settingsButton}>
          <LucideIcon name="settings" color="#111827" size={24} strokeWidth={2.2} />
        </Pressable>
      </View>

      <Pressable onPress={onEditProfile} style={styles.profileCard}>
        <View style={styles.avatarShell}>
          <CartoonAvatar size={64} />
        </View>
        <View style={styles.profileText}>
          <Text style={styles.name}>张明</Text>
          <Text style={styles.phone}>186****2042</Text>
        </View>
      </Pressable>

      <View style={styles.menuGroup}>
        {menuItems.map((item, index) => (
          <ProfileMenuRow key={item.title} item={item} isLast={index === menuItems.length - 1} />
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingBottom: 126,
    paddingHorizontal: 16,
    paddingTop: 14,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 54,
    marginBottom: 10,
  },
  headerSpacer: {
    width: 40,
  },
  title: {
    color: '#111827',
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: 0,
    textAlign: 'center',
  },
  settingsButton: {
    alignItems: 'center',
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  profileCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 18,
    flexDirection: 'row',
    gap: 16,
    marginBottom: 24,
    minHeight: 96,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.07,
    shadowRadius: 18,
    elevation: 3,
  },
  avatarShell: {
    backgroundColor: '#f2f4f8',
    borderRadius: 32,
    height: 64,
    overflow: 'hidden',
    width: 64,
  },
  profileText: {
    flex: 1,
    gap: 6,
  },
  name: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
  },
  phone: {
    color: '#9ca3af',
    fontSize: 13,
    fontWeight: '800',
  },
  menuGroup: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    overflow: 'hidden',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 18,
    elevation: 3,
  },
  menuRow: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 56,
    paddingHorizontal: 16,
  },
  menuDivider: {
    borderBottomColor: '#f1f3f7',
    borderBottomWidth: 1,
  },
  menuIcon: {
    alignItems: 'center',
    height: 28,
    justifyContent: 'center',
    marginRight: 12,
    width: 28,
  },
  menuTitle: {
    color: '#111827',
    flex: 1,
    fontSize: 15,
    fontWeight: '800',
  },
});
