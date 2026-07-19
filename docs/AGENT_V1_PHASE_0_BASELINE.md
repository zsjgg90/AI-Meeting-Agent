# MeetMind Agent v1.0 Phase 0 Baseline Freeze

Last updated: 2026-07-20

## Scope

This document freezes the current Release Candidate baseline before the
MeetMind Agent v1.0 upgrade. Phase 0 does not change the formal analysis
pipeline and does not introduce Agent orchestration.

## Current Baseline

| Item | Baseline |
| --- | --- |
| Git branch | Blocked: current workspace `.git` directory is not recognized by `git status`. |
| Git commit | Blocked: `git rev-parse HEAD` fails with `fatal: not a git repository`. |
| Alembic head | `20260715_0011_add_prompt_rag_metadata.py`, revision `20260715_0011`. |
| Prompt version | `meeting-analyst-v1`. |
| Prompt file | `services/worker/app/prompts/meeting_analyst_qwen3.md`. |
| RAG source | `data/rag/meeting_analyst_rag_350_chunks.jsonl`. |
| RAG dataset version | `meeting_analyst_rag_v1`. |
| RAG chunk schema version | `rag-chunk-v1`. |
| RAG collection | `meeting_analyst_rules`. |
| RAG expected chunk count | `350`. |
| Embedding model | `BAAI/bge-small-zh-v1.5`. |
| Chroma database | `data/vector_db`. |
| Six-dimension schema | `meeting-analysis-v1`. |
| Formal model | `qwen3:14b` through Ollama. |
| Formal inference defaults | `temperature=0`, `top_p=0.2`, `seed=42`, `format=json`. |
| Formal result source | `legacy_qwen_rag`. |

## Current Formal Analysis Chain

```text
Expo -> API -> Worker -> RAG Retrieval -> Qwen3 14B
-> MeetingAnalysisSchema -> MeetingAnalysisPostProcessor
-> AntiHallucinationValidator -> PostgreSQL -> API -> Expo
```

The semantic event pipeline remains shadow/debug only and must not overwrite
formal meeting summaries.

## Current Fallback Boundaries

- Transcription provider defaults to `auto`.
- If Volcengine/Doubao ASR credentials are missing or unavailable, transcription
  may fall back to OpenAI or local faster-whisper depending on local settings.
- If semantic shadow analysis fails, the formal Qwen3 + RAG result must remain
  the returned result.
- If Qwen3 output needs deterministic cleanup, the result passes through
  `MeetingAnalysisPostProcessor` and then `anti_hallucination_validator.py`.
- Agent orchestration is not part of the current fallback chain.

## Agent Rollout Feature Flags

The following flags are now available in API and Worker settings:

```env
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
```

Meanings:

- `AGENT_MODE_ENABLED`: allow an Agent path to become the formal result.
- `AGENT_SHADOW_MODE`: allow background Agent execution without overwriting
  formal results.
- `AGENT_ACTIONS_ENABLED`: allow confirmed Agent actions to be executed by
  deterministic services.

Phase 0 default behavior keeps the RC formal path unchanged.

## Baseline Acceptance Dataset Requirement

The Agent upgrade requires a reusable baseline set before later phases can be
accepted. Required minimum sample counts:

| Meeting scenario | Required count | Preserved count |
| --- | ---: | ---: |
| Project weekly meeting | 3 | 0 |
| Requirement review | 3 | 0 |
| Cross-department coordination | 3 | 0 |
| Technical solution review | 2 | 0 |
| Version planning | 2 | 0 |
| Customer requirement discussion | 2 | 0 |
| Project retrospective | 2 | 0 |
| Management decision meeting | 2 | 0 |

Each preserved meeting must include:

- Original transcript.
- Existing six-dimension output.
- Validator audit.
- Raw model output.
- Final API response.
- Human expected result.

Recommended storage location:

```text
data/eval/agent_v1_baseline/<scenario>/<meeting_id>/
```

This repository currently contains the baseline requirement and format, but the
actual 19 meeting baseline artifacts have not been imported or verified.

## Phase 0 Acceptance Status

| Criterion | Status |
| --- | --- |
| Current old-path tests pass | Passed: `.\scripts\test-all.ps1` on 2026-07-20. |
| Expo, API, Worker run normally | Failed runtime diagnostic on 2026-07-20: Worker 8001, PostgreSQL, Ollama, RAG, and Alembic head OK; API 8002 health/ready unreachable. |
| Agent can be fully disabled by flags | Implemented at configuration level with default off. |
| Reusable baseline test set saved | Not complete; artifact requirement documented. |
| Agent upgrade branch established | Blocked by invalid local Git metadata. |

## Next Required Actions

1. Repair or reclone Git metadata, then create an Agent upgrade branch and record
   branch plus commit in this document.
2. Import and verify the 19 required baseline meeting artifact folders.
3. Start or repair local API on the expected port, then rerun
   `.\scripts\check-services.ps1`.
