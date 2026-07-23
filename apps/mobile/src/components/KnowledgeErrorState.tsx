import { Pressable, StyleSheet, Text, View } from 'react-native';

import { LucideIcon } from './LucideIcon';

type Props = {
  message: string;
  onRetry: () => void;
};

export function KnowledgeErrorState({ message, onRetry }: Props) {
  return (
    <View style={styles.panel}>
      <View style={styles.icon}>
        <LucideIcon name="triangle-alert" color="#ef4444" size={28} strokeWidth={2.2} />
      </View>
      <Text style={styles.title}>数据加载失败</Text>
      <Text style={styles.text}>{message}</Text>
      <Pressable onPress={onRetry} style={styles.button}>
        <LucideIcon name="rotate-ccw" color="#ffffff" size={15} strokeWidth={2.4} />
        <Text style={styles.buttonText}>重试</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#fee2e2',
    borderRadius: 18,
    borderWidth: 1,
    gap: 10,
    justifyContent: 'center',
    minHeight: 220,
    padding: 22,
  },
  icon: {
    alignItems: 'center',
    backgroundColor: '#fff1f2',
    borderRadius: 14,
    height: 58,
    justifyContent: 'center',
    width: 58,
  },
  title: { color: '#111827', fontSize: 17, fontWeight: '900' },
  text: { color: '#8b95a7', fontSize: 13, fontWeight: '700', lineHeight: 20, textAlign: 'center' },
  button: {
    alignItems: 'center',
    backgroundColor: '#6657ff',
    borderRadius: 14,
    flexDirection: 'row',
    gap: 6,
    marginTop: 4,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  buttonText: { color: '#ffffff', fontSize: 13, fontWeight: '900' },
});
