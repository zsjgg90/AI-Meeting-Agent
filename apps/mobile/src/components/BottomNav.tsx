import { Pressable, StyleSheet, Text, View } from 'react-native';

import { LucideIcon, type LucideIconName } from './LucideIcon';

export type BottomTab = 'home' | 'knowledge' | 'recording' | 'todo' | 'me';

type Props = {
  active: BottomTab;
  onTabPress: (tab: BottomTab) => void;
};

const tabs: Array<{ key: BottomTab; label: string; icon: LucideIconName }> = [
  { key: 'home', label: '首页', icon: 'house' },
  { key: 'knowledge', label: '知识库', icon: 'book-open' },
  { key: 'recording', label: '麦克风', icon: 'mic' },
  { key: 'todo', label: '待办', icon: 'square-check-big' },
  { key: 'me', label: '我的', icon: 'user-round' },
];

export function BottomNav({ active, onTabPress }: Props) {
  return (
    <View style={styles.nav}>
      {tabs.map((tab) => {
        const isActive = active === tab.key;
        const isRecordingTab = tab.key === 'recording';
        const iconColor = isActive ? '#2B6CFF' : '#8b95a7';
        return (
          <Pressable
            key={tab.key}
            onPress={() => onTabPress(tab.key)}
            style={[styles.item, isRecordingTab ? styles.centerItem : null]}
          >
            <View style={[styles.iconWrap, isActive ? styles.iconWrapActive : null, isRecordingTab ? styles.centerButton : null]}>
              <LucideIcon
                name={tab.icon}
                color={isRecordingTab ? '#ffffff' : iconColor}
                size={isRecordingTab ? 29 : 23}
                strokeWidth={isRecordingTab ? 2.6 : 2.1}
              />
            </View>
            <Text style={[styles.label, isActive ? styles.active : null, isRecordingTab ? styles.centerLabel : null]}>
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  nav: {
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderTopColor: '#eef1f6',
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: 'row',
    left: 0,
    minHeight: 101,
    paddingBottom: 0,
    paddingTop: 8,
    position: 'absolute',
    right: 0,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    elevation: 12,
  },
  item: {
    alignItems: 'center',
    flex: 1,
    gap: 3,
    minHeight: 83,
    justifyContent: 'center',
    transform: [{ translateY: -8 }],
  },
  centerItem: {
    transform: [{ translateY: -22 }],
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: 18,
    height: 34,
    justifyContent: 'center',
    width: 46,
  },
  iconWrapActive: {
    backgroundColor: '#e8f0fe',
  },
  centerButton: {
    backgroundColor: '#2B6CFF',
    borderColor: '#ffffff',
    borderRadius: 32,
    borderWidth: 4,
    height: 62,
    shadowColor: '#2B6CFF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.22,
    shadowRadius: 18,
    width: 62,
    elevation: 8,
  },
  label: {
    color: '#8b95a7',
    fontSize: 11,
    fontWeight: '900',
    includeFontPadding: false,
    lineHeight: 15,
  },
  active: {
    color: '#2B6CFF',
  },
  centerLabel: {
    marginTop: -1,
  },
});
