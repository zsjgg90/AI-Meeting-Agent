import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CartoonAvatar } from '../components/CartoonAvatar';
import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

type Props = {
  onEditProfile: () => void;
  onHelpFeedback: () => void;
  onAbout: () => void;
  onSettings: () => void;
};

type MenuItem = {
  title: string;
  subtitle: string;
  icon: LucideIconName;
  onPress: () => void;
};

function ProfileMenuRow({ item, isLast }: { item: MenuItem; isLast: boolean }) {
  return (
    <Pressable onPress={item.onPress} style={[styles.menuRow, !isLast ? styles.menuDivider : null]}>
      <View style={styles.menuIcon}>
        <LucideIcon name={item.icon} color="#6c4dff" size={22} strokeWidth={2} />
      </View>
      <View style={styles.menuText}>
        <Text style={styles.menuTitle}>{item.title}</Text>
        <Text style={styles.menuSub}>{item.subtitle}</Text>
      </View>
      <LucideIcon name="chevron-right" color="#9ca3af" size={20} strokeWidth={2} />
    </Pressable>
  );
}

export function ProfileScreen({ onEditProfile, onHelpFeedback, onAbout, onSettings }: Props) {
  const menuItems: MenuItem[] = [
    {
      title: '帮助与反馈',
      subtitle: '查看帮助或反馈你的问题',
      icon: 'circle-help',
      onPress: onHelpFeedback,
    },
    {
      title: '关于 MeetMind AI',
      subtitle: '了解产品信息和版本更新',
      icon: 'info',
      onPress: onAbout,
    },
    {
      title: '设置',
      subtitle: '账号、通知和更多设置',
      icon: 'settings',
      onPress: onSettings,
    },
  ];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <Text style={styles.title}>我的</Text>

      <Pressable onPress={onEditProfile} style={styles.profileCard}>
        <View style={styles.avatarShell}>
          <CartoonAvatar size={72} />
        </View>
        <View style={styles.profileText}>
          <Text style={styles.name}>张明</Text>
          <Text style={styles.phone}>138 **** 5678</Text>
        </View>
        <View style={styles.editWrap}>
          <Text style={styles.editText}>编辑资料</Text>
          <LucideIcon name="chevron-right" color="#6c4dff" size={17} strokeWidth={2.2} />
        </View>
      </Pressable>

      <Text style={styles.sectionTitle}>支持与设置</Text>
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
    paddingBottom: 28,
    paddingHorizontal: 18,
    paddingTop: 22,
  },
  title: {
    color: '#111827',
    fontSize: 24,
    fontWeight: '900',
    letterSpacing: 0,
    marginBottom: 22,
    textAlign: 'center',
  },
  profileCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 26,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 14,
    marginBottom: 28,
    minHeight: 132,
    padding: 18,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.09,
    shadowRadius: 28,
    elevation: 5,
  },
  avatarShell: {
    borderColor: '#eee9ff',
    borderRadius: 42,
    borderWidth: 4,
    overflow: 'hidden',
  },
  profileText: {
    flex: 1,
    gap: 6,
  },
  name: {
    color: '#111827',
    fontSize: 21,
    fontWeight: '900',
  },
  phone: {
    color: '#7b8496',
    fontSize: 13,
    fontWeight: '800',
  },
  editWrap: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 2,
    zIndex: 1,
  },
  editText: {
    color: '#6c4dff',
    fontSize: 13,
    fontWeight: '900',
  },
  sectionTitle: {
    color: '#8b95a7',
    fontSize: 14,
    fontWeight: '900',
    marginBottom: 12,
  },
  menuGroup: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 24,
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.07,
    shadowRadius: 24,
    elevation: 4,
  },
  menuRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
    minHeight: 82,
    paddingHorizontal: 16,
  },
  menuDivider: {
    borderBottomColor: '#eef0f6',
    borderBottomWidth: 1,
  },
  menuIcon: {
    alignItems: 'center',
    backgroundColor: '#f0edff',
    borderRadius: 23,
    height: 46,
    justifyContent: 'center',
    width: 46,
  },
  menuText: {
    flex: 1,
    gap: 4,
  },
  menuTitle: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  menuSub: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '700',
  },
});
