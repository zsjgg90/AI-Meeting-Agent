# Runbook

## Daily Local Start

```powershell
.\services\worker\start-worker-local.ps1
.\services\api\start-api-local.ps1
cd apps\mobile
npx expo start --host lan --port 8081
```

## Health And Readiness

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe http://127.0.0.1:8001/ready
curl.exe http://127.0.0.1:8002/health
curl.exe http://127.0.0.1:8002/ready
```

Or run:

```powershell
.\scripts\check-services.ps1
```

## Formal Analysis Log Markers

During real meeting analysis, Worker logs should include:

```text
[RAG] Collection loaded: meeting_analyst_rules, count=350
[ANALYST] Step 1/5: retrieving RAG rules
[ANALYST] Step 2/5: building prompt
[ANALYST] Step 3/5: calling Qwen3
[OLLAMA] Calling model: qwen3:14b
[ANALYST] Step 5/5: validating result
```

## Common Failures

### API `/ready` fails with Worker connection error

Cause: `WORKER_URL` points to Docker hostname such as `http://worker:8001`.

Fix:

```powershell
.\services\api\start-api-local.ps1
```

The local script converts Docker-style Worker hostnames for Windows local runs.

### Worker `/ready` fails on Ollama

Check:

```powershell
ollama list
curl.exe http://127.0.0.1:11434/api/tags
```

Install:

```powershell
ollama pull qwen3:14b
```

### RAG model loads slowly or attempts network access

Cause: the embedding model is not fully cached.

Fix: pre-cache `BAAI/bge-small-zh-v1.5` or set `RAG_EMBEDDING_MODEL` to a local snapshot path.

### Transcript exists but analysis fails

Check:

```powershell
curl.exe http://127.0.0.1:8002/meetings/{meeting_id}/transcript
curl.exe -X POST http://127.0.0.1:8002/meetings/{meeting_id}/analyze
curl.exe http://127.0.0.1:8002/meetings/{meeting_id}/summary
```

Confirm transcript segments are non-empty before analyzing.

## Verification Suite

```powershell
.\scripts\test-all.ps1
.\scripts\check-services.ps1
```

