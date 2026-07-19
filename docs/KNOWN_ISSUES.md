# Known Issues

## High Priority

1. Duplicate active-looking directories: `api`, `mobile`, `services/api`, `apps/mobile`.
2. API and Worker duplicate SQLAlchemy model definitions.
3. `summary_agent.py` is too large and contains legacy OpenAI/rule-based paths plus current Qwen3 persistence orchestration.
4. Local startup scripts include hardcoded paths and one third-party ASR credential.
5. Expo API URL has a hardcoded LAN IP fallback.
6. `.env.example` contains corrupted Chinese text.
7. `scripts/check-services.ps1` still checks the historical local API port
   8002. The current manually running Expo/API session may use API port 8000,
   so the script can report API failure even while the phone is connected to a
   healthy 8000 service.

## Medium Priority

1. Several backup files remain in `services/worker/app`.
2. RAG paths and collection names are hardcoded in `rag_retriever.py`.
3. Some legacy runtime logs and debug outputs live inside the repo tree.
4. README still mixes older MVP/OpenAI wording with current Qwen3 + RAG behavior.
5. Semantic Event module is tested independently but not wired into Orchestrator.
6. Default tests do not execute live Qwen3 + RAG inference; live evaluation remains manual.
7. Live meeting-pipeline acceptance still requires human semantic-quality review
   before final acceptance can be marked passed. The 2026-07-17 rerun passed
   automatic gates but kept `acceptance_passed=false` for manual review. Report:
   `data/debug/meeting_pipeline_acceptance/20260717_020605/acceptance_report.json`.
8. The semantic pipeline is temporarily in shadow mode because live inspection
   showed quality issues before the six-dimension mapper: mitigations can be
   classified as risks, and explicit conclusions can be classified as summary
   progress. The current gold trace is under
   `data/debug/semantic_pipeline_trace/project_weekly/`.
9. The Expo-visible meeting `expo-fixture-20260717-150739` is a manual
   fixture written from the supplied test pack's gold six-dimension answer,
   not a production Qwen3 + RAG, semantic, or fallback result. Its chain audit
   is under `data/debug/chain_audit/expo-fixture-20260717-150739/`.
10. Older summaries without prompt/model metadata may still return
    `result_source=unknown` until regenerated or manually audited.
11. The `meeting_001` legacy Qwen3 + RAG quality audit found raw model output
    errors before normalization: over-detailed agenda, duplicate interface
    items across dimensions, inferred action priority/owner fields, ellipsized
    `source_text`, and missing risks. `anti_hallucination_validator.py` now
    intercepts the agenda, duplicate, evidence, metadata, and conclusion
    boundary issues before persistence. Audit inputs and outputs:
    `data/debug/real_production_analysis/meeting_001/quality_audit.md`,
    `validated_result.json`, and `validator_audit.md`. Prompt cleanup is still
    recommended later so Qwen3 emits complete continuous source evidence
    directly.
12. The 2026-07-18 multi-meeting stability run with deterministic
    `MeetingAnalysisPostProcessor` did not pass the live production gate. Eight
    Qwen3 calls completed with identical deterministic parameters
    (`temperature=0`, `top_p=0.2`, `seed=42`, `format=json`). Improvements:
    proposal leakage dropped to 0, ellipsized/invalid source evidence dropped
    to 0 after filtering, unsupported metadata dropped to 0, and large
    Validator changes dropped to 0. Remaining blockers: 3/4 duplicate meeting
    comparisons still had severe semantic conflict, 2 runs had agenda count
    below 3, action item consistency was below threshold for 2 meetings, and
    the risk-review meeting had unstable risk extraction. Report:
    `data/debug/prompt_stability_eval/stability_report.json`.

## Phase 4 Notes

- The formal Qwen3 + RAG result now passes through `analysis_contract.py` before persistence.
- API and Worker still duplicate SQLAlchemy models; this remains a known maintenance risk, not solved in Phase 4.

## Phase 6 Notes

- API and Worker now expose `/ready`, but readiness checks require services to
  already be running.
- `scripts/check-services.ps1` is read-only and does not start or repair local services.
- Worker structured logs redact large/sensitive fields, but older `print`
  statements still exist in some ASR and diagnostic modules.
- API processing endpoints now deduplicate active tasks and apply a finite Worker request timeout, but very slow local Qwen analysis can still produce `summary_failed` if it exceeds the configured timeout.
- Worker Ollama calls now read `OLLAMA_TIMEOUT_SECONDS` and log the configured
  timeout plus actual duration. Real production debug artifacts are written by
  `run_real_production_analysis.py`.
- A 2026-07-17 API reproduction with 14 transcript segments from the desktop
  meeting-script pack failed after 600 seconds with task error `timed out`.
  Root cause: serialized Qwen3 semantic extraction and legacy Qwen3 analysis
  both exceeded the local timeout window. Worker now uses a rule-based
  long-meeting fast path to avoid this failure mode.
- Phase 6 live acceptance rerun with `--ollama-timeout 120` produced 3/3 direct
  new-pipeline successes and 0 fallbacks. Legacy comparison timed out for 2/3
  meetings during local Qwen3 inference. The semantic path is now shadow-only
  until semantic-event classification quality is improved.
- A manual Expo fixture audit found that several suspicious phrases in
  `expo-fixture-20260717-150739` first appear in the supplied test pack's gold
  answer and then in manually inserted DB fields. They are absent from the
  transcript dialogue and should not be attributed to Qwen3, fallback, or the
  semantic shadow pipeline.
- A 2026-07-20 Expo production analysis failure for meeting
  `73c47be6-0ea0-41eb-ac73-81e458574abd` was caused by stale
  `transcript_segments` row locks from an earlier timed-out summary run. Worker
  now commits speaker-name backfill before RAG/Qwen inference to prevent long
  model calls from holding transcript locks. RAG embedding loading also defaults
  to local cache mode to avoid startup blocking on Hugging Face metadata.

## Low Priority

1. `services/worker/README.md` says speaker labels map to `Speaker 1`, but code currently normalizes to labels such as `speaker_0`.
2. Some files display mojibake in PowerShell output, although key Python files compile.
3. `apps/mobile` has its own `.git` directory, which can confuse root-level source control operations.
