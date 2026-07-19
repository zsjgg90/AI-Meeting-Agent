# Local Development

## Prerequisites

- PostgreSQL listening on `127.0.0.1:5432`
- Ollama listening on `127.0.0.1:11434`
- Ollama model pulled:

```powershell
ollama pull qwen3:14b
```

- Node.js and npm for Expo
- Python virtual environments for API and Worker

## One-Command Startup

From repo root:

```powershell
.\start-dev.ps1
```

This checks PostgreSQL, Ollama, Worker, API, and starts Expo.

## Manual Startup

Worker:

```powershell
.\services\worker\start-worker-local.ps1
```

API:

```powershell
.\services\api\start-api-local.ps1
```

Expo:

```powershell
cd apps\mobile
npx expo start --host lan --port 8081
```

## Health Checks

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe http://127.0.0.1:8002/health
curl.exe http://{LAN_IP}:8002/health
```

## Local Development Notes

- Expo Go cannot call `localhost` on a physical phone.
- Expo must use the machine LAN IP for API access.
- Local Worker startup defaults `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so cached Hugging Face models are used without blocking analysis on network probes.
- API defaults `WORKER_REQUEST_TIMEOUT_SECONDS=600`; if Worker or Ollama stalls longer than this, tasks should fail instead of leaving meetings stuck in analysis states.
- Worker logs should show `[ANALYST]`, `[RAG]`, and `[OLLAMA]` during analysis.
- Do not rely on logs under `services/*/*.log` as source of truth; prefer console logs during debugging.
