# Stage7.3 Golden Regression Validation

## 开发目标

重新运行 5 个 Stage7 Golden Case 的正式会议分析 pipeline，生成新的 `actual_generated.json`，验证 Stage7.2 Semantic Boundary 优化是否真实改善 Golden Regression 指标。

## 背景

Stage7.1 已完成 Golden Dataset Evidence Grounding 校准。Stage7.2 已完成 semantic boundary 规则优化，涉及：

- `anti_hallucination_validator.py`
- `semantic_event_validator.py`
- `meeting_analysis_pipeline.py`

本阶段禁止修改 expected、Golden Dataset、Prompt、RAG 和 Validator 规则，只执行生成与验证。

## 新 Actual 生成方式

使用现有正式 pipeline 入口：

`app.meeting_analyst_service.MeetingAnalystService.analyze`

输入为各 Golden Case 的 `transcript.txt`。输出写入：

`data/eval/reports/stage7_golden_regression/latest_runs/<case>/`

每个 case 保存：

- `actual_generated.json`
- `pipeline.log`
- `metadata.json`

运行参数：

- Model: `qwen3:14b`
- Prompt Version: `meeting-analyst-v1`
- RAG Version: `meeting_analyst_rag_v2_1_1`
- RAG Collection: `meeting_analyst_rules_v2_1_1`
- Temperature: `0.0`
- Top P: `0.2`
- Seed: `42`
- Format: `json`
- `RAG_EMBEDDING_LOCAL_FILES_ONLY=true`

## Actual 生成结果

5 个 case 均成功生成：

- `ai_meeting_agent_001`
- `board_strategy_001`
- `design_review_001`
- `project_delivery_001`
- `tech_incident_001`

## Stage7.2 规则是否生效

生效。

- Decision false positives 明显下降：平均 Decision Precision 从 `0.4000` 提升到 `0.8000`。
- Evidence safety 改善：Hallucination Rate 从 `0.0500` 降到 `0.0000`。
- Evidence Coverage 从 `0.9500` 提升到 `1.0000`。
- Risk Recall 保持 `0.8000`，达到本阶段阈值。

## 指标变化

| Metric | Before | Latest | Delta |
|---|---:|---:|---:|
| Decision Precision | 0.4000 | 0.8000 | +0.4000 |
| Task Recall | 0.3667 | 0.4000 | +0.0333 |
| Risk Recall | 0.8000 | 0.8000 | +0.0000 |
| Hallucination Rate | 0.0500 | 0.0000 | -0.0500 |
| Evidence Coverage | 0.9500 | 1.0000 | +0.0500 |

## 剩余问题

- `ai_meeting_agent_001` 未召回 expected 中的 action requirements，也没有输出短期优化结论。
- `design_review_001` 输出了 `提前同步组件规范`，但未召回 expected 的 `结合数据验证设计方向`。
- `tech_incident_001` 未召回 `继续排查事故原因` 和 `补充长期监控机制`。
- `board_strategy_001` 风险仍存在措辞偏移：source 为 `增长速度可能受到影响`，actual 为 `可能导致增长速度下降`，导致 Risk Recall 为 `0.0000`。

## 测试结果

- 已执行：`python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_pipeline_output`
- 结果：通过，14 tests OK。

## 是否满足 Stage7.4 RC1 Freeze 条件

部分满足。

满足：

- Decision Precision 有明显提升。
- Risk Recall 保持 `>= 0.8`。
- Hallucination Rate 未增加，且降为 `0.0000`。
- Evidence Coverage 达到 `1.0000`。

未完全满足：

- Task Recall 仍然较低，仅 `0.4000`。

建议：进入 Stage7.4 前，应明确是否接受低 Task Recall 作为 RC1 已知限制；如果不接受，需要先做一个小范围 action extraction / requirement-to-action 修复。
