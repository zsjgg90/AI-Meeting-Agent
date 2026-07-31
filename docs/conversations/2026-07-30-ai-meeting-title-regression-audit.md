# AI Meeting Title Regression Audit

## 开发目标

对第一版 AI 会议标题生成链路做真实/已有验收样例回归审计，确认不会把单条待办、单岗位事项或泛化内容误用作会议标题。

## 背景

上一轮标题优化已在同一次 Qwen3 + RAG 结构化分析输出中增加 `meeting_type`、`meeting_type_confidence`、`meeting_title_candidate` 和 `title_basis`，并通过 Worker 确定性校验后才更新 fallback 标题。本次只审计和微调标题门禁，不新增模型调用，不访问数据库，不改六维分析链路。

## 实现方案

新增离线审计脚本 `services/worker/scripts/run_meeting_title_regression_audit.py`。脚本引用仓库已有 transcript 文件作为样例来源，使用固定的标题字段 payload 调用当前 `meeting_title.py` validator 和 `maybe_apply_ai_title()`，输出 Markdown/JSON 报告到 `data/debug/title_regression/`。

## 修改内容

- 新增标题回归审计脚本。
- 生成 `data/debug/title_regression/20260730_title_regression_report.md` 和 `.json`。
- 发现并修复一个明确漏判：不含时间词但只覆盖单岗位事项的标题，例如 `后端接口优化确认会`。
- 在 `meeting_title.py` 中增加窄范围 role-plus-action 拦截，避免扩大到合法全局标题。
- 补充 Worker fake service 测试对单岗位事项标题的拒绝断言。

## 影响范围

影响 Worker 标题确定性校验和离线审计工具。未修改数据库、API 合同、RAG 数据、六维分析 schema 含义、PostProcessor 或 anti-hallucination Validator。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_title_regression_audit.py`，通过并生成报告。
- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_meeting_analyst_service_fake`，通过。
- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_analysis_contract services.worker.tests.test_meeting_analysis_postprocessor services.worker.tests.test_anti_hallucination_validator`，通过。
- 已执行 `.\scripts\test-all.ps1`，通过。

## 已知限制

本次审计不调用 Qwen3，因此无法衡量新 prompt 在真实模型下生成 `meeting_type`、`meeting_title_candidate` 和 `title_basis` 的概率分布。审计结论只覆盖确定性标题门禁质量。

## 后续建议

第一版可继续用于 RC1 安全门禁。第二版建议在受控环境追加 live Qwen3 样例统计，重点观察模型是否稳定输出足够 basis，以及是否经常把局部事项写入 `meeting_title_candidate`。
