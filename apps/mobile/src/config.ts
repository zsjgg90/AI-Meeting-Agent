import Constants from 'expo-constants';
import { NativeModules } from 'react-native';

function normalizeDevHost(hostUri: string | null | undefined): string | null {
  if (!hostUri || typeof hostUri !== 'string') {
    return null;
  }

  try {
    const url = new URL(hostUri.includes('://') ? hostUri : `http://${hostUri}`);
    if (!url.hostname) {
      return null;
    }
    if (url.hostname.endsWith('.exp.direct')) {
      return `https://${url.host}/api-proxy`;
    }
    return `${url.protocol}//${url.host}/api-proxy`;
  } catch {
    return null;
  }
}

const expoConstants = Constants as any;
export const devScriptUrl =
  typeof NativeModules.SourceCode?.scriptURL === 'string' ? NativeModules.SourceCode.scriptURL : null;
export const devHostUri =
  expoConstants.expoConfig?.hostUri ||
  expoConstants.manifest2?.extra?.expoClient?.hostUri ||
  expoConstants.manifest?.debuggerHost ||
  expoConstants.manifest?.packagerOpts?.hostUri ||
  null;

function devServerApiBaseUrl(): string | null {
  return normalizeDevHost(devHostUri) || normalizeDevHost(devScriptUrl);
}

export const apiBaseUrl = devServerApiBaseUrl() || process.env.EXPO_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8002';

export const apiDebugInfo = {
  apiBaseUrl,
  devHostUri: devHostUri || null,
  devScriptUrl,
  envApiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL || null,
};

export const featureFlags = {
  enableAiAssistantUi: process.env.EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI === 'true',
  enableKnowledgeBaseUi: process.env.EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI !== 'false',
};
