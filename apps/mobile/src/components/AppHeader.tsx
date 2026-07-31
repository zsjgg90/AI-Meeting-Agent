import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LucideIcon } from './LucideIcon';

type Props = {
  title: string;
  canGoBack: boolean;
  onBack: () => void;
  rightText?: string;
  onRightPress?: () => void;
  accentColor?: string;
};

export function AppHeader({ title, canGoBack, onBack, rightText, onRightPress, accentColor }: Props) {
  const nextAccentColor = accentColor || '#111827';
  return (
    <View style={styles.header}>
      {canGoBack ? (
        <Pressable onPress={onBack} style={styles.backButton}>
          <LucideIcon name="chevron-left" color={nextAccentColor} size={22} strokeWidth={2.2} />
        </Pressable>
      ) : (
        <View style={styles.backButtonPlaceholder} />
      )}
      <View style={styles.titleWrap}>
        <Text style={[styles.title, accentColor ? { color: accentColor } : null]}>{title}</Text>
      </View>
      {rightText ? (
        <Pressable onPress={onRightPress} style={styles.rightButton}>
          <Text style={[styles.rightText, accentColor ? { color: accentColor } : null]}>{rightText}</Text>
        </Pressable>
      ) : (
        <View style={styles.backButtonPlaceholder} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    alignItems: 'center',
    backgroundColor: '#f6f7fb',
    flexDirection: 'row',
    minHeight: 58,
    paddingHorizontal: 16,
    paddingVertical: 9,
  },
  backButton: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 20,
    borderWidth: 1,
    height: 40,
    justifyContent: 'center',
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    width: 40,
  },
  backButtonPlaceholder: {
    height: 40,
    width: 40,
  },
  titleWrap: {
    flex: 1,
  },
  title: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  rightButton: {
    alignItems: 'center',
    minHeight: 40,
    justifyContent: 'center',
    minWidth: 40,
  },
  rightText: {
    color: '#2B6CFF',
    fontSize: 14,
    fontWeight: '900',
  },
});
