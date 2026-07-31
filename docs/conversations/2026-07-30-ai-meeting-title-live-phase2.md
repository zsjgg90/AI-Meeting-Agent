# AI Meeting Title Live Phase 2 Audit

## 开发目标

对第一版 AI 会议标题生成链路进行第二阶段受控 live 样例统计，验证真实 Qwen3 输出的标题字段稳定性，不扩展功能范围。

## 背景

第一版标题链路已经复用正式 Qwen3 + RAG 结构化分析调用，输出 `meeting_type`、`meeting_type_confidence`、`meeting_title_candidate` 和 `title_basis`，并在 Worker 侧通过确定性校验后才更新 fallback 标题。上一轮离线回归只覆盖 validator，不调用 Qwen3；本轮补充真实模型输出统计。

## 实现方案

新增 `services/worker/scripts/run_meeting_title_live_audit.py`。脚本发现桌面 20 套验收脚本和仓库 `data/debug` 中的真实/验收 transcript，选取 24 场样例，逐场调用现有 `MeetingAnalystService.analyze()`，记录模型标题字段、validator 结果、模拟最终标题、是否 fallback 和人工评价。脚本不访问数据库，不新增标题专用模型请求，不改六维分析链路。

## 修改内容

- 新增 live 标题审计脚本，并输出 Markdown/JSON 报告到 `data/debug/title_regression/20260730_title_live_phase2/`。
- 修复审计脚本样例发现逻辑，排除自身生成的 `data/debug/title_regression/` 输入副本，避免重复把报告缓存当作新样例。
- 修复审计脚本缓存模式，`--reuse-cache` 下不初始化 RAG/LLM，缓存缺失时直接失败。
- 对标题 validator 做最小修复：允许版本号内部点号，例如 `V3.2`，但普通带点标题仍拒绝。
- 补充 Worker fake service 测试，覆盖版本号标题通过和普通点号标题拒绝。

## 影响范围

影响 Worker 标题 validator、Worker 标题测试和离线/live 审计脚本。未修改数据库、API 合同、Prompt、RAG 数据、六维分析 schema 含义或移动端。

## 测试结果

- 已执行 `services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_title_live_audit.py --allow-live-model --limit 24 --ollama-timeout 300 --run-id 20260730_title_live_phase2`，完成 24 场 live Qwen3 样例。
- 已执行 `services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_title_live_audit.py --allow-live-model --limit 24 --ollama-timeout 300 --run-id 20260730_title_live_phase2 --reuse-cache`，使用缓存刷新最终报告。
- 已执行 `services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_title_regression_audit.py`，通过。
- 已执行 `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_meeting_analyst_service_fake`，通过。
- 已执行 `.\scripts\test-all.ps1`，通过。

## 审计结果

24 场样例中，23 个标题为 `accurate` 或 `acceptable`，1 个标题安全回退；Validator 拒绝率 4.17%，安全回退率 4.17%，局部事项误标题率 0%，meeting_type 缺失率 0%，title_basis 缺失或重复率 0%，全部 confidence 落在 `0.90-1.00`。

唯一回退标题为 `V2.4迭代中期问题对齐与下周目标确认会`，原因是同时包含时间词 `下周` 和动作词 `确认`，触发任务型标题规则。该样例覆盖整场会议主题，属于单例规则偏严，未继续增加特例。

## 已知限制

桌面 20 套源文档可由现有稳定性解析器抽取 14 场，其余样例来自仓库已有 debug/acceptance transcript。部分源文档存在 mojibake 文本，但与既有稳定性测试输入一致。

## 后续建议

建议进入第二版多候选与覆盖度评分阶段，重点处理 meeting_type 相邻枚举偏差，以及时间词+动作词规则在会议级标题上的语义误杀。
