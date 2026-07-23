import { Pressable, StyleSheet, Text, View } from 'react-native';

import { LucideIcon } from './LucideIcon';

type Props = {
  title: string;
  text: string;
  actionText?: string;
  onAction?: () => void;
};

export function KnowledgeEmptyState({ title, text, actionText, onAction }: Props) {
  return (
    <View style={styles.panel}>
      <View style={styles.icon}>
        <LucideIcon name="file-text" color="#8b95a7" size={30} strokeWidth={2.2} />
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.text}>{text}</Text>
      {actionText && onAction ? (
        <Pressable onPress={onAction} style={styles.button}>
          <Text style={styles.buttonText}>{actionText}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#edf0f7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 10,
    justifyContent: 'center',
    minHeight: 220,
    padding: 22,
  },
  icon: {
    alignItems: 'center',
    backgroundColor: '#f3f4f6',
    borderRadius: 14,
    height: 58,
    justifyContent: 'center',
    width: 58,
  },
  title: { color: '#111827', fontSize: 17, fontWeight: '900' },
  text: { color: '#8b95a7', fontSize: 13, fontWeight: '700', lineHeight: 20, textAlign: 'center' },
  button: {
    backgroundColor: '#6657ff',
    borderRadius: 14,
    marginTop: 4,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  buttonText: { color: '#ffffff', fontSize: 13, fontWeight: '900' },
});
