import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { LucideIcon } from '../components/LucideIcon';

export function SettingsScreen() {
  return (
    <View style={styles.container}>
      <Pressable
        onPress={() => Alert.alert('退出登录', '当前版本暂未接入登录系统。')}
        style={styles.logoutCard}
      >
        <View style={styles.logoutIcon}>
          <LucideIcon name="log-out" color="#ef4444" size={20} strokeWidth={2} />
        </View>
        <Text style={styles.logoutText}>退出登录</Text>
        <LucideIcon name="chevron-right" color="#9ca3af" size={20} strokeWidth={2.2} />
      </Pressable>

      <View style={styles.footer}>
        <Text style={styles.footerText}>退出后，将清除本地缓存信息</Text>
        <Text style={styles.footerText}>当前版本 v1.0.0</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 24,
  },
  logoutCard: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 72,
    paddingHorizontal: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.06,
    shadowRadius: 22,
    elevation: 3,
  },
  logoutIcon: {
    alignItems: 'center',
    backgroundColor: '#fff1f2',
    borderRadius: 17,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  logoutText: {
    color: '#ef4444',
    flex: 1,
    fontSize: 15,
    fontWeight: '900',
  },
  footer: {
    alignItems: 'center',
    gap: 7,
    marginTop: 'auto',
    paddingBottom: 34,
  },
  footerText: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '700',
  },
});
