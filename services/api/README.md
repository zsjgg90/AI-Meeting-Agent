# Meeting Agent API

FastAPI backend for the meeting AI Agent MVP.

## Local Docker Run

From the repository root:

```bash
cp .env.example .env
docker-compose up --build
```

The API container runs Alembic migrations before starting Uvicorn.

## API

- `POST /meetings` creates a meeting
- `GET /meetings` lists meetings
- `GET /meetings/{id}` returns meeting detail
- `POST /meetings/{id}/audio` uploads an audio file
- `POST /meetings/{id}/process` starts transcription and meeting analysis
- `POST /meetings/{id}/analyze` starts the same Meeting Analyst pipeline explicitly
- `GET /meetings/{id}/transcript` returns transcript output
- `GET /meetings/{id}/summary` returns the structured Meeting Analyst JSON:
  - `meeting_agenda`
  - `meeting_summary`
  - `key_conclusions`
  - `action_items`
  - `unresolved_issues`
  - `risks_and_focus`
  - `topics`
  - `metadata`

Docker Swagger UI: http://localhost:8000/docs

Local Windows script Swagger UI: http://localhost:8002/docs

## Audio Upload

`POST /meetings/{id}/audio` accepts `m4a`, `mp3`, and `wav` files. Uploaded files are stored under:

```text
storage/meetings/{meeting_id}/audio/
```

The response includes:

- `audio_file_id`
- `meeting_id`
- `filename`
- `path`
- `file_size_bytes`

The database records file path, file size, content type, and upload time.

## Manual Migration

```bash
cd services/api
alembic upgrade head
```
