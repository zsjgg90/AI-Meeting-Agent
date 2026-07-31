import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CartoonAvatar } from '../components/CartoonAvatar';
import { LucideIcon, type LucideIconName } from '../components/LucideIcon';

type Props = {
  onFaq: () => void;
  onFeedback: () => void;
};

function HelpEntry({
  title,
  subtitle,
  onPress,
}: {
  title: string;
  subtitle: string;
  icon?: LucideIconName;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={styles.card}>
      <View style={styles.cardText}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardSub}>{subtitle}</Text>
      </View>
      <View style={styles.chevronCircle}>
        <LucideIcon name="chevron-right" color="#8b95a7" size={20} strokeWidth={2.2} />
      </View>
    </Pressable>
  );
}

export function HelpFeedbackScreen({ onFaq, onFeedback }: Props) {
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <View style={styles.illustrationGlow} />
        <View style={styles.avatarGroup}>
          <CartoonAvatar size={116} showQuestion />
          <View style={styles.questionBubble}>
            <Text style={styles.questionText}>?</Text>
          </View>
          <View style={[styles.star, styles.starOne]} />
          <View style={[styles.star, styles.starTwo]} />
        </View>
        <Text style={styles.heroTitle}>遇到问题？我们随时为你提供帮助</Text>
        <Text style={styles.heroText}>你可以查看常见问题，或向我们反馈你遇到的问题和建议</Text>
      </View>

      <View style={styles.list}>
        <HelpEntry title="常见问题" subtitle="查看使用帮助和常见问题" icon="circle-help" onPress={onFaq} />
        <HelpEntry title="意见反馈" subtitle="告诉我们你的问题或建议" icon="pencil-line" onPress={onFeedback} />
      </View>
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
    paddingTop: 18,
  },
  hero: {
    alignItems: 'center',
    marginBottom: 34,
    paddingHorizontal: 14,
    paddingTop: 16,
  },
  illustrationGlow: {
    backgroundColor: '#eaf1ff',
    borderRadius: 86,
    height: 172,
    position: 'absolute',
    top: 10,
    width: 172,
  },
  avatarGroup: {
    alignItems: 'center',
    height: 158,
    justifyContent: 'center',
    marginBottom: 22,
    width: 184,
  },
  questionBubble: {
    alignItems: 'center',
    backgroundColor: '#f7f8fc',
    borderRadius: 30,
    height: 60,
    justifyContent: 'center',
    position: 'absolute',
    right: 18,
    top: 24,
    width: 60,
  },
  questionText: {
    color: '#ffffff',
    fontSize: 34,
    fontWeight: '900',
  },
  star: {
    backgroundColor: '#8fb5ff',
    borderRadius: 999,
    height: 8,
    position: 'absolute',
    width: 8,
  },
  starOne: {
    left: 18,
    top: 42,
  },
  starTwo: {
    right: 6,
    top: 100,
  },
  heroTitle: {
    color: '#111827',
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 25,
    textAlign: 'center',
  },
  heroText: {
    color: '#7b8496',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 22,
    marginTop: 10,
    maxWidth: 260,
    textAlign: 'center',
  },
  list: {
    gap: 14,
  },
  card: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 14,
    minHeight: 86,
    overflow: 'hidden',
    paddingHorizontal: 18,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    elevation: 4,
  },
  cardText: {
    flex: 1,
    gap: 5,
  },
  cardTitle: {
    color: '#111827',
    fontSize: 16,
    fontWeight: '900',
  },
  cardSub: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '700',
  },
  chevronCircle: {
    alignItems: 'center',
    backgroundColor: '#f7f8fc',
    borderRadius: 20,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
});
