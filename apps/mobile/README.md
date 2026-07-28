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
The default bottom navigation exposes Knowledge Base instead of AI Assistant.
The AI Assistant entry can be restored later by setting
`EXPO_PUBLIC_ENABLE_AI_ASSISTANT_UI=true`.

## Screens

- Home: MeetMind AI brand header, search entry, real-time recording entry, audio import entry, and a full-page scrollable meeting list from real API data. Completed cards preview the first agenda, conclusion, and action task from canonical six-dimension fields with legacy fallback.
- New meeting: enter a meeting name and create it through the API
- Recording: start, pause, resume, end, and upload audio with `expo-av`
- Import meeting: pick a local audio file with `expo-document-picker`, create a meeting through the API, and reuse the existing upload/process/analyze screen.
- Knowledge Base: enterprise meeting knowledge home, categorized lists, keyword search, filters, and source meeting traceability. Full RAG question answering is not implemented in this stage.
- Meeting detail: defaults to the rebuilt meeting transcript page with an inline `expo-av` audio player, draggable progress, centered 15-second seek controls, timestamp seek, bounded transcript-segment playback, transcript quick look, transcript export entry, and a FlatList timeline from real `transcript_segments`. The AI summary tab reuses the same top nav, player, and tab bar, then displays real meeting metadata, summary export buttons for `summary` MD/PDF/DOCX/TXT, basic info, canonical six-dimension fields with legacy fallback, read-only action item status, and available evidence/time anchors. Agent tools are a placeholder in this stage.
