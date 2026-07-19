# Deployment

## Required Services

- PostgreSQL
- API Service
- Worker Service
- Ollama
- Chroma vector database files under `data/vector_db`
- Expo app for mobile development/demo

## Required Model

```powershell
ollama pull qwen3:14b
ollama list
```

`qwen3:14b` is the formal meeting analysis model.

## Required RAG Data

Formal RAG files:

- `data/rag/meeting_analyst_rag_manifest.json`
- `data/rag/meeting_analyst_rag_350_chunks.jsonl`
- `data/vector_db`

Expected collection:

```text
meeting_analyst_rules
```

Expected chunk count:

```text
350
```

## Environment

Use `.env.example` as the base. Critical variables:

```env
DATABASE_URL=postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent
WORKER_URL=http://127.0.0.1:8001
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:14b
RAG_ENABLED=true
RAG_COLLECTION_NAME=meeting_analyst_rules
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

For offline or restricted-network deployments, set `RAG_EMBEDDING_MODEL` to a local cached model path.

## Windows Local Startup

```powershell
.\services\worker\start-worker-local.ps1
.\services\api\start-api-local.ps1
cd apps\mobile
npx expo start --host lan --port 8081
```

## Service Verification

```powershell
.\scripts\check-services.ps1
```

Expected:

- API `/health`: ok
- API `/ready`: ok
- Worker `/health`: ok
- Worker `/ready`: ok
- Ollama model: `qwen3:14b`
- RAG collection count: 350

## Database Migration

From `services/api`:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\alembic.exe current
```

Current expected head:

```text
20260715_0011
```

## Docker Notes

Docker Compose uses internal service hostnames such as `db` and `worker`. Windows local scripts convert Docker-style local values to `127.0.0.1` where needed.

Do not use Docker hostnames from Expo Go on a physical phone. Expo must use the machine LAN IP for API access.

