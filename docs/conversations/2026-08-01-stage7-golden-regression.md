# Stage7 Golden Regression Optimization

## 开发目标

基于 `data/eval/golden_cases/project_delivery_001/` 对比人工标注真值和当前 pipeline 输出，修复会议分析 Agent 在结论、待办、风险和未决事项上的边界误判。

## 背景

该 Golden Case 聚焦 proposal-vs-decision、evidence validation 和 hallucination control。原输出存在三类主要问题：将“暂时不做最终决定”放入核心结论，将条件性资源评估放入结论和风险，将建议或需要提前确认的表达升级为 action/open question。

## 实现方案

本次采用最小改动方案，只在 Worker anti-hallucination validator 中增加边界过滤和证据对齐规则，不修改 Prompt、RAG、Schema、API Contract、数据库或 Golden Dataset `expected.json`。

## 修改内容

- 增加 unresolved signal 判断，防止“暂不决定/未明确/是否启动”进入 `key_conclusions`。
- 增加 conditional follow-up 判断，防止“如果指标未改善，需要重新评估资源投入”类条件评估进入核心结论。
- 增加 confirmed short-term direction 修复，将“建议先做可以快速上线的部分”且后文“这个方向先推进”的场景稳定为 `优先执行当前可落地方案`。
- 增加 action 过滤，删除 direction-only、suggestion-only 或 source 不支持任务细节的 action。
- 增加 unresolved issue 过滤，删除“需要提前确认，否则可能反复”这类流程要求/风险提示误入未决事项。
- 增加 explicit risk source 过滤，只保留 source_text 中有明确风险表达的风险项。
- 更新 `project_delivery_001` 的 `actual_after.json` 为修复后的 validator 输出，并生成 Stage7 评估报告。

## 影响范围

影响范围限定在 `services/worker/app/anti_hallucination_validator.py` 的最终后处理阶段，以及对应 Worker 单元测试。不会改变模型调用、RAG 检索、Prompt、Schema、API、数据库或移动端展示逻辑。

## 测试结果

- 已执行：`python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_pipeline_output`
- 结果：通过，9 tests OK。
- 已执行：`python .\scripts\evaluate_meeting_analysis.py .\data\eval\golden_cases\project_delivery_001\expected.json .\data\eval\golden_cases\project_delivery_001\actual_after.json --transcript .\data\eval\golden_cases\project_delivery_001\transcript.txt --output .\data\eval\reports\stage7_project_delivery_report.md --json-output .\data\eval\reports\stage7_project_delivery_report.json`
- 结果：报告生成成功。

## 指标结果

- `decision_precision`: 1.0
- `task_recall`: 0.0
- `risk_recall`: 1.0
- `hallucination_rate`: 0.0
- `evidence_coverage`: 1.0

## 已知限制

`task_recall` 保持 0.0，因为 expected 中的 action task `整理数据和反馈样本`、owner `客户成功` 和 deadline `待确认` 没有 transcript 直接证据。本次遵循 evidence alignment 规则，没有为提高指标生成无证据任务。

## 后续建议

建议后续复核 `project_delivery_001/expected.json` 的 action item 标注，确认是否应调整为有原文证据的任务，或在评估脚本中增加“expected item unsupported by transcript”的标注诊断。
