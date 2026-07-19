import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { CartoonAvatar } from '../components/CartoonAvatar';
import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

function InfoRow({
  label,
  value,
  icon,
  editable = false,
  isLast = false,
}: {
  label: string;
  value: string;
  icon: LucideIconName;
  editable?: boolean;
  isLast?: boolean;
}) {
  return (
    <View style={[styles.row, !isLast ? styles.rowDivider : null]}>
      <View style={styles.rowIcon}>
        <LucideIcon name={icon} color="#6c4dff" size={18} strokeWidth={2} />
      </View>
      <Text style={styles.label}>{label}</Text>
      {editable ? (
        <TextInput value={value} style={styles.input} />
      ) : (
        <Text style={styles.value}>{value}</Text>
      )}
    </View>
  );
}

export function EditProfileScreen() {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.avatarSection}>
        <Pressable
          onPress={() => Alert.alert('提示', '头像上传功能将在后续版本开放。')}
          style={styles.avatarWrap}
        >
          <View style={styles.avatarRing}>
            <CartoonAvatar size={112} />
          </View>
          <View style={styles.cameraButton}>
            <LucideIcon name="camera" color="#ffffff" size={18} strokeWidth={2.2} />
          </View>
        </Pressable>
        <Text style={styles.avatarTip}>点击头像更换</Text>
      </View>

      <View style={styles.formCard}>
        <InfoRow label="用户名" value="张明" icon="user-round" editable />
        <InfoRow label="手机号" value="138 **** 5678" icon="phone" isLast />
      </View>

      <Text style={styles.helper}>手机号用于登录和接收重要通知</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    paddingBottom: 32,
    paddingHorizontal: 18,
    paddingTop: 24,
  },
  avatarSection: {
    alignItems: 'center',
    gap: 12,
    marginBottom: 28,
  },
  avatarWrap: {
    position: 'relative',
  },
  avatarRing: {
    borderColor: '#ddd6ff',
    borderRadius: 66,
    borderWidth: 6,
    overflow: 'hidden',
    shadowColor: '#6c4dff',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.12,
    shadowRadius: 22,
  },
  cameraButton: {
    alignItems: 'center',
    backgroundColor: '#6c4dff',
    borderColor: '#ffffff',
    borderRadius: 20,
    borderWidth: 3,
    bottom: 2,
    height: 40,
    justifyContent: 'center',
    position: 'absolute',
    right: 2,
    width: 40,
  },
  avatarTip: {
    color: '#8b95a7',
    fontSize: 13,
    fontWeight: '800',
  },
  formCard: {
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
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    minHeight: 66,
    paddingHorizontal: 16,
  },
  rowDivider: {
    borderBottomColor: '#eef0f6',
    borderBottomWidth: 1,
  },
  rowIcon: {
    alignItems: 'center',
    backgroundColor: '#f0edff',
    borderRadius: 16,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  label: {
    color: '#111827',
    flex: 1,
    fontSize: 15,
    fontWeight: '900',
  },
  input: {
    color: '#4b5563',
    flex: 1,
    fontSize: 15,
    fontWeight: '800',
    minHeight: 48,
    padding: 0,
    textAlign: 'right',
  },
  value: {
    color: '#4b5563',
    fontSize: 15,
    fontWeight: '800',
  },
  helper: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 18,
  },
});
