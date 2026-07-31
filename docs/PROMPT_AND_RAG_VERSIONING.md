# Prompt And RAG Versioning

Last updated: 2026-07-30

## Formal Prompt

The formal Meeting Analyst prompt is:

- Prompt ID: `meeting-analyst`
- Prompt version: `meeting-analyst-v1`
- Schema version: `meeting-analysis-v1`
- Template: `services/worker/app/prompts/meeting_analyst_qwen3.md`
- Registry: `services/worker/app/prompt_registry.py`
- Runtime builder: `services/worker/app/meeting_analyst_prompt.py`

Business code must not hardcode the formal prompt body. It should load the
template through the prompt registry and keep `prompt_version` in analysis
metadata.

The current `meeting-analyst-v1` template was rolled back from the stricter
fixed-order experiment to the simpler boundary-focused prompt. It includes
explicit quality rules for:

- 3-6 theme-level agenda items, not speaker-turn agendas;
- `source_text` copied as a complete continuous transcript fragment, with no
  `...` or `……`;
- no inferred `owner_name`, `deadline`, or `priority`;
- proposal-vs-decision, open-issue-vs-action, and progress-vs-conclusion
  boundaries;
- cross-dimension de-duplication while allowing formal decision/action pairs.
- internal title fields `meeting_type`, `meeting_type_confidence`,
  `meeting_title_candidate`, and `title_basis`, using the complete transcript,
  `meeting_agenda`, and `meeting_summary` before `key_conclusions`, and not
  using `action_items` as the primary title basis.

Prompt-only regression artifacts for `meeting_001` are stored under
`data/debug/real_production_analysis/meeting_001/` as
`model_raw_output_v2.json`, `normalized_result_v2.json`, and
`quality_audit_v2.md`.

Multi-meeting stability artifacts are stored under
`data/debug/prompt_stability_eval/` by
`services/worker/scripts/run_prompt_stability_eval.py`. This script is a live
quality gate only and must reuse the current prompt version, RAG dataset, model,
PostProcessor, and Validator without modifying them. Each run saves
`normalized_before_postprocess.json`, `postprocessed_result.json`, and
`validated_result.json` in a `run_<n>/` subdirectory.

Current deterministic Qwen3 defaults for the formal path are `temperature=0`,
`top_p=0.2`, `seed=42`, and `format=json`.

Legacy prompts remain for compatibility and experiments, but they are not the
formal Qwen3 + RAG analysis path:

- `services/worker/app/prompts/meeting_analyst.md`
- Legacy OpenAI prompt strings in `services/worker/app/summary_agent.py`
- `services/worker/app/prompts/semantic_event_extractor.md`

## RAG Dataset

The formal Meeting Analyst RAG source is:

- Manifest: `data/rag/meeting_analyst_rag_manifest.json`
- Source file: `data/rag/meeting_analyst_rag_350_chunks.jsonl`
- Dataset version: `meeting_analyst_rag_v1`
- Chunk schema version: `rag-chunk-v1`
- Stable chunk id field: `chunk_id`
- Collection: `meeting_analyst_rules`
- Embedding model: `BAAI/bge-small-zh-v1.5`
- Chroma path: `data/vector_db`

RAG chunks define classification rules only. They must not inject meeting facts.

## Runtime Traceability

Formal analysis metadata must include:

- `schema_version`
- `model_name`
- `prompt_version`
- `rag_chunk_ids`
- `rag_dataset_version`
- `rag_chunk_schema_version`
- `rag_collection_name`
- `rag_embedding_model`
- `confidence_score`
- `generated_at`

`rag_chunk_ids` must come from the actual retrieval result used to build the
prompt context.

## RAG Import

Import command:

```powershell
cd D:\codex_work\会议声纹识别
services\worker\.venv\Scripts\python.exe services\worker\scripts\import_rag_chroma.py
```

The import script validates duplicate `chunk_id` values and uses Chroma
`upsert`, so repeated imports are idempotent.

To intentionally rebuild the collection:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\import_rag_chroma.py --reset
```

## Configuration

Relevant environment variables:

```env
RAG_ENABLED=true
RAG_CHROMA_DB_DIR=
RAG_COLLECTION_NAME=meeting_analyst_rules
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_TOP_K=8
RAG_DISTANCE_THRESHOLD=
RAG_MAX_CONTEXT_CHARS=12000
RAG_DATASET_VERSION=meeting_analyst_rag_v1
RAG_CHUNK_SCHEMA_VERSION=rag-chunk-v1
```

## Contract

The prompt and RAG context must feed the formal chain:

```text
Transcript
-> RAG Query
-> RAG Retriever
-> RAG Context
-> Prompt
-> Qwen3
-> Raw Output
-> analysis_contract
-> meeting-analysis-v1
-> MeetingAnalysisPostProcessor
-> AntiHallucinationValidator
-> Persistence
```

Do not bypass `services/worker/app/analysis_contract.py`.
