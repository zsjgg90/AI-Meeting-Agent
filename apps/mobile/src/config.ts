export const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8002';

export const featureFlags = {
  enableAiAssistantUi: process.env.EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI === 'true',
  enableKnowledgeBaseUi: process.env.EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI !== 'false',
};
