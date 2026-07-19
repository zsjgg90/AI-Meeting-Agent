# Known Limitations

## P0

No open P0 blockers were confirmed during RC validation.

## P1

1. Live Qwen3 + RAG analysis depends on local availability of the BGE embedding model. If the model cache is incomplete, the retriever may attempt Hugging Face network access.
2. API and Worker duplicate SQLAlchemy model definitions, creating schema drift risk.
3. `summary_agent.py` still contains legacy analysis paths and remains complex.
4. Root `.env` can contain Docker hostnames. Local startup scripts mitigate this, but manual service starts can still fail if they use Docker hostnames on Windows.

## P2

1. Legacy root `api` and `mobile` directories remain visible beside active `services/api` and `apps/mobile`.
2. Default tests do not run live Qwen3 + RAG evaluation.
3. Expo automated screen tests are not present.
4. End-to-end recording/upload/process/analyze/display smoke testing is manual.
5. Some Chinese text in `.env.example` and PowerShell output can display mojibake.

## P3

1. Semantic Event extraction exists as an independent module and is not yet connected to formal six-dimension analysis.
2. RAG versioning is file-based; no administrative UI exists.
3. Multi-user permissions and enterprise tenancy are not implemented.

