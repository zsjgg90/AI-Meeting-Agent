# Production Analysis Stall Fix

## 开发目标

修复 Expo 最近会议一直 loading / 分析失败的问题，并恢复真实会议
`73c47be6-0ea0-41eb-ac73-81e458574abd` 的六维纪要生成。

## 背景

该会议已有 48 段有效中文转写，但 `transcription_tasks.error_message`
为 `timed out`，会议状态为 `failed` 或 `summarizing`，且没有
`meeting_summaries` 记录。直接调用 Worker `/analyze` 曾在 900 秒客户端
超时，且 `ollama ps` 为空，说明请求没有进入 Qwen 推理。

## 实现方案

采用最小修复：

1. 释放早期超时请求遗留的 Postgres transcript 行锁。
2. 调整 Worker summary orchestration，把 `speaker_name` 回填提交为短事务，
   再进入 RAG/Qwen 长分析。
3. 让 RAG embedding 模型默认从本地 Hugging Face cache 加载，避免手动启动
   Worker 时阻塞在网络模型元数据请求。

## 修改内容

- `services/worker/app/summary_agent.py`：`speaker_name` 回填后立即
  `db.commit()`，避免长模型调用持有 `transcript_segments` 行锁。
- `services/worker/app/config.py`：新增
  `rag_embedding_local_files_only: bool = True`。
- `services/worker/app/rag_retriever.py`：加载 `SentenceTransformer` 时传入
  `local_files_only=settings.rag_embedding_local_files_only`。
- `.env.example`、`README.md`、`docs/CONFIGURATION.md`、`docs/CURRENT_TASKS.md`、
  `docs/changelog.md`、`docs/KNOWN_ISSUES.md`、`SESSION_HANDOFF.md`、
  `AGENTS.md`：同步维护说明。

## 影响范围

影响 Worker 会议分析前置准备和 RAG embedding 初始化。未修改 Prompt、RAG
数据、Validator、Schema、数据库结构、API 契约或前端展示逻辑。

## 测试结果

- `services\worker\.venv\Scripts\python.exe -m unittest services.worker.tests.test_prompt_rag_versioning`：通过，5 tests。
- `services\worker\.venv\Scripts\python.exe -m unittest discover -s services\worker\tests`：通过，32 tests。
- RAG 初始化复测：不额外设置 HF 离线环境时，`RagRetriever` 初始化约
  6470 ms，RAG 检索约 38 ms，Prompt 长度约 8108 chars。
- Worker `/ready`：通过，database/prompt/ollama/rag 均 ok。
- 真实会议 Worker `/analyze`：通过，耗时约 40352.66 ms，生成 summary
  `33db99a1-634d-4d57-b28b-f720c4d9bcde`。
- `scripts\check-services.ps1`：失败，原因是脚本检查历史 API 端口 8002，
  当前实际手机/API 会话使用 8000；Worker/Ollama/Postgres/Expo 检查通过。

## 已知限制

- 本次只修复卡死和失败状态恢复，不评估或调整六维内容质量。
- 当前生成结果的议程数量为 1，属于后续质量评估范围，不在本次修复内。
- 服务检查脚本与当前手动 API 端口存在差异，需要后续统一。

## 后续建议

优先统一本地 API 端口与 `scripts/check-services.ps1`、Expo `.env`、
启动脚本中的端口配置，避免运行态诊断和手机实际连接目标不一致。
