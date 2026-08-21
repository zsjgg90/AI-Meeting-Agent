# Semantic Pipeline Comparison: d17102d5-a7b0-41da-9597-8d7623c8afb2

## Original

产品经理: 本次评审企业知识库权限需求，目标是支持按部门和项目控制文档可见范围，并在移动端展示权限不足提示。
研发负责人: 部门维度可以复用现有组织架构，项目维度需要新增一层资源绑定关系。第一版建议只支持查看权限，不做编辑权限。
前端: 移动端需要接口返回权限状态和不可见原因，否则只能展示通用提示。权限变更后是否需要实时刷新还没有明确。
测试: 需要补充跨部门、跨项目、离职成员和临时成员四类场景。权限缓存如果存在延迟，也要有可验证的规则。
产品经理: 本期确认只做查看权限，编辑权限进入后续版本。研发输出接口字段方案，前端补充权限不足页面，测试整理四类权限用例。实时刷新策略先作为遗留问题继续评估。

## First Error Stage

| error_type | first_stage | suggestion | evidence |
| --- | --- | --- | --- |
| greeting_as_agenda | not_found | Fix six-dimension mapper/validator routing. |  |
| progress_as_decision | not_found | Fix six-dimension mapper/validator routing. |  |
| flow_talk_as_summary | not_found | Fix six-dimension mapper/validator routing. |  |
| commitment_inflated_as_action | not_found | Fix six-dimension mapper/validator routing. |  |
| agenda_as_risk | not_found | Fix six-dimension mapper/validator routing. |  |
| mitigation_as_risk | not_found | Fix six-dimension mapper/validator routing. |  |
| confirmed_conclusion_as_summary | not_found | Fix six-dimension mapper/validator routing. |  |

## Stage Files

- `00_speaker_contexts.json`
- `01_utterances.json`
- `02_semantic_events_raw.json`
- `03_semantic_events_validated.json`
- `04_topic_groups.json`
- `05_six_dimension_mapped.json`
- `06_six_dimension_validated.json`
- `08_responsibility_evidence_matrix.json`
- `memory_snapshot.json`
- `retrieved_memory_context.json`
- `memory_retrieval_audit.json`
- `reasoning_contexts.json`
- `reasoning_audit.json`
- `action_candidates.json`
- `tool_action_contracts.json`
- `action_audit.json`
- `workflow_state_observations.json`
- `workflow_recommendations.json`
- `workflow_audit.json`
- `07_final_meeting_analysis.json`