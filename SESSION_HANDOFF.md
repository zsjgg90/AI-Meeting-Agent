# Session Handoff

## Current State

The project is in Release Candidate verification state after completing the seven-phase maintainability hardening plan.
Agent v1.0 upgrade preparation has started at Phase 0 baseline freeze. The
baseline document is `docs/AGENT_V1_PHASE_0_BASELINE.md`.
The Phase 0 runtime diagnostic currently fails because API port 8002 is not
reachable; Worker 8001, PostgreSQL, Ollama, RAG, and Alembic head are OK.

Repository freeze metadata:

- Repository: `https://github.com/zsjgg90/AI-Meeting-Agent`
- Baseline branch: `main`
- Baseline commit: `85dca9cb6e2944bfed2926d0a26b5f40d64ffc10`
- Baseline tag: `agent-v1-phase0-baseline`
- Agent development branch: `feature/agent-v1`
- Freeze date: `2026-07-20`

Completed phases:

1. Project audit
2. Project memory and documentation entry
3. Unified configuration management
4. Unified schema and module boundaries
5. Prompt and RAG version management
6. Testing, logging, and observability
7. RC final validation

## Active Paths

- Mobile: `apps/mobile`
- API: `services/api`
- Worker: `services/worker`
- RAG source: `data/rag`
- Chroma DB: `data/vector_db`
- Docs: `docs`

Legacy paths remain but should not be modified for active work:

- `api`
- `mobile`

## Formal Analysis Chain

```text
Expo -> API -> Worker -> RAG Retrieval -> Qwen3 14B -> Validator -> MeetingAnalysisSchema -> PostgreSQL -> API -> Expo
```

Formal model:

```text
qwen3:14b
```

Formal schema:

```text
meeting-analysis-v1
```

Formal prompt:

```text
meeting-analyst-v1
```

## Commands To Reproduce RC Checks

```powershell
.\scripts\test-all.ps1
.\scripts\check-services.ps1
```

## Important RC Finding

The local API startup script was updated so Docker-style `WORKER_URL=http://worker:8001` is converted for Windows local development. This fixes API readiness when the root `.env` contains Docker hostnames.

Modified files from RC:

- `scripts/local-env.ps1`
- `services/api/start-api-local.ps1`

## 2026-07-20 Production Analysis Repair

Meeting `73c47be6-0ea0-41eb-ac73-81e458574abd` (`周会5`) failed because an
earlier timed-out summary run left `transcript_segments` speaker-name updates
locked. Later Worker `/analyze` calls waited on those locks and never reached
RAG or Qwen. The stale Postgres backends were terminated and Worker analysis was
rerun successfully, generating summary
`33db99a1-634d-4d57-b28b-f720c4d9bcde` in about 40.35 seconds.

Code changes:

- `services/worker/app/summary_agent.py` now commits speaker-name backfill
  before long RAG/Qwen analysis.
- `services/worker/app/rag_retriever.py` now loads the embedding model with
  `local_files_only=True` by default through Worker settings.

Runtime note: this desktop session has API listening on port 8000 while
`scripts/check-services.ps1` checks the historical 8002 port. Worker 8001 is
healthy after restart.

## Next Recommended Work

Do not continue broad refactoring immediately. First stabilize:

1. Push `main`, `agent-v1-phase0-baseline`, and `feature/agent-v1` after GitHub
   connectivity or authorization is available.
2. Import the 19 required Agent baseline meeting artifacts under
   `data/eval/agent_v1_baseline/`.
3. Run `.\scripts\test-all.ps1`.
4. Run `.\scripts\check-services.ps1` with local services available.
5. Continue embedding model offline/cache setup, shared API/Worker model
   strategy, live benchmark gate, and E2E demo script.
