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

## Screens

- Home: meeting list and create entry
- New meeting: enter a meeting name and create it through the API
- Recording: start, pause, resume, end, and upload audio with `expo-av`
- Knowledge Base: enterprise meeting knowledge home, categorized lists, keyword search, filters, and source meeting traceability. Full RAG question answering is not implemented in this stage.
- Meeting detail: transcript, AI summary, decisions, risks, and action items. Summary dimensions render through the shared `NumberedList` component for agenda, conclusions, unresolved issues, follow-up actions, and risks. Packed strings such as `1. A；2. B` are normalized into independent rows before rendering.
