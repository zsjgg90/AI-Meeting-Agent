# Schema And Module Boundaries

Last updated: 2026-07-20

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

## Agent Contract Schema

MeetMind Agent v1.0 Phase 1 adds a Worker-internal Agent contract:

- `services/worker/app/agent_contract.py`

Current Agent contract schema version:

```text
agent-contract-v1
```

The Agent contract defines the business objects that later Agent Runtime,
validators, and controlled service conversions may use:

- `Requirement`
- `Decision`
- `AgentActionItem`
- `Issue`
- `Risk`
- `Dependency`
- `Milestone`
- `CustomerRequest`
- `ProjectState`
- `AgentActionProposal`
- `AgentContext`

`AgentActionItem` intentionally uses an Agent-specific class name so it does
not collide with the existing six-dimension action item type or the API/DB
action item read models.

All Agent business objects use `EvidenceRef` for source evidence. `EvidenceRef`
contains:

- `source_type`
- `source_meeting_id`
- `source_segment_id`
- `source_text`
- `start_time`
- `end_time`
- `speaker`
- `confidence`
- `metadata`

`source_type` is restricted to `transcript`, `meeting_history`,
`project_knowledge`, `manual`, or `unknown`. `confidence` may be `None`, and
when present it must be between `0.0` and `1.0`; the contract does not fabricate
a default confidence score.

`AgentContext` is a per-run context only. It keeps `transcript` and
`meeting_analysis` loosely coupled:

```text
transcript: list[dict[str, Any]]
meeting_analysis: dict[str, Any]
```

`AgentContext.runtime_metadata` always contains:

```json
{"schema_version": "agent-contract-v1"}
```

Callers may add extra metadata, but they cannot override the Agent contract
schema version.

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
| Agent Contract | Worker-internal Agent v1 business objects and per-run `AgentContext` validation | API contracts, database writes, raw LLM persistence, Agent runtime orchestration, tool execution |
| Repository/persistence mapping | DB-compatible payload and rows | Prompt building, model calls |

## Compatibility Strategy

- No database migration is required for Phase 4.
- Existing DB fields are kept.
- API keeps legacy response aliases to avoid breaking existing Expo screens.
- `metadata.schema_version` is added as a non-breaking field.
- Formal Qwen3 + RAG results now pass through `MeetingAnalysisSchema` before persistence.
- Semantic pipeline results pass through `MeetingAnalysisSchema` before persistence.
- `SemanticEvent`, `TopicEventGroup`, `SixDimensionResult`, and validation flags remain internal Worker-side structures; introducing API or persistence output for them requires a separate contract change.
- `Requirement`, `Decision`, `AgentActionItem`, `Issue`, `Risk`, `Dependency`,
  `Milestone`, `CustomerRequest`, `ProjectState`, `AgentActionProposal`, and
  `AgentContext` are internal Agent contract objects in Phase 1. They are not
  persisted to PostgreSQL, exposed through the API, or used to replace
  `MeetingAnalysisSchema`.
- Raw LLM output must not directly become formal Agent business objects. Later
  phases must use controlled conversion and validation before any state update.
- Qwen3 + RAG analysis remains the fallback path and must log `fallback_reason` when used after semantic pipeline failure.

## Known Remaining Risks

- API and Worker still define duplicate SQLAlchemy models and must remain manually synchronized.
- Legacy OpenAI/rule-based code remains in `summary_agent.py`; current formal path is isolated but the file is still large.
- Prompt/RAG version management is documented in `docs/PROMPT_AND_RAG_VERSIONING.md`; persisted metadata is available after migration `20260715_0011`.
