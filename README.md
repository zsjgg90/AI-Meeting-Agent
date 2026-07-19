# 会议声纹识别 AI Agent MVP 1.0

这是一个会议后处理 MVP，用来快速验证从手机录音到后端转写、说话人归并、六维会议纪要和行动项生成的完整链路。

MeetMind AI 面向产品经理、项目经理、研发负责人及中小团队管理者，目标是理解需求评审、项目周会、技术评审、版本规划等会议中的需求、决策、任务、依赖和风险，并跨会议持续追踪项目执行状态。

当前 Release Candidate 正式分析链路为：

```text
Expo -> API -> Worker -> Qwen3 + RAG -> MeetingAnalysisSchema
-> MeetingAnalysisPostProcessor -> AntiHallucinationValidator -> PostgreSQL -> Expo
```

语义事件链路当前处于 shadow mode，仅用于后台诊断和质量对比，不覆盖正式会议纪要：

```text
Transcript -> SemanticEventExtractor -> SemanticEventValidator
Validated Semantic Events -> Topic Event Aggregator -> TopicEventGroup
TopicEventGroup -> SixDimensionMapper -> SixDimensionResult
SixDimensionResult -> SixDimensionValidator -> SixDimensionResult
```

相关模块位于 `services/worker/app/meeting_analysis_pipeline.py`、
`services/worker/app/topic_event_aggregator.py`、
`services/worker/app/six_dimension_mapper.py`、
`services/worker/app/six_dimension_validator.py`。内部 Topic/Event/Validation
结构不会写入数据库或暴露 API。Worker 会在正式 Qwen3 + RAG 输出后尝试运行 shadow
语义链路，并把七级中间结果写入：

```text
data/debug/semantic_pipeline_trace/<meeting_id>/
```

该目录包含 `01_utterances.json` 到 `07_final_meeting_analysis.json` 以及
`comparison.md`，用于定位错误首次出现在哪一层。shadow 链路失败或产出为空不会影响
正式纪要结果。

链路审计报告可写入：

```text
data/debug/chain_audit/<meeting_id>/
```

如果会议 metadata 显示 `model_name=fixture-gold-standard`，说明该会议是人工测试
fixture，不代表正式 Qwen3 + RAG 或语义 shadow 链路输出质量。
Summary metadata also includes `result_source`: `fixture` means a manual gold
answer, `legacy_qwen_rag` means the formal production Qwen3 + RAG path, and
`semantic_pipeline` means semantic shadow/debug output.

Agent v1.0 upgrade work starts from the Phase 0 baseline freeze documented in
`docs/AGENT_V1_PHASE_0_BASELINE.md`. The RC formal path remains the default.
Agent rollout guardrails are available as:

```env
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
```

最终交付文档：

- `PROJECT_FINAL_REPORT.md`
- `DEPLOYMENT.md`
- `RUNBOOK.md`
- `KNOWN_LIMITATIONS.md`
- `ROADMAP.md`
- `SESSION_HANDOFF.md`

## 技术栈

- Mobile: Expo React Native
- API: FastAPI，代码位于 `services/api`
- Worker: 音频转写、说话人聚类、Qwen3 + RAG 会议分析服务，代码位于 `services/worker`
- DB: PostgreSQL + SQLAlchemy
- Migration: Alembic
- Storage: 本地 `storage/` 目录
- AI: 火山引擎/本地 Whisper 转写 + Ollama Qwen3 14B + RAG 六维会议分析

## 目录结构

```text
.
├── docker-compose.yml
├── .env.example
├── storage/
├── services/
│   └── api/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── alembic.ini
│       ├── alembic/
│       └── app/
│   └── worker/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
├── apps/
│   └── mobile/
└── mobile/
```

移动端新实现位于 `apps/mobile`，旧 `mobile` 目录为早期原型。

## 启动后端

复制环境变量文件：

```bash
cp .env.example .env
```

如需正式会议分析，需要本地 Ollama 已安装并拉取：

```bash
ollama pull qwen3:14b
```

Docker 启动 PostgreSQL、FastAPI 和 Worker：

```bash
docker compose up --build
```

API 容器启动时会先执行：

```bash
alembic upgrade head
```

Docker 访问地址：

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Worker: http://localhost:8001
- Worker health: http://localhost:8001/health

Windows 本地开发默认端口：

