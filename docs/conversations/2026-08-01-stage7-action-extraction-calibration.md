# Stage7.3.x Action Extraction Calibration

## Development Goal

Improve evidence-grounded action recall for Stage7 Golden Regression without changing Golden Dataset, Prompt, RAG, or broad pipeline architecture.

## Background

Stage7.3 regenerated outputs improved decision precision and evidence safety, but Task Recall remained low at `0.4000`. The main gap was that explicit requirement-style action statements such as `需要验证...` and `需要同步...` could be removed as weak action claims.

## Implementation Plan

Use minimal semantic-boundary changes:

- Preserve action items only when `source_text` contains explicit action requirement wording.
- Continue removing suggestion, consideration, uncertainty, and discussion-only text from action items.
- Keep owner and deadline cleanup unchanged, so unsupported owner/deadline fields are cleared.
- Extend semantic validator and semantic fast path to recognize explicit requirement-style actions consistently.

## Changes

- Updated `anti_hallucination_validator.py` so `需要补充`, `需要同步`, `需要更新`, `需要验证`, `需要排查`, `后续安排`, and `下一步完成` can survive action filtering when evidence is present.
- Kept `建议`, `可以`, `可能`, `不确定`, and `讨论` as weak or blocking signals for action extraction.
- Updated `semantic_event_validator.py` assignment patterns to include `同步`, `排查`, `验证`, `评估`, `安排`, `后续安排`, and `下一步完成`.
- Updated `meeting_analysis_pipeline.py` fast-path intent rules so explicit requirement actions become `task_assignment`, while suggestions and considerations remain `proposal`.
- Added tests for explicit `需要验证` and `需要同步` actions, plus negative cases for `建议优化` and `可以考虑`.

## Impact Scope

Modified scope is limited to Stage7 action boundary rules and tests:

- Worker anti-hallucination validator
- Semantic event validator
- Semantic pipeline fast path
- Validator unit tests

No Golden Dataset, Prompt, RAG, schema, API, database, or mobile code was changed.

## Test Results

Executed:

```powershell
python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_pipeline_output
```

Result:

```text
Ran 19 tests in 0.017s
OK
```

## Golden Regression Results

New actual outputs were generated under:

`data/eval/reports/stage7_golden_regression/latest_runs_stage7_3_x/`

Overall metrics:

- Decision Precision: `0.8000`
- Task Recall: `0.5000`
- Risk Recall: `0.8000`
- Hallucination Rate: `0.0000`
- Evidence Coverage: `1.0000`

Compared with Stage7.3:

- Task Recall improved from `0.4000` to `0.5000`.
- Hallucination Rate stayed at `0.0000`.
- Evidence Coverage stayed at `1.0000`.

## Known Limitations

- `ai_meeting_agent_001` still misses expected action requirements because they are not emitted as action candidates by the model output.
- `design_review_001` produces evidence-grounded action text, but recall remains mismatched against the narrower expected task wording.
- `board_strategy_001` still has a risk wording mismatch where the generated risk is more specific than the transcript's conditional wording.

## Follow-Up Suggestions

Stage7.4 RC1 Freeze can proceed only if `Task Recall=0.5000` is accepted as a documented limitation. Otherwise, run one more targeted action extraction pass before freeze, focused on model/postprocessor preservation of requirement-style action candidates.
