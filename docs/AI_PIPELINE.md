# AI Pipeline

## Formal Meeting Analysis Pipeline

The formal meeting analysis path is:

```text
TranscriptSegment rows
  -> build_transcript_text
  -> meeting_analyst_service.analyze_meeting
  -> RagRetriever.build_context
  -> build_meeting_analyst_prompt
  -> OllamaClient.chat
  -> qwen3:14b
  -> extract_json
  -> normalize_meeting_analysis_result
  -> MeetingAnalysisPostProcessor
  -> validate_meeting_analysis
  -> save_summary
```

Formal Qwen3 + RAG results must carry `metadata.result_source=legacy_qwen_rag`.
Manual Expo gold answers must carry `result_source=fixture`, and semantic
shadow/debug outputs must carry `result_source=semantic_pipeline`.

The same formal Qwen3 + RAG call also returns internal title fields:
`meeting_type`, `meeting_type_confidence`, `meeting_title_candidate`, and
`title_basis`. These fields do not change the six output dimensions. Worker
only applies `meeting_title_candidate` to `meeting.title` when the current
title is still the system fallback, the type confidence is at least `0.70`,
there are at least two valid basis entries, and deterministic title validation
passes. Title validation failure keeps the fallback title and must not block
summary persistence or meeting completion.

`MeetingAnalysisPostProcessor` is a deterministic boundary pass between schema
normalization and the anti-hallucination Validator. It may filter, deduplicate,
sort, clear unsupported fields, and enforce dimension boundaries, but it must
not generate, rewrite, or supplement meeting facts.

## Semantic Shadow Pipeline

The semantic event pipeline is currently shadow-only. `summary_agent.py` calls
`analyze_meeting_shadow_mode`, which first obtains the formal Qwen3 + RAG result,
then runs the semantic path for trace generation:

```text
TranscriptSegment rows
  -> analyze_meeting_shadow_mode
  -> run_semantic_shadow_trace
  -> SemanticEventExtractor or rule-based SemanticEvent fast path
  -> SemanticEventValidator
  -> TopicEventAggregator
  -> SixDimensionMapper
  -> SixDimensionValidator
  -> data/debug/semantic_pipeline_trace/<meeting_id>/
```

The shadow path logs `semantic_pipeline.trace_dir`,
`semantic_pipeline.shadow_completed`, or `semantic_pipeline.shadow_failed`. A
shadow failure, empty semantic output, or malformed semantic result must not
overwrite the formal Qwen3 + RAG summary.

Each shadow run writes:

- `01_utterances.json`
- `02_semantic_events_raw.json`
- `03_semantic_events_validated.json`
- `04_topic_groups.json`
- `05_six_dimension_mapped.json`
- `06_six_dimension_validated.json`
- `07_final_meeting_analysis.json`
- `comparison.md`

## Six Output Dimensions

The summary API should return:

- `meeting_agenda`
- `meeting_summary`
- `key_conclusions`
- `action_items`
- `unresolved_issues`
- `risks_and_focus`
- `topics`
- `metadata`

## Model Configuration

The model must be read from configuration:

- env: `OLLAMA_MODEL`
- default: `qwen3:14b`
- env: `OLLAMA_TEMPERATURE`
- default: `0`
- env: `OLLAMA_TOP_P`
- default: `0.2`
- env: `OLLAMA_SEED`
- default: `42`
- env: `OLLAMA_FORMAT`
- default: `json`
- env: `OLLAMA_TIMEOUT_SECONDS`
- default: `600`
- config: `services/worker/app/config.py`
- client: `services/worker/app/ollama_client.py`

Do not hardcode model names in business logic.
The formal Qwen3 + RAG path logs the resolved temperature, top_p, seed, JSON
format, context length, and timeout for each model call.

