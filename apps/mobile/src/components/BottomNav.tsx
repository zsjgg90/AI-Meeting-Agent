import { Pressable, StyleSheet, Text, View } from 'react-native';

import { featureFlags } from '../config';
import { LucideIcon, type LucideIconName } from './LucideIcon';

export type BottomTab = 'home' | 'knowledge' | 'ai' | 'todo' | 'me';

type Props = {
  active: BottomTab;
  onTabPress: (tab: BottomTab) => void;
};

const tabs: Array<{ key: BottomTab; label: string; icon: LucideIconName }> = [
  { key: 'home', label: '首页', icon: 'house' },
  featureFlags.enableAiAssistantUi
    ? { key: 'ai', label: 'AI 助手', icon: 'sparkles' }
    : { key: 'knowledge', label: '知识库', icon: 'book-open' },
  { key: 'todo', label: '待办', icon: 'square-check-big' },
  { key: 'me', label: '我的', icon: 'user-round' },
];

export function BottomNav({ active, onTabPress }: Props) {
  return (
    <View style={styles.nav}>
      {tabs.map((tab) => {
        const isActive = active === tab.key;
        const iconColor = isActive ? '#6657ff' : '#8b95a7';
        return (
          <Pressable key={tab.key} onPress={() => onTabPress(tab.key)} style={styles.item}>
            <View style={[styles.iconWrap, isActive ? styles.iconWrapActive : null]}>
              <LucideIcon name={tab.icon} color={iconColor} size={23} strokeWidth={2.1} />
            </View>
            <Text style={[styles.label, isActive ? styles.active : null]}>{tab.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  nav: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderTopColor: '#eef0f6',
    borderTopWidth: 1,
    flexDirection: 'row',
    minHeight: 74,
    paddingBottom: 10,
    paddingTop: 9,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.07,
    shadowRadius: 22,
    elevation: 10,
  },
  item: {
    alignItems: 'center',
    flex: 1,
    gap: 4,
    minHeight: 54,
    justifyContent: 'center',
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: 16,
    height: 32,
    justifyContent: 'center',
    width: 42,
  },
  iconWrapActive: {
    backgroundColor: '#f0efff',
  },
  label: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '900',
    includeFontPadding: false,
    lineHeight: 15,
  },
  active: {
    color: '#6657ff',
  },
});