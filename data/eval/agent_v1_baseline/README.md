# Agent v1.0 Baseline Dataset

This directory is reserved for the Phase 0 reusable baseline dataset.

Expected layout:

```text
data/eval/agent_v1_baseline/<scenario>/<meeting_id>/
```

Each meeting folder must contain:

- `transcript.txt`
- `six_dimension_output.json`
- `validator_audit.md`
- `model_raw_output.json`
- `final_api_response.json`
- `human_expected_result.md`

The required minimum baseline set is documented in
`docs/AGENT_V1_PHASE_0_BASELINE.md`.
