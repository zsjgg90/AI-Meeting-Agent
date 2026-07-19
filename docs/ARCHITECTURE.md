# Architecture

## High-Level Flow

```text
Expo App
  -> API Service
  -> PostgreSQL
  -> Worker Service
  -> ASR Provider / local Whisper
  -> Speaker diarization / speaker label normalization
  -> TranscriptSegment persistence
  -> RAG retrieval
  -> Ollama qwen3:14b
  -> Anti-hallucination validator
  -> MeetingSummary + ActionItem persistence
  -> API read endpoints
  -> Expo display
```

## Module Ownership

### `apps/mobile`

Owns the user interface:

- Home
- New meeting
- Recording
- AI processing state
- Meeting detail
- Meeting history
- Todo
- Profile and support pages

It should call only API Service endpoints.

### `services/api`

Owns public HTTP contracts:

- Meeting CRUD
- Audio upload
- Process/analyze task trigger
- Transcript and summary reads
- Action item reads
- Speaker mapping updates
- Feedback persistence
- Export endpoints

It should not call Ollama or Chroma directly.

### `services/worker`

Owns heavy processing:

- Audio path resolution
- ASR provider selection
- Volcengine/Doubao ASR integration
- Local faster-whisper fallback
- Pyannote diarization fallback/agent stage
- Transcript persistence
- Qwen3 + RAG meeting analysis
- Validator enforcement
- Summary/action item persistence

### PostgreSQL

Core tables include:

- `meetings`
- `audio_files`
- `transcript_segments`
- `meeting_summaries`
- `action_items`
- `speaker_mappings`
- `meeting_chunks`
- `transcription_tasks`
- `user_feedbacks`

Schema changes must go through Alembic.

## Known Boundary Risks

- API and Worker currently duplicate SQLAlchemy model definitions.
- `summary_agent.py` contains current Qwen3 bridge plus legacy OpenAI/rule-based code.
- Legacy root `api` and `mobile` directories remain visible.
- Runtime logs, debug JSON, and local audio are stored inside the repo tree.

