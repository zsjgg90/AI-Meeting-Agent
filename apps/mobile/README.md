# Meeting Agent Mobile

Expo React Native app for the meeting MVP.

## Setup

```bash
cp .env.example .env
npm install
npx expo start
```

Configure the API base URL in `.env`:

```env
EXPO_PUBLIC_API_BASE_URL=http://YOUR_LAN_IP:8002
EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=false
EXPO_PUBLIC_ENABLE_KNOWLEDGE_BASE_UI=true
```

For Expo Go on a physical phone, use the computer LAN IP instead of `localhost` or `127.0.0.1`. The local API startup script serves on port `8002`.
The default bottom navigation is `首页 | 知识库 | 麦克风 | 待办 | 我的`.
The center microphone is only an entry into the existing realtime recording
flow; it does not introduce a second recorder state or screen. The AI Assistant
screens remain hidden unless explicitly re-enabled by configuration and are no
longer part of the default bottom tab bar.

## Screens

- Home: MeetMind AI brand header, search entry, real-time recording entry, audio import entry, and a full-page scrollable meeting list from real API data. Completed cards preview the first agenda, conclusion, and action task from canonical six-dimension fields with legacy fallback.
- New meeting: enter a meeting name and create it through the API
- Recording: the home recording action and BottomNav center microphone create the fallback-titled meeting through the API, expand the shared overlay, and start the existing `expo-av` recorder. Expanded/collapsed overlay, mini player, pause/resume, end, and background upload/process/analyze all reuse the existing global recording session.
- Voiceprint management: the Profile `声纹管理` entry opens an independent React Native voiceprint page with a disabled unavailable recognition switch, truthful empty state, and an add-sample entry. The add-sample page uses a separate page-local `Audio.Recording` instance for voice sample capture only. Because no formal voiceprint API exists yet, saving reports `待接入接口` and does not upload, register, identify, or create fake users.
- Push config: the Profile `推送配置` entry opens a React Native push configuration page for Feishu, email, and SMS channels. Because no formal Feishu, email, SMS, push-config, or push-history API exists yet, the switches stay disabled/off and the page shows `未配置`, `暂未开放`, and `待接入` instead of fake connection or delivery success.
- Import meeting: pick a local audio file with `expo-document-picker`, create a meeting through the API, and reuse the existing upload/process/analyze screen.
- Knowledge Base: enterprise meeting knowledge home, categorized lists, keyword search, filters, and source meeting traceability. Full RAG question answering is not implemented in this stage.
- Todo: rebuilt `我的待办` home backed by the `/tasks` API with real task pagination, pull-to-refresh, priority/deadline display, and real checkbox completion through `PATCH /tasks/{task_id}/status`. The Todo search button opens an independent task search page that reuses `GET /tasks?q=...` fuzzy Chinese/English keyword search, waits for keyboard search submission before requesting results, and stores only recent keywords locally with AsyncStorage. Tapping a Todo or search result card opens the independent task detail overlay with real task fields, square checkbox completion, source meeting lookup, missing-field fallbacks, persisted title/description/owner/due-date/priority/reminder edits through `PATCH /tasks/{task_id}`, server-side task attachments through `POST /tasks/{task_id}/attachments`, and no bottom navigation.
- Meeting detail: defaults to the rebuilt meeting transcript page with an inline `expo-av` audio player, draggable progress, centered 15-second seek controls, timestamp seek, bounded transcript-segment playback, transcript quick look, transcript export entry, and a FlatList timeline from real `transcript_segments`. The AI summary tab reuses the same top nav, player, and tab bar, then displays real meeting metadata, summary export buttons for `summary` MD/PDF/DOCX/TXT, basic info, canonical six-dimension fields with legacy fallback, read-only action item status, and available evidence/time anchors. Agent tools are a placeholder in this stage.