Single-meeting live production diagnostics use:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
```

The script writes `input_transcript.txt`, `rag_context.json`, `prompt.txt`,
`model_raw_output.json`, `normalized_result.json`, and `pipeline.log` under
`data/debug/real_production_analysis/<meeting_id>/`.

Prompt-only regression reruns for the same meeting may additionally write
`model_raw_output_v2.json`, `normalized_result_v2.json`, and
`quality_audit_v2.md`. These compare raw model quality before Validator
cleanup, including agenda count, ellipsized evidence, cross-dimension
duplicates, unsupported action metadata, and proposal leakage into conclusions.

Multi-meeting prompt stability regression uses:

```powershell
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_prompt_stability_eval.py --meeting-limit 4 --meeting-indices 1,2,3,4 --runs-per-meeting 2 --ollama-timeout 180
```

The script does not change Prompt, RAG, Validator, persistence, API, or frontend
code. It repeats selected meetings with the same Qwen3 + RAG configuration and
writes `run_1_result.json`, `run_2_result.json`, `comparison.json`, and
`stability_report.json/.md` under `data/debug/prompt_stability_eval/`.
The report includes inference parameter equality checks plus conclusion, action,
agenda, and output-order consistency metrics across duplicate runs.
Each run also writes `normalized_before_postprocess.json`,
`postprocessed_result.json`, and `validated_result.json` under `run_<n>/`,
plus PostProcessor and Validator audit files. The report includes
keep/remove/modify counts for both layers.

`anti_hallucination_validator.py` is the formal pre-persistence quality gate for
legacy Qwen3 + RAG output. It does not call the model. Current checks include:

- agenda cleanup and default max 6 agenda items;
- proposal/question/action filtering from `key_conclusions`;
- strict continuous `source_text` validation, with deterministic repair from
  the transcript when possible;
- unsupported action `owner_name`, `deadline`, and `priority` cleanup;
- cross-dimension duplicate removal with action > conclusion > issue > risk
  priority, while allowing formal decisions to coexist with their follow-up
  actions.

Validator-only real regression artifacts for `meeting_001` are written as
`validated_result.json` and `validator_audit.md` in the same debug directory.

## RAG Configuration

Current RAG implementation:

- source file: `data/rag/meeting_analyst_rag_350_chunks.jsonl`
- Chroma DB: `data/vector_db`
- collection: `meeting_analyst_rules`
- embedding model: `BAAI/bge-small-zh-v1.5`

These values are currently in `services/worker/app/rag_retriever.py` and should be configuration candidates in a later phase.

## Semantic Event Module

The sentence-level semantic event module is wired into the Worker as a shadow
diagnostic path through `meeting_analysis_pipeline.py`. Internal semantic event,
topic, and validation structures remain Worker-only and are not persisted or
exposed through API responses.

Current files:

- `semantic_event_schema.py`
- `semantic_event_extractor.py`
- `semantic_event_validator.py`
- `semantic_clause_splitter.py`
- `topic_event_schema.py`
- `topic_event_aggregator.py`
- `six_dimension_schema.py`
- `six_dimension_mapper.py`
- `six_dimension_validator.py`
- `meeting_analysis_pipeline.py`
- `prompts/semantic_event_extractor.md`

The topic-level event aggregation path is:

```text
Validated Semantic Events
  -> TopicEventAggregator.aggregate
  -> TopicEventGroup
```

It groups validated sentence-level events by topic, detects topic switches,
deduplicates repeated events, merges simple state transitions, and preserves
the merged source evidence on the retained event.

The rule-based semantic six-dimension mapping path is:

```text
TopicEventGroup
  -> SixDimensionMapper.map_topics
  -> SixDimensionResult
```

It maps topic events into agenda, summary, conclusions, actions, open issues,
and risks with source evidence.

The rule-based semantic six-dimension validation path is:

```text
SixDimensionResult
  -> SixDimensionValidator.validate
  -> SixDimensionResult
```

It filters entries with invalid topic/event evidence, checks dimension-specific
source intent rules, deduplicates repeated entries, keeps allowed decision/action
pairs, and marks low-confidence items for review. Internal topic, event, and
validation structures are not persisted or exposed through API responses.
