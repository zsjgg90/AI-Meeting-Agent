# Evaluation Schema

`evaluation_case.schema.json` defines the offline evaluation case shape:

- `transcript`: raw transcript text or segment list used only for evidence
  checks.
- `expected_result`: human gold answer compatible with `meeting-analysis-v1`.
- `actual_result`: AI output compatible with `meeting-analysis-v1`.
- `evaluation_metadata`: model, prompt, RAG, case, and schema metadata.

This schema is an evaluation artifact only. It does not replace or modify
`services/worker/app/meeting_analysis_schema.py`.
