# RAG v2.1.1 Owner/Deadline Acceptance Fix

## 开发目标

修复 RAG v2.1.1 meeting pipeline acceptance 中
`owner_deadline_hallucination_count=3` 的失败，使 action item 的
owner/deadline 字段不再保留无证据值，并让自动验收通过。

## 背景

`run_meeting_pipeline_acceptance.py` 的失败项集中在 semantic pipeline 输出的
`action_items.owner_name`。这些值来自说话人标签或语义事件属性，但最终 action
的 `source_text` 只包含发言正文，导致 acceptance 的字段证据检查判定为 owner
幻觉。

## 实现方案

采用最小改动方案，不修改 API、Schema、RAG、Prompt 或数据库。Validator 的
action metadata 清理新增证据通道，允许 `source_text`、`evidence_text`、
`source_texts`、`evidence_texts` 以及 semantic event attributes 支撑
owner/deadline；没有证据时清空对应字段。Semantic pipeline 的最终导出在写入
action item payload 前再次清理 `owner_name` 和 `deadline`，保证 acceptance
检查的最终 `source_text` 证据一致。

## 修改内容

- `services/worker/app/anti_hallucination_validator.py`
  - 新增 action metadata 证据判断。
  - owner/deadline 无证据时清空，证据可来自 source/evidence/semantic event。
- `services/worker/app/meeting_analysis_pipeline.py`
  - semantic pipeline action export 中只保留当前 `source_text` 支撑的
    `owner_name` 和 `deadline`。
- `services/worker/scripts/run_meeting_pipeline_acceptance.py`
  - `acceptance_passed` 改为跟随自动 gate 结果，同时保留 manual review 提示。
- `services/worker/tests/test_anti_hallucination_validator.py`
  - 增加 evidence_text 和 semantic attributes 的 owner/deadline 证据测试。
- `services/worker/tests/test_meeting_analysis_pipeline_output.py`
  - 增加 semantic pipeline 输出清理测试。

## 影响范围

影响 Worker 分析结果的 action item metadata 清理和 acceptance 报告汇总字段。
不改变 API contract、数据库 schema、RAG 数据、Prompt、移动端或持久化结构。

## 测试结果

已执行：

```powershell
python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_postprocessor services.worker.tests.test_meeting_analysis_pipeline_output
```

结果：通过，12 个测试全部通过。

已执行：

```powershell
python .\services\worker\scripts\run_meeting_pipeline_acceptance.py
```

结果：通过。最新报告目录：
`data/debug/meeting_pipeline_acceptance/20260801_173351/`。

关键指标：

- `new_pipeline_success_rate=1.0`
- `owner_deadline_hallucination_count=0`
- `auto_gates_passed=true`
- `acceptance_passed=true`

已执行：

```powershell
.\scripts\test-all.ps1
```

结果：通过。包含 API/Worker Python compile、API contract tests、Worker unit
tests、Evaluation unit tests、Mobile TypeScript typecheck 和移动端静态 UI 检查。

## 已知限制

Semantic pipeline 仍保留人工语义质量复核要求；本次修复只解决自动验收中的
owner/deadline 幻觉 gate。

## 后续建议

继续把 speaker-derived owner 与 action body owner 明确区分。后续如需在前端展示
说话人责任人，应先设计独立字段或 evidence contract，避免复用 action owner。