- API: http://127.0.0.1:8002
- Worker: http://127.0.0.1:8001
- Expo: http://127.0.0.1:8081

本地启动：

```powershell
.\services\worker\start-worker-local.ps1
.\services\api\start-api-local.ps1
cd apps\mobile
npx expo start --host lan --port 8081
```

本地验证：

```powershell
.\scripts\test-all.ps1
.\scripts\check-services.ps1
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_meeting_pipeline_acceptance.py --limit 3 --ollama-timeout 60
services\worker\.venv\Scripts\python.exe services\worker\scripts\run_real_production_analysis.py --meeting-id meeting_001 --ollama-timeout 600
```

`run_meeting_pipeline_acceptance.py` 会使用真实 Qwen3/Ollama 和现有 RAG
对比语义候选链路与旧 Qwen3 + RAG 链路，报告输出到
`data/debug/meeting_pipeline_acceptance/`。该脚本属于 live gate，不纳入默认
`test-all.ps1`。当前正式 Worker 输出仍以旧 Qwen3 + RAG 为准。
`run_real_production_analysis.py` uses the current V3.2 `meeting_001`
transcript by default and writes transcript, RAG context, prompt, raw model
output, normalized result, and pipeline log under
`data/debug/real_production_analysis/<meeting_id>/`.
The current `meeting_001` quality audit is saved as
`data/debug/real_production_analysis/meeting_001/quality_audit.md`.
The same directory may also contain Validator-only regression artifacts:
`validated_result.json` and `validator_audit.md`. These are produced from the
existing raw model output without re-calling Qwen3 and record agenda compression,
continuous evidence repair/rejection, duplicate removal, and action metadata
cleanup before persistence.
Prompt regression artifacts for the optimized legacy Qwen3 + RAG prompt are
written as `model_raw_output_v2.json`, `normalized_result_v2.json`, and
`quality_audit_v2.md` in the same directory.
Multi-meeting prompt stability regression is available via
`services/worker/scripts/run_prompt_stability_eval.py`. It repeats each selected
meeting twice with the same Qwen3 model, Prompt, and RAG settings, then writes
`run_1_result.json`, `run_2_result.json`, `comparison.json`, and aggregate
`stability_report.json/.md` under `data/debug/prompt_stability_eval/`.
Each run also saves `normalized_before_postprocess.json`,
`postprocessed_result.json`, and `validated_result.json` under a per-run
subdirectory so schema normalization, deterministic postprocessing, and
Validator effects can be audited separately. The current 2026-07-18 stability
report did not pass the production gate; see
`docs/KNOWN_ISSUES.md` before treating the prompt as production-ready.

本地端到端流程至少需要：

- `OLLAMA_MODEL=qwen3:14b`：正式 Meeting Analyst 模型
- `RAG_COLLECTION_NAME=meeting_analyst_rules`：正式规则检索集合
- `OLLAMA_TIMEOUT_SECONDS=600`：Worker 单次 Ollama 请求超时，真实分析日志会记录该值和实际耗时
- `WORKER_REQUEST_TIMEOUT_SECONDS=600`：API 等待 Worker 处理/分析的最长时间，超时后任务会落入失败态，避免 APP 长时间停留在“分析中”
- `VOLCENGINE_ASR_API_KEY`：可选，用于火山引擎 ASR；未配置时回退到其他转写 provider
- `HUGGINGFACE_TOKEN`：可选，用于 pyannote 说话人分离；不配置时仍会转写和总结，但 `speaker_label` 可能为空

Worker 模型配置：

```env
TRANSCRIPT_PROVIDER=auto
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
VOLCENGINE_ASR_API_KEY=
VOLCENGINE_ASR_RESOURCE_ID=volc.seedasr.auc
VOLCENGINE_REALTIME_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
VOLCENGINE_ENABLE_SPEAKER_INFO=true
VOLCENGINE_ENABLE_GENDER_DETECTION=true
WHISPER_MODEL_SIZE=small
REALTIME_WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=zh
WHISPER_INITIAL_PROMPT=以下是普通话会议录音，请准确转写为简体中文，保留人名、项目名、数字和专业术语。
HUGGINGFACE_TOKEN=
OLLAMA_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TIMEOUT_SECONDS=600
OLLAMA_TEMPERATURE=0
OLLAMA_TOP_P=0.2
OLLAMA_SEED=42
OLLAMA_FORMAT=json
RAG_ENABLED=true
RAG_COLLECTION_NAME=meeting_analyst_rules
RAG_EMBEDDING_LOCAL_FILES_ONLY=true
AGENT_MODE_ENABLED=false
AGENT_SHADOW_MODE=true
AGENT_ACTIONS_ENABLED=false
```

