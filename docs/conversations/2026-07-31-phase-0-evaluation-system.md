# Phase 0 Evaluation System

## 开发目标

建立 AI 会议分析质量评测基础设施，只实现离线评测框架，不接入生产会议分析流程。

## 背景

当前正式分析链路仍为 Qwen3 + RAG 输出 `meeting-analysis-v1` 六维结构，经
PostProcessor 和 AntiHallucinationValidator 后持久化。项目需要一个独立评测层，
用于比较人工标准答案与 AI 实际输出，但不能修改 ASR、Semantic Pipeline、RAG、
Prompt、Qwen3 调用、API、数据库或 Mobile。

## 实现方案

新增 `data/eval/` 下的评测资产目录，定义独立 evaluation case schema，并新增
`scripts/evaluate_meeting_analysis.py` 作为纯离线 CLI。脚本读取已有
`expected.json`、`actual.json` 和可选 transcript 文件，使用确定性文本归一化匹配
计算 Phase 0 指标，并生成 Markdown baseline report。

## 修改内容

- 新增 `data/eval/README.md`。
- 新增 `data/eval/schema/evaluation_case.schema.json` 和说明文档。
- 新增 `data/eval/metrics/README.md`。
- 新增 `data/eval/reports/baseline_v1.0_RC1.md` 占位基线报告。
- 新增 `scripts/evaluate_meeting_analysis.py`。
- 新增 `tests/test_evaluate_meeting_analysis.py`。
- 更新 README、TESTING、PROJECT_STATE、CURRENT_TASKS、CHANGELOG 和
  SESSION_HANDOFF 中的评测体系说明。

## 影响范围

评测框架只读取本地 JSON/TXT 文件并输出本地报告。未修改生产 `MeetingAnalysisSchema`、
API contract、数据库迁移、Worker 分析链路、Prompt、RAG、Validator、ASR、
Semantic Pipeline 或 Mobile。

## 测试结果

已执行：

```powershell
python -m unittest tests.test_evaluate_meeting_analysis
```

结果：3 个测试通过。

## 已知限制

Phase 0 指标采用归一化文本包含/相等匹配和连续 `source_text` 证据覆盖判断，适合作为
基础设施与回归门禁，不等同于最终语义评分。

## 后续建议

- 补充真实且脱敏的 `meeting_cases` 样本。
- 引入人工复核后的 expected/actual baseline 数据。
- 在后续阶段评估语义相似度指标，但继续保持与生产链路解耦。
