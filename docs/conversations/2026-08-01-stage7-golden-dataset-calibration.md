# Stage7.1 Golden Dataset Evidence Grounding Calibration

## 开发目标

校准 `data/eval/golden_cases/` 下 5 个 Stage7 Golden Case 的 `expected.json`，使人工真值严格遵循 evidence grounding 原则。

## 背景

Stage7 初版回归显示平均 Evidence Coverage 为 `0.9500`，但 Task Recall 为 `0.0000`。复核后确认部分 expected action、decision、risk 标注包含 transcript 未直接支持的任务、owner、deadline 或推断风险，需要先校准 Golden Dataset，再继续优化 pipeline。

## 实现方案

本阶段只修改 Golden Dataset 的 `expected.json` 和评估报告，不修改 pipeline、validator、RAG、prompt、schema、API 或数据库。校准规则如下：

- decision 必须有明确决定表达。
- action item 必须有明确任务动作、承诺/指派或行动要求。
- owner、deadline 不允许推断。
- risk 必须来自明确风险表达或条件风险表达。
- unresolved issue 必须是真正未解决事项，不包含普通流程要求。

## 修改内容

### ai_meeting_agent_001

- 保留 `短期先优化分析流程` 作为短期方向结论。
- 将 action 校准为 `优化分析流程`、`继续评估模型架构调整`、`确定数据链路优化优先级`，并清空推断 owner/deadline。
- 删除原 action 的推断 owner `产品团队` 和 deadline `待确认`。
- 删除 `分析结果遗漏任务风险`，因为 transcript 只陈述存在任务遗漏，没有明确风险表达。
- 增加 `数据链路优化优先级尚未确定` 作为真实 unresolved issue。

### board_strategy_001

- 删除 `暂不确定最终方案` 的 key conclusion，因为 `再确定最终方向` 表示未决，不是决定。
- 将 action 校准为 `评估不同方案收益和成本`，并清空推断 owner/deadline。
- 保留 `最终增长方向尚未确定` 作为 unresolved issue。
- 保留条件风险 `减少市场投入可能影响增长速度`。

### design_review_001

- 保持 key conclusions 为空，避免将卡片式布局建议升级为决定。
- 将 action 校准为 `结合数据验证设计方向`，并清空推断 owner/deadline。
- 保留 `最终设计方案未确认` 作为 unresolved issue。
- 删除 `组件规范未提前同步可能影响开发` 风险，因为 transcript 只说需要提前同步组件规范，没有说明影响开发。

### project_delivery_001

- 保留 `优先执行当前可落地方案` 作为被后续 `这个方向先推进` 支持的短期方向结论。
- 删除 action `客户成功 / 整理数据和反馈样本 / 待确认`，因为 transcript 不支持该任务、owner 或 deadline。
- 保留 `底层重构是否启动尚未确定`。
- 保留 `方案延期可能影响交付节奏`，证据为 `时间风险比较高`。

### tech_incident_001

- 删除 `当前无法确认具体根因` key conclusion，因为 `初步怀疑` 和 `还没有最终确认` 不是决定。
- 将 action 校准为 `继续排查事故原因` 和 `补充长期监控机制`，并清空推断 owner/deadline。
- 保留 `事故根因未确定` 和 `安全攻击可能性仍需继续排查` 作为 unresolved issues。
- 删除 `缺少长期监控机制` 风险，因为 transcript 只表达补充要求，没有明确风险后果。

## 影响范围

- 修改 5 个 Golden Case 的 `expected.json`。
- 重新生成 `data/eval/reports/stage7_golden_regression/` 下 5 个 case 的 `.md` / `.json` 评估报告。
- 更新 `data/eval/reports/stage7_golden_regression/summary.md`。

## 测试结果

- 已执行：`python -m unittest services.worker.tests.test_anti_hallucination_validator services.worker.tests.test_meeting_analysis_pipeline_output`
- 结果：通过，9 tests OK。
- 已执行：逐 case 运行 `scripts/evaluate_meeting_analysis.py` 重新生成 Stage7 Golden Regression 报告。
- 结果：5 个 case 报告均生成成功。

## 指标结果

- 平均 Decision Precision: `0.4000`
- 平均 Task Recall: `0.3667`
- 平均 Risk Recall: `0.8000`
- 平均 Hallucination Rate: `0.0500`
- 平均 Evidence Coverage: `0.9500`

## 已知限制

- `board_strategy_001` 仍有一个 actual unresolved evidence item 无法通过连续证据校验。
- `board_strategy_001` 的风险语义被 actual 强化为“导致增长速度下降”，与 expected 的条件风险“可能影响增长速度”不完全匹配。
- `tech_incident_001` 仍暴露模型将排查事项升级为 decision 的问题。

## 后续建议

可以进入 Stage7.2 Risk Mapping 优化，重点处理条件风险措辞、无证据 unresolved issue 过滤、以及 incident/strategy 场景下非最终决定的边界清理。
