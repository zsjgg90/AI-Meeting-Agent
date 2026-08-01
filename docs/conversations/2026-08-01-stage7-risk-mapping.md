# Stage7.2 Semantic Boundary Optimization

## 开发目标

完成 rag-v2.1.1 Stage7.2 Semantic Boundary 优化，修复 non-final decision、conditional risk、requirement/action 与 unresolved issue 的边界规则。

## 背景

Stage7.1 Golden Dataset Evidence Grounding 完成后，回归指标为：

- Decision Precision: `0.4000`
- Task Recall: `0.3667`
- Risk Recall: `0.8000`
- Hallucination Rate: `0.0500`
- Evidence Coverage: `0.9500`

剩余问题集中在条件讨论误入 decision、建议误入 key conclusions、流程要求误入 unresolved issue、条件风险未稳定进入 risks。

## 实现方案

本次采用最小改动方案，不修改 Golden Dataset、Prompt、RAG、Schema 或架构。修改集中在三处：

- `anti_hallucination_validator.py`：正式 legacy Qwen3 + RAG 输出后处理边界。
- `semantic_event_validator.py`：semantic event intent 校验边界。
- `meeting_analysis_pipeline.py`：规则 fast path intent 判断。

## 修改内容

- 新增 non-final decision 过滤：`再确定最终方向`、`后续确定`、`继续评估`、`暂不确认`、`暂不决定`、`初步怀疑`、`还没有最终确认`、`不能直接确认`、`待进一步评估` 不允许进入 `key_conclusions`。
- 对 non-final decision 执行保守转移：存在未决信号时转入 `unresolved_issues`；存在明确行动要求时转入 `action_items`；否则删除。
- 扩展 conditional risk 支持：`可能影响`、`可能导致`、`受到影响`、`如果...可能...`、`如果...导致...`、`否则`、`返工`、`投诉`、`失败`。
- 增加风险措辞保守化：source 是可能性表达时，移除 actual risk 中的确定性强化。
- 扩展 weak unresolved 过滤：`需要同步`、`需要补充`、`需要更新`、`需要提交`、`需要排查`、`需要验证`、`需要评估` 归为 requirement/action，不作为 unresolved issue。
- 调整 semantic event confirmation patterns，避免 `确定` 单字触发 decision，保留 `确定方案`、`确认采用`、`决定执行`、`达成一致` 等强确认。
- 同步 fast path `_rule_intent()`，避免弱决定表达进入 decision，并补充条件风险与未决信号。

## 影响范围

影响范围限定在 Worker 分析边界规则和单元测试。未修改 API、数据库、Prompt、RAG、Golden Dataset 或移动端。

## 测试结果

- 已执行：`python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_pipeline_output`
- 结果：通过，14 tests OK。

## Golden Regression 结果

已重新执行 5 个 Stage7 Golden Regression report 生成命令。由于评估脚本读取的是既有静态 `actual_after.json`，本次代码优化不会自动改变这些 actual 产物，因此整体指标与 Stage7.1 保持一致：

- 平均 Decision Precision: `0.4000`
- 平均 Task Recall: `0.3667`
- 平均 Risk Recall: `0.8000`
- 平均 Hallucination Rate: `0.0500`
- 平均 Evidence Coverage: `0.9500`

## 已知限制

- 需要重新运行正式 pipeline 生成新的 `actual_after.json` 后，才能观察 Stage7.2 规则对 Golden Regression 指标的真实影响。
- 当前 static regression 仍保留 `board_strategy_001` 的 unsupported unresolved issue 和决策边界残留。

## 后续建议

可以进入 Stage7.3，前提是 Stage7.3 首先重新生成 Golden actual 输出并验证 Stage7.2 规则效果，再决定是否继续优化 model-side task wording alignment 和剩余 decision false positives。
