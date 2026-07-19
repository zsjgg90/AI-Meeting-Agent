# Meeting Transcription Worker

This worker transcribes uploaded meeting audio with `faster-whisper`, runs speaker diarization with `pyannote.audio`, and writes transcript segments to PostgreSQL.

## Transcript Provider

The Transcript Agent supports provider-based transcription:

```env
TRANSCRIPT_PROVIDER=auto
VOLCENGINE_ASR_API_KEY=
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.auc
VOLCENGINE_REALTIME_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_ENABLE_SPEAKER_INFO=true
VOLCENGINE_ENABLE_GENDER_DETECTION=true
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
WHISPER_MODEL_SIZE=small
REALTIME_WHISPER_MODEL_SIZE=small
WHISPER_LANGUAGE=zh
```

- `auto`: use Volcengine/Doubao ASR with the new console `VOLCENGINE_ASR_API_KEY` when configured, otherwise OpenAI, then fall back to local `faster-whisper`.
- `volcengine` or `doubao`: require Volcengine/Doubao ASR new console API key and fail if it is unavailable.
- `openai`: require OpenAI transcription and fail if it is unavailable.
- `faster_whisper`: use local transcription only.

Realtime captions try the Volcengine realtime resource first when configured and fall back to local incremental transcription if unavailable. After the meeting ends, the Transcript Agent re-transcribes uploaded audio with the configured high-accuracy provider and overwrites the realtime draft transcript.

## Input

```bash
python -m app.transcribe_meeting <meeting_id>
```

## Output Table

The worker writes rows to `transcript_segments`.

Each segment contains:

- `start_time`
- `end_time`
- `text`
- `speaker_label`

Volcengine speaker labels such as `spk_0` and `spk_1` are mapped to editable labels such as `Speaker 1` and `Speaker 2`.

## Diarization

Set a Hugging Face token that has access to the configured pyannote model:

```env
HUGGINGFACE_TOKEN=hf_...
PYANNOTE_PIPELINE=pyannote/speaker-diarization-3.1
```

Optional speaker count hints:

```env
PYANNOTE_NUM_SPEAKERS=
PYANNOTE_MIN_SPEAKERS=
PYANNOTE_MAX_SPEAKERS=
```

## Docker

From the repository root:

```bash
docker compose run --rm worker python -m app.transcribe_meeting <meeting_id>
```

## Meeting Analyst Agent Pipeline

Generate a structured summary from saved transcript segments:

```bash
docker compose run --rm worker python -m app.summarize_meeting <meeting_id>
```

The Meeting Analyst pipeline runs:

1. Transcript Cleaner
2. Semantic Label Agent
3. Topic Chunk Agent
4. Six-dimension analyst agents
5. Boundary Rule Engine
6. JSON Schema validation with one retry for LLM JSON failures

It saves:

- `meeting_summaries`: `meeting_agenda`, `meeting_summary`, `key_conclusions`, `unresolved_issues`, `risks_and_focus`, `topics`, `model_name`, `confidence_score`
- `action_items`: `owner_name`, `task`, `deadline`, `priority`, `status`, `source_text`, `source_segment_id`, `confidence`
- `transcript_segments`: `semantic_label`, `speaker_name`

If JSON parsing fails, the agent retries the LLM call once. If the LLM is unavailable, the rule-based pipeline still returns valid structured JSON.

Run tests:

```bash
cd ../..
services/worker/.venv/Scripts/python.exe -m unittest services.worker.tests.test_meeting_analyst_pipeline
```
