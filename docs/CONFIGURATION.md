# Configuration

## Configuration Files

- Root `.env`
- Root `.env.example`
- `docker-compose.yml`
- `scripts/local-env.ps1`
- `services/api/app/config.py`
- `services/worker/app/config.py`
- `services/api/start-api-local.ps1`
- `services/worker/start-worker-local.ps1`
- `apps/mobile/src/config.ts`
- `apps/mobile/.env`

## Local Windows Values

Use these values when API and Worker run directly on Windows:

```env
DATABASE_URL=postgresql+psycopg://meeting_agent:meeting_agent@127.0.0.1:5432/meeting_agent
STORAGE_DIR=D:\codex_work\会议声纹识别\storage
WORKER_URL=http://127.0.0.1:8001
WORKER_REQUEST_TIMEOUT_SECONDS=600
OLLAMA_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_SECONDS=600
```

`services/api/start-api-local.ps1` and `services/worker/start-worker-local.ps1` load root `.env` through `scripts/local-env.ps1`. If `DATABASE_URL` uses Docker hostnames such as `db`, `postgres`, or `database`, local scripts normalize the host to `127.0.0.1`.

## Expo Go Values

Physical phones cannot use `localhost` or `127.0.0.1` to reach the computer API. Set:

```env
EXPO_PUBLIC_API_BASE_URL=http://{LAN_IP}:8002
```

`apps/mobile/src/config.ts` has a local-only fallback:

```text
http://127.0.0.1:8002
```

Use `apps/mobile/.env` for real device testing.

## Docker Values

Inside Docker Compose, `DATABASE_URL` may use:

```env
postgresql+psycopg://meeting_agent:meeting_agent@db:5432/meeting_agent
```

API should call Worker through:

```env
WORKER_URL=http://worker:8001
WORKER_REQUEST_TIMEOUT_SECONDS=600
```

## Secret Handling

Secrets must live in root `.env` or machine environment variables. Startup scripts must not contain API keys.

Important secret keys:

- `OPENAI_API_KEY`
- `VOLCENGINE_ASR_API_KEY`
- `HUGGINGFACE_TOKEN`

## Model Configuration

Formal Meeting Analyst model:

```env
OLLAMA_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TEMPERATURE=0
OLLAMA_TOP_P=0.2
OLLAMA_SEED=42
OLLAMA_FORMAT=json
OLLAMA_CONTEXT=8192
OLLAMA_TIMEOUT_SECONDS=600
```

Business code should read model values from typed settings only. Do not hardcode model names in service logic.
`OLLAMA_TIMEOUT_SECONDS` controls the Worker-side single Ollama request timeout.
`OLLAMA_TEMPERATURE`, `OLLAMA_TOP_P`, `OLLAMA_SEED`, and `OLLAMA_FORMAT` are
used by the formal Qwen3 + RAG path and live stability scripts to keep repeated
meeting analysis calls deterministic. Current defaults are `temperature=0`,
`top_p=0.2`, `seed=42`, and JSON response format.
API-to-Worker calls still use `WORKER_REQUEST_TIMEOUT_SECONDS`; keep the API
timeout greater than the expected sum of transcription, RAG, Qwen analysis, and
persistence time.

## RAG Configuration

Formal Meeting Analyst RAG:

```env
RAG_ENABLED=true
RAG_CHROMA_DB_DIR=
RAG_COLLECTION_NAME=meeting_analyst_rules
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_LOCAL_FILES_ONLY=true
RAG_TOP_K=8
RAG_DISTANCE_THRESHOLD=
RAG_MAX_CONTEXT_CHARS=12000
RAG_DATASET_VERSION=meeting_analyst_rag_v1
RAG_CHUNK_SCHEMA_VERSION=rag-chunk-v1
```

`RAG_CHROMA_DB_DIR` is optional. If empty, Worker uses `data/vector_db`.
`RAG_EMBEDDING_LOCAL_FILES_ONLY=true` makes Worker load the embedding model from the local Hugging Face cache and fail fast if the cache is missing. Keep this enabled for production analysis so manual Worker starts do not block on network model metadata requests.
For local Windows Worker startup, `services/worker/start-worker-local.ps1` also defaults `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

Prompt and RAG versioning details are documented in:

- `docs/PROMPT_AND_RAG_VERSIONING.md`

## Agent Rollout Guardrails

Agent v1.0 rollout flags are read by both API and Worker settings:

```env
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
```

Default values keep the Release Candidate formal Qwen3 + RAG path unchanged.
`AGENT_MODE_ENABLED=false` prevents any Agent path from becoming the formal
summary result. `AGENT_SHADOW_MODE=true` allows future background Agent
diagnostics once implemented. `AGENT_ACTIONS_ENABLED=false` prevents Agent
suggestions from executing state-changing operations.

Phase 0 baseline details are documented in:

- `docs/AGENT_V1_PHASE_0_BASELINE.md`

## Remaining Configuration Risks

- API Docker default port and local development port differ in some historical docs.
- Root `.env` is local state and may still contain machine-specific values.
- `apps/mobile/.env` must be updated whenever the computer LAN IP changes.
