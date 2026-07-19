# Schema And Module Boundaries

Last updated: 2026-07-17

## Authoritative Meeting Analysis Schema

The authoritative business schema for six-dimension meeting analysis is:

- `services/worker/app/meeting_analysis_schema.py`

The Worker contract boundary is:

- `services/worker/app/analysis_contract.py`

Formal flow:

```text
LLM raw JSON
-> JSON parse
-> anti hallucination validator
-> normalize_meeting_analysis_result()
-> MeetingAnalysisSchema
-> analysis_to_persistence_payload()
-> MeetingSummary + ActionItem
-> API SummaryRead
-> Expo MeetingSummary type
```

Model raw output must not be written to the database directly.

## Schema Version

Current schema version:

```text
meeting-analysis-v1
```

The version is exposed to API consumers through:

```text
GET /meetings/{meeting_id}/summary
metadata.schema_version
```

## Six-Dimension Mapping

| Dimension | Canonical field | DB compatibility | API field | Frontend field |
| --- | --- | --- | --- | --- |
| Meeting agenda | `meeting_agenda` | `meeting_agenda`, legacy `agenda` | `meeting_agenda`, `agenda` | `meeting_agenda`, `agenda` |
| Meeting summary | `meeting_summary` | `meeting_summary`, legacy `overview` | `meeting_summary`, `overview`, `summary` | `meeting_summary`, `overview`, `summary` |
| Key conclusions | `key_conclusions` | `key_conclusions`, legacy `decisions` | `key_conclusions`, `decisions` | `key_conclusions`, `decisions` |
| Action items | `action_items` | `action_items` table | `action_items` | `action_items` |
| Unresolved issues | `unresolved_issues` | `unresolved_issues`, legacy `open_questions` | `unresolved_issues`, `open_questions` | `unresolved_issues`, `open_questions` |
| Risks and focus | `risks_and_focus` | `risks_and_focus`, legacy `risks` | `risks_and_focus`, `risks` | `risks_and_focus`, `risks` |

Legacy fields remain for backward compatibility. New code should prefer canonical fields.

## Module Boundaries

| Layer | Owns | Must not own |
| --- | --- | --- |
| Expo | UI, user interaction, API calls, view model fallback | Worker/Ollama/Chroma access, raw LLM parsing |
| API | HTTP contracts, validation, upload coordination, task submission, read models | ASR, RAG, model calls, business analysis |
| Worker | ASR, diarization, transcript building, AI analysis orchestration, validation, persistence mapping | Mobile UI, public HTTP contracts |
| RAG Retriever | Retrieval only | Prompt business definitions, persistence |
| Ollama Client | Model transport only | Schema normalization, validation, persistence |
| Validator | Evidence and boundary validation | Database writes, API response shaping |
| Semantic Analysis Pipeline | Worker-side orchestration from transcript rows to existing six-dimension result dict | Database writes, API response shaping, direct persistence of internal event/topic schemas |
| Topic Event Aggregator | Grouping of validated `SemanticEvent` rows into `TopicEventGroup` | LLM calls, database writes, API response shaping |
| Six Dimension Mapper | Rule mapping from `TopicEventGroup` into `SixDimensionResult` | LLM calls, database writes, API response shaping |
| Six Dimension Validator | Quality control for `SixDimensionResult` evidence, status, and duplicates | LLM calls, database writes, API response shaping |
| Repository/persistence mapping | DB-compatible payload and rows | Prompt building, model calls |

## Compatibility Strategy

- No database migration is required for Phase 4.
- Existing DB fields are kept.
- API keeps legacy response aliases to avoid breaking existing Expo screens.
- `metadata.schema_version` is added as a non-breaking field.
- Formal Qwen3 + RAG results now pass through `MeetingAnalysisSchema` before persistence.
- Semantic pipeline results pass through `MeetingAnalysisSchema` before persistence.
- `SemanticEvent`, `TopicEventGroup`, `SixDimensionResult`, and validation flags remain internal Worker-side structures; introducing API or persistence output for them requires a separate contract change.
- Qwen3 + RAG analysis remains the fallback path and must log `fallback_reason` when used after semantic pipeline failure.

## Known Remaining Risks

- API and Worker still define duplicate SQLAlchemy models and must remain manually synchronized.
- Legacy OpenAI/rule-based code remains in `summary_agent.py`; current formal path is isolated but the file is still large.
- Prompt/RAG version management is documented in `docs/PROMPT_AND_RAG_VERSIONING.md`; persisted metadata is available after migration `20260715_0011`.