Formal legacy Qwen3 + RAG summaries are normalized, then passed through
`services/worker/app/meeting_analysis_postprocessor.py`, then through
`anti_hallucination_validator.py` before persistence. The deterministic
postprocessor only filters, deduplicates, sorts, clears unsupported metadata,
and enforces dimension boundaries; it does not create or rewrite meeting facts.
Worker loads the RAG embedding model from the local Hugging Face cache by
default. Keep `RAG_EMBEDDING_LOCAL_FILES_ONLY=true` for local production
analysis so a manually started Worker does not block on network model metadata
requests. Summary analysis also commits speaker-name backfill before entering
RAG/Qwen inference, so long model calls do not hold transcript row locks.

`WHISPER_MODEL_SIZE` 可改为 `medium` 以进一步提升准确率，但 CPU 转写会明显变慢。
`TRANSCRIPT_PROVIDER=auto` 会优先使用豆包/火山引擎 ASR 新版控制台鉴权 `VOLCENGINE_ASR_API_KEY`；会后完整音频默认使用 `volc.seedasr.auc`，实时字幕分片默认尝试 `volc.seedasr.sauc.duration`，并通过 `VOLCENGINE_ENABLE_SPEAKER_INFO=true` 开启说话人聚类，通过 `VOLCENGINE_ENABLE_GENDER_DETECTION=true` 开启男女音色识别。未配置豆包凭证时使用 OpenAI 高准确率转写；云端调用失败时自动回退到本地 faster-whisper。也可以设置为 `volcengine`、`openai` 或 `faster_whisper` 强制指定。

## 启动移动端

```bash
cd apps/mobile
cp .env.example .env
npm install
npm run start:dev
```

移动端 API 地址从 `.env` 读取：

```env
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000
```

如果使用真机 Dev Client，请把 `localhost` 改为电脑的局域网 IP，例如：

```env
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000
```

### 实时字幕真机调试

当前实时字幕使用豆包流式会议字幕资源 `volc.seedasr.sauc.duration`，移动端通过原生录音流按 200ms 推送 16kHz、mono、PCM 16-bit 小包。该能力依赖 `@siteed/audio-studio` 原生模块，普通 Expo Go 无法加载，需要使用 Expo Development Build。

后端实时字幕 WebSocket：

```text
ws://{API_HOST}/meetings/{meeting_id}/realtime-stream
```

移动端流程：

1. 点击开始录音后，APP 打开 WebSocket。
2. 每 200ms 推送一包 PCM 音频。
3. API 桥接豆包流式 ASR，并开启 `enable_speaker_info=true`、`enable_gender_detection=true`。
4. API 实时写入 `transcript_segments`，包含 `speaker_label` 和 `speaker_gender`。
5. 录音结束后，APP 仍会上传完整 WAV 音频，走会后高准确率处理和会议纪要生成。

iOS 真机需要使用 EAS 生成开发构建：

```bash
cd apps/mobile
npx expo install expo-dev-client
npx eas build --profile development --platform ios
```

Android 本地可用：

```bash
cd apps/mobile
npx expo prebuild
npx expo run:android
```

## 后端接口

- `POST /meetings` 创建会议
- `GET /meetings` 获取会议列表
- `GET /meetings/{id}` 获取会议详情
- `POST /meetings/{id}/audio` 上传音频文件
- `WS /meetings/{id}/realtime-stream` 实时字幕流式转写
- `POST /meetings/{id}/process` 触发会议处理
- `POST /meetings/{id}/analyze` 触发 Meeting Analyst Agent Pipeline
- `GET /meetings/{id}/transcript` 获取转写结果
- `GET /meetings/{id}/summary` 获取六大维度结构化会议分析
- `PUT /meetings/{id}/speakers/{speaker_label}` 保存 `speaker_label -> display_name` 映射

`GET /meetings/{id}/summary` 返回结构：

