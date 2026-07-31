# AI Meeting Title Optimization

## 开发目标

实现第一版 AI 会议标题优化，避免模型把单条待办、截止时间、单个岗位事项或单一风险当成会议标题。

## 背景

RC1 已有同一次 Qwen3 + RAG 分析返回 `meeting_title` 并自动替换系统 fallback 标题的流程，但标题候选缺少会议类型、置信度和依据约束，确定性校验也不足以拦截任务型标题。

## 实现方案

复用现有正式 Qwen3 + RAG 结构化分析调用，在 prompt 和 Worker 内部 schema 中增加 `meeting_type`、`meeting_type_confidence`、`meeting_title_candidate`、`title_basis`。标题更新仍发生在 `save_summary()` 持久化摘要时，只在当前标题仍为 `YYYY-MM-DD HH:mm 实时录音/文件导入` 且未被用户编辑或 AI 更新过时执行。

## 修改内容

- 更新正式 Meeting Analyst prompt，要求输出固定枚举会议类型、类型置信度、标题候选和至少两条标题依据。
- 扩展 Worker 内部 `MeetingAnalysisSchema` 和归一化/持久化 payload，透传标题内部字段。
- 收紧 `meeting_title.py` 确定性校验：拒绝空/过短/过长标题、泛化标题、解释句、JSON/Markdown/换行/非法符号，以及同时包含时间词和动作词的任务型标题。
- 标题自动更新要求 `meeting_type_confidence >= 0.70` 且 `title_basis` 至少两条有效依据。
- 保留旧 `meeting_title` 输入兼容，但优先使用 `meeting_title_candidate`。

## 影响范围

影响 Worker 正式分析 prompt、内部分析 schema、标题校验和摘要持久化 payload。正式六维字段含义、API 合同、数据库结构、移动端展示、RAG 数据和 Validator 规则不变。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_meeting_analyst_service_fake`，通过。
- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_analysis_contract services.worker.tests.test_meeting_analysis_postprocessor`，通过。
- 已执行 `.\scripts\test-all.ps1`，通过。覆盖 API Python compile、Worker Python compile、API contract tests、Worker unit tests、Mobile TypeScript typecheck 和移动端静态 UI 检查。

## 已知限制

标题质量仍依赖同一次模型输出的会议类型和依据。校验失败会保留 fallback 标题，不会尝试从六维字段重新拼接标题，以避免重新引入单条待办误判。

## 后续建议

用真实项目周会、需求评审和项目复盘录音观察标题候选分布；若误拒率偏高，优先调整确定性校验词表和 basis 判定，不新增独立标题模型请求。
