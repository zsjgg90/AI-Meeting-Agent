# Agent v1 Phase 5B Live Shadow Acceptance Tool

## 开发目标

新增独立的真实 Qwen3 14B + RAG Shadow 验收工具，用于在显式授权后串行验证
Agent Shadow 的真实输出质量、耗时、GPU 压力、timeout/fallback/error、Validator
稳定性和正式结果隔离。

## 背景

Agent v1 Phase 5 已完成三类核心场景的离线 Shadow acceptance，但该阶段只验证
fixture 结构、静态计划命中和离线报告能力，不代表真实 Qwen3/RAG 质量或性能。Phase
5B 需要先实现可控 live gate 工具，等待确认后再运行真实模型。

## 实现方案

- 新增 `services/worker/scripts/run_agent_shadow_live_acceptance.py`。
- 复用 Phase 5 fixtures、`AgentOrchestrator`、静态 Runtime 思路、现有 RAG、
  Qwen3、PostProcessor、Validator 和 debug artifact 设计。
- 默认不调用真实模型；只有传入 `--allow-live-model` 才进入真实 RAG/Qwen3 分层捕获。
- 支持 `smoke`、`full`、`--meeting-id`、`--scenario`、`--ollama-timeout`、
  `--gpu-monitor`、`--gpu-sample-interval` 和 `--stop-on-failure`。
- 每场串行执行，输出完整 per-meeting artifacts；不可用中间层写入
  `available=false`，不伪造内容。
- 使用 `nvidia-smi` 可选采集 GPU 指标，采集失败只记录 warning，不阻断 Shadow。
- 使用正式结果快照哈希验证 fixture formal result 未被 Shadow 修改。

## 修改内容

- 新增 Phase 5B live acceptance runner。
- 新增 `services/worker/tests/test_agent_shadow_live_acceptance.py`。
- 将 Phase 5B 测试加入 `scripts/test-all.ps1` 默认 Worker 门禁。
- 更新 README、当前任务、变更日志、测试文档和会话交接文档。

## 影响范围

影响范围限定在 Worker 脚本、Worker 单元测试和文档。未修改 Prompt、RAG 数据或检索
规则、Validator、API、数据库、Migration、Expo、正式分析链路、Agent 结果提升或
Agent Action 执行。

## 测试结果

已执行：

```powershell
services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_agent_shadow_live_acceptance
```

结果：通过 11 项测试。

真实 Qwen3/RAG Shadow 验收未执行，等待用户确认后再运行。

## 已知限制

- 默认离线模式只验证工具结构、选择逻辑、artifact 写入和安全边界，不代表真实模型质量。
- GPU 监控依赖本机 `nvidia-smi`，失败时仅记录 warning。
- Tool timeout 仍不能强杀已阻塞的底层同步调用，真实模型请求主要依赖 Ollama requests timeout。
- 质量评分为规则辅助初评分，必须人工复核。
- 当前正式结果隔离验证基于 fixture formal result 快照；真实数据库隔离仍需后续在服务态验收中结合 DB/API 证据。

## 后续建议

1. 先审阅 Phase 5B 工具实现和离线测试结果。
2. 确认本机 Ollama、`qwen3:14b`、RAG/Chroma、embedding 本地缓存和 GPU 状态。
3. 先运行 3 场 smoke，全部通过后再运行 9 场 full。
4. 在 Phase 5B 通过前不要进入 Phase 6。

## Phase 5B GPU Summary Regression

- Fixed GPU summary parsing for `nvidia-smi --format=csv` output whose headers
  contain spaces after commas, for example `timestamp, memory.used [MiB]`.
- The parser now uses `csv.DictReader(..., skipinitialspace=True)` and strips
  field names before looking up `memory.used [MiB]`, `memory.total [MiB]`,
  `utilization.gpu [%]`, `temperature.gpu`, and `power.draw [W]`.
- Missing, blank, or `N/A` values remain non-fatal and are not fabricated.
- Worker live acceptance should be started with stdout/stderr captured under
  `data/debug/agent_shadow_live_acceptance/worker-phase5b.log`. If Worker keeps
  port 8001 open but `/health` or `/ready` timeout, preserve that log and
  collect a process/thread stack snapshot before changing Worker business
  logic.

## Phase 5B Full Live Acceptance Result

- Local artifact: `data/debug/agent_shadow_live_acceptance/20260720-163624`.
  This directory is local acceptance evidence only and is ignored by Git.
- Completed 9/9 meetings with `overall_passed=true`.
- Average quality score was 95.78; minimum quality score was 90.
- Cold start was about 42.69 seconds; warm start average was about 28.96
  seconds.
- timeout, fallback, and error counts were all 0.
- CUDA OOM count was 0.
- Formal-result isolation passed for 9/9 meetings.
- Worker `/health`, Worker `/ready`, and Ollama were healthy after the run.
- Meetings 2-9 did not show sustained monotonic GPU memory growth; the first
  meeting reflected Qwen model cold-load GPU cache behavior.
- RAG returned the same 8 chunks in all 9 meetings, which is a retrieval
  diversity observation for later work.
- Quality scoring remains rule-assisted and keeps `manual_review_required=true`.