```json
{
  "meeting_agenda": [],
  "meeting_summary": "",
  "key_conclusions": [],
  "action_items": [],
  "unresolved_issues": [],
  "risks_and_focus": [],
  "topics": [],
  "metadata": {}
}
```

Meeting Analyst Agent Pipeline 包含 Transcript Cleaner、Semantic Label Agent、Topic Chunk Agent、六大维度 Agent、边界校验 Rule Engine 和 JSON Schema 校验。

## 快速验证

创建会议：

```bash
curl -X POST http://localhost:8000/meetings \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"MVP Demo Meeting\"}"
```

获取会议列表：

```bash
curl http://localhost:8000/meetings
```

上传音频：

```bash
curl -X POST http://localhost:8000/meetings/{meeting_id}/audio \
  -F "file=@sample.m4a"
```

音频上传支持 `m4a`、`mp3`、`wav`，文件会保存到：

```text
storage/meetings/{meeting_id}/audio/
```

数据库会记录文件路径、文件大小和上传时间，接口返回 `audio_file_id`。

触发处理：

```bash
curl -X POST http://localhost:8000/meetings/{meeting_id}/process
```

查询转写：

```bash
curl http://localhost:8000/meetings/{meeting_id}/transcript
```

查询纪要：

```bash
curl http://localhost:8000/meetings/{meeting_id}/summary
```

## 端到端流程检查

1. 在 APP 首页点击 `New`。
2. 输入会议名称并创建会议。
3. 进入录音页，点击 `Start Recording`。
4. 可点击 `Pause` / `Resume`，完成后点击 `End`。
5. 点击 `Upload Audio`，APP 会上传音频并调用 `POST /meetings/{id}/process`。
6. API 创建处理任务，并在后台调用 worker。
   如果同一会议已有 `queued` 或 `running` 任务，API 会返回现有任务，避免重复排队。
7. Worker 读取 `storage/meetings/{meeting_id}/audio/` 中最新上传的音频。
8. Worker 使用 `faster-whisper` 写入 `transcript_segments`。
9. 如果豆包返回 `spk_0/spk_1`，worker 会保存为 `Speaker 1/Speaker 2`；如果没有 provider 说话人信息且配置了 `HUGGINGFACE_TOKEN`，worker 使用 `pyannote.audio` 兜底分离说话人。
10. Worker 调用 LLM summary agent，写入 `meeting_summaries` 和 `action_items`。
11. APP 会议详情页会自动刷新处理中状态，并显示转写文本、AI 总结、决策和待办事项；会议议程、核心结论、遗留问题、待办与后续安排、风险与关注点以共享 `NumberedList` 有序编号列表展示。前端会先把 `1. 内容A；2. 内容B`、`1、内容A`、多行文本和分号分隔文本拆成独立条目，并去掉原始编号。
12. 在会议详情页的发言人名称区域，可以把 `Speaker 1/Speaker 2` 保存为真实姓名；后端会保存 `speaker_label -> display_name` 映射，APP 会用真实姓名显示转写和纪要。

## MVP 限制

- 不做实时入会或真实声纹注册。
- 当前已支持录音页实时字幕，但需要 Development Build，不能使用普通 Expo Go。
- `Speaker 1 / Speaker 2 / Speaker 3` 来自豆包说话人聚类或后端兜底分离，不等于真实身份识别。
- 未配置 `OPENAI_API_KEY` 时，后端仍可启动，但 `/process` 后任务会失败并记录错误。
- RAG 目前只保存文本块，暂不做 embedding 和向量检索。

## Worker 转写

先确保数据库已执行 Alembic migration，然后运行：

```bash
docker compose run --rm worker python -m app.transcribe_meeting {meeting_id}
```

Worker 会读取该会议最新上传的音频文件，使用 `faster-whisper` 转写，再用 `pyannote.audio` 做说话人分离，并写入 `transcript_segments` 表。每个 segment 包含 `start_time`、`end_time`、`text`、`speaker_label`，当前 speaker 只显示 `Speaker A/B/C` 这类 MVP 标签。

生成结构化会议总结：

```bash
docker compose run --rm worker python -m app.summarize_meeting {meeting_id}
```

Summary agent 会读取 transcript segments，调用 LLM 输出结构化 JSON，并保存到 `meeting_summaries` 和 `action_items` 表。若 JSON 解析失败，会自动重试一次。
