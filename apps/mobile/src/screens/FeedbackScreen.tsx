import { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { submitFeedback } from '../api';
import { LucideIcon } from '../components/LucideIcon';

type Props = {
  registerSubmit?: (handler: () => void) => void;
  onSubmitted?: () => void;
};

const feedbackTypes = ['功能建议', '问题反馈', '体验优化', '账号与数据', '其他'];

export function FeedbackScreen({ registerSubmit, onSubmitted }: Props) {
  const [feedbackType, setFeedbackType] = useState('');
  const [description, setDescription] = useState('');
  const [contact, setContact] = useState('');
  const [typeOpen, setTypeOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = useCallback(async () => {
    if (submitting) return;
    if (!feedbackType) {
      Alert.alert('请选择反馈类型');
      return;
    }
    if (!description.trim()) {
      Alert.alert('请填写问题描述');
      return;
    }

    try {
      setSubmitting(true);
      await submitFeedback({
        feedback_type: feedbackType,
        description: description.trim(),
        contact: contact.trim() || null,
        image_urls: [],
      });
      Alert.alert('提交成功', '感谢你的反馈，我们会持续改进产品体验。');
      setFeedbackType('');
      setDescription('');
      setContact('');
      onSubmitted?.();
    } catch (error) {
      Alert.alert('提交失败', error instanceof Error ? error.message : '请稍后重试');
    } finally {
      setSubmitting(false);
    }
  }, [contact, description, feedbackType, onSubmitted, submitting]);

  useEffect(() => {
    registerSubmit?.(handleSubmit);
  }, [handleSubmit, registerSubmit]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.card}>
        <Text style={styles.label}>反馈类型</Text>
        <Pressable onPress={() => setTypeOpen((value) => !value)} style={styles.select}>
          <Text style={[styles.placeholder, feedbackType ? styles.selectText : null]}>
            {feedbackType || '请选择反馈类型'}
          </Text>
          <LucideIcon name="chevron-right" color="#9ca3af" size={18} strokeWidth={2.2} />
        </Pressable>
        {typeOpen ? (
          <View style={styles.typeList}>
            {feedbackTypes.map((item) => (
              <Pressable
                key={item}
                onPress={() => {
                  setFeedbackType(item);
                  setTypeOpen(false);
                }}
                style={[styles.typeOption, feedbackType === item ? styles.typeOptionActive : null]}
              >
                <Text style={[styles.typeOptionText, feedbackType === item ? styles.typeOptionTextActive : null]}>
                  {item}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>问题描述</Text>
        <TextInput
          multiline
          maxLength={500}
          placeholder="请详细描述你遇到的问题或建议..."
          placeholderTextColor="#c0c5d2"
          value={description}
          onChangeText={setDescription}
          style={styles.textarea}
          textAlignVertical="top"
        />
        <Text style={styles.counter}>{description.length}/500</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>联系方式（选填）</Text>
        <TextInput
          placeholder="请输入手机号或邮箱，方便我们联系你"
          placeholderTextColor="#c0c5d2"
          value={contact}
          onChangeText={setContact}
          style={styles.input}
        />
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>上传图片（选填）</Text>
        <Pressable
          onPress={() => Alert.alert('提示', '图片上传功能将在后续版本开放。')}
          style={styles.uploadBox}
        >
          <LucideIcon name="image-plus" color="#8b95a7" size={25} strokeWidth={1.9} />
          <Text style={styles.uploadText}>添加图片</Text>
        </Pressable>
      </View>

      <Text style={styles.footer}>感谢你的反馈，我们会不断改进产品体验！</Text>
      <Pressable disabled={submitting} onPress={handleSubmit} style={[styles.submitButton, submitting ? styles.submitButtonDisabled : null]}>
        <Text style={styles.submitText}>{submitting ? '提交中...' : '提交反馈'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    gap: 14,
    paddingBottom: 32,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#eef0f6',
    borderRadius: 22,
    borderWidth: 1,
    padding: 16,
    shadowColor: '#6b7280',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.06,
    shadowRadius: 22,
    elevation: 3,
  },
  label: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '900',
    marginBottom: 12,
  },
  select: {
    alignItems: 'center',
    flexDirection: 'row',
    minHeight: 30,
  },
  placeholder: {
    color: '#b5bbc8',
    flex: 1,
    fontSize: 14,
    fontWeight: '700',
  },
  selectText: {
    color: '#111827',
    fontWeight: '900',
  },
  typeList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 14,
  },
  typeOption: {
    backgroundColor: '#f6f7fb',
    borderColor: '#eef0f6',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  typeOptionActive: {
    backgroundColor: '#eaf1ff',
    borderColor: '#bcd3ff',
  },
  typeOptionText: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '800',
  },
  typeOptionTextActive: {
    color: '#2B6CFF',
  },
  textarea: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '700',
    minHeight: 122,
    padding: 0,
  },
  counter: {
    color: '#9ca3af',
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'right',
  },
  input: {
    color: '#111827',
    fontSize: 14,
    fontWeight: '700',
    minHeight: 32,
    padding: 0,
  },
  uploadBox: {
    alignItems: 'center',
    borderColor: '#d8dbe6',
    borderRadius: 14,
    borderStyle: 'dashed',
    borderWidth: 1,
    gap: 7,
    height: 88,
    justifyContent: 'center',
    width: 88,
  },
  uploadText: {
    color: '#8b95a7',
    fontSize: 12,
    fontWeight: '800',
  },
  footer: {
    color: '#a1a8b7',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 6,
    textAlign: 'center',
  },
  submitButton: {
    alignItems: 'center',
    backgroundColor: '#2B6CFF',
    borderRadius: 16,
    minHeight: 50,
    justifyContent: 'center',
  },
  submitButtonDisabled: {
    opacity: 0.65,
  },
  submitText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '900',
  },
});
