import json
import re
import sys
from pathlib import Path

import chromadb
import requests
from sentence_transformers import SentenceTransformer


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.worker.app.anti_hallucination_validator import (
    validate_meeting_analysis,
)


DB_DIR = PROJECT_ROOT / "data" / "vector_db"
COLLECTION_NAME = "meeting_analyst_rules"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"


TEST_TRANSCRIPT = """
短视频素材工具V2.0需求对话

产品小A：今天我们快速对齐一下短视频素材工具V2.0的优化需求。目前线上用户反馈最多的两个问题，一是素材批量下载功能卡顿、经常下载失败，二是素材分类标签混乱，用户找素材效率极低。本次迭代的核心目标，就是提升素材工具的使用流畅度，降低用户操作投诉率，同时新增素材智能推荐功能，提升用户留存。本次我提的需求主要有三个，第一，优化批量下载接口，支持一次性最多五十条素材批量下载；第二，重构素材分类标签体系，支持自定义标签、标签筛选、标签搜索；第三，首页新增个性化素材推荐模块，根据用户浏览习惯推送内容。你这边评估下整体落地难度和开发周期。

研发小B：好的，我针对这三个需求逐一评估。首先，批量下载接口优化和素材标签体系重构，这两个功能技术难度不高，现有架构完全可以支撑，没有底层兼容问题。但是首页智能推荐模块有个问题，目前我们后台没有搭建用户行为数据统计体系，没有浏览、点击、收藏的用户数据，直接做智能推荐的话，只能实现随机推荐，达不到个性化推荐的业务效果，属于无效功能迭代。另外我确认一下，本次优化是否需要兼容旧版本历史数据，比如用户之前自定义的旧标签数据？

产品小A：我明白你的问题，数据体系确实还没搭建。那我们做需求取舍，V2.0正式版本先砍掉智能个性化推荐功能，避免功能鸡肋、浪费开发资源，这个功能延后迭代。后续数据体系搭建完成后，我们再单独排期上线。关于旧数据，必须百分百兼容，所有用户历史自定义标签、收藏素材数据，需要无缝迁移，不能出现数据丢失、错乱的情况。另外我这边希望本次版本能在8月1日前上线，配合平台短视频创作活动。

研发小B：没问题，砍掉个性化推荐后，整体开发工作量大幅减少。我梳理了一下，接口优化、标签重构、旧数据适配、页面适配优化，整体开发、自测、联调大概20天，完全可以保证8月1日前上线。另外我补充两个落地细节，第一，新标签体系上线后，需要产品输出明确的默认标签分组规则；第二，批量下载需要限制单次下载频率，防止高频请求导致服务器压力过大，这个限制规则需要产品明确标准。

产品小A：这两个细节我后续全部补充进需求文档，明确标签默认规则、下载频率限制阈值。除此之外，本次迭代还有其他技术风险或者落地难点吗？

研发小B：没有其他技术难点了。唯一需要注意的风险是，本次涉及用户历史数据迁移，如果迭代中途临时修改标签规则、下载逻辑，会导致数据适配返工，延误上线时间。所以我建议本次需求定稿后，全程冻结，不接受临时变更。

产品小A：可以，本次需求正式冻结，全程无变更。那我们今天就敲定所有落地内容，后续按照分工推进即可。
"""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")

    return json.loads(text[start : end + 1])


def get_rag_context(query: str, top_k: int = 8) -> str:
    print("Loading embedding model...")

    embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_collection(name=COLLECTION_NAME)

    query_embedding = embedding_model.encode(
        [query],
        normalize_embeddings=True,
    ).tolist()[0]

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    parts = []

    for i in range(len(result["ids"][0])):
        metadata = result["metadatas"][0][i]
        document = result["documents"][0][i]
        distance = result["distances"][0][i]

        parts.append(
            f"""
【RAG规则 {i + 1}】
标题：{metadata.get("title", "")}
章节：{metadata.get("section", "")}
知识类型：{metadata.get("knowledge_type", "")}
距离：{round(distance, 4)}

{document}
""".strip()
        )

    return "\n\n".join(parts)


def call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是专业 AI Meeting Analyst。"
                    "你必须严格输出合法 JSON，不要输出解释、Markdown 或多余文本。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "options": {
            "temperature": 0.1,
            "top_p": 0.8,
            "num_ctx": 8192,
        },
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300,
    )

    response.raise_for_status()
    return response.json()["message"]["content"]


def build_prompt(rag_context: str, transcript: str) -> str:
    return f"""
你将基于 RAG 规则分析会议内容。

【重要要求】
1. 只输出合法 JSON。
2. 不要输出 Markdown。
3. 不要编造会议中没有的信息。
4. 会议总结必须是归纳总结，不能复制原文。
5. 核心结论只放已经确认的宏观共识。
6. 待办只放会后需要执行的具体任务。
7. 遗留问题只放本次无法解决、暂无方案、暂无排期、暂时搁置的问题。
8. 风险只放未来可能发生的潜在隐患或需要重点关注的事项。
9. 待办、遗留问题、风险不能重复。
10. 如果负责人或截止时间不明确，返回 null。

【强制约束】
1. 不允许把“8月1日前上线”自动分配给所有待办。
2. 只有当某个待办的 source_text 中明确出现截止时间，才允许填写 deadline。
3. 如果 source_text 没有明确截止时间，deadline 必须返回 null。
4. 不允许推断不存在的日期，例如 7月25日、7月30日、2023-08-01。
5. 不允许将“需要产品明确规则”改写成“研发制定方案”。
6. “产品补充标签默认规则、下载频率限制阈值”是待办。
7. “批量下载缺少频率限制可能导致服务器压力过大”必须进入 risks_and_focus。
8. “历史数据迁移过程中临时修改标签规则或下载逻辑导致返工延期”必须进入 risks_and_focus。
9. 如果某事项只是研发提出的依赖条件，不能自动变成研发待办。
10. source_text 必须尽量使用会议原文，不要使用省略号替代关键证据。

【RAG 规则】
{rag_context}

【输出 JSON Schema】
{{
  "meeting_agenda": [
    "string"
  ],
  "meeting_summary": "string",
  "key_conclusions": [
    {{
      "conclusion": "string",
      "source_text": "string",
      "confidence": 0.0
    }}
  ],
  "action_items": [
    {{
      "owner_name": "string or null",
      "task": "string",
      "deadline": "string or null",
      "priority": "low | medium | high",
      "source_text": "string",
      "confidence": 0.0
    }}
  ],
  "unresolved_issues": [
    {{
      "issue": "string",
      "reason": "string",
      "source_text": "string",
      "confidence": 0.0
    }}
  ],
  "risks_and_focus": [
    {{
      "risk": "string",
      "impact": "string",
      "focus_area": "string",
      "source_text": "string",
      "confidence": 0.0
    }}
  ]
}}

【会议内容】
{transcript}
""".strip()


def main() -> None:
    rag_query = """
会议六大维度分析规则。
重点检索：
会议议程、会议总结、核心结论、待办与后续安排、遗留问题、风险与关注点。
尤其关注：
待办和遗留问题边界、遗留问题和风险边界、建议和核心结论边界、会议总结禁止原文摘录、限流风险、数据迁移返工风险。
"""

    rag_context = get_rag_context(
        query=rag_query,
        top_k=8,
    )

    print("\n================ RAG CONTEXT ================")
    print(rag_context)

    prompt = build_prompt(
        rag_context=rag_context,
        transcript=TEST_TRANSCRIPT,
    )

    print("\n================ CALLING QWEN3 ================")

    raw_output = call_ollama(prompt)

    print("\n================ RAW OUTPUT ================")
    print(raw_output)

    print("\n================ VALIDATED JSON ================")

    parsed = extract_json(raw_output)

    validated = validate_meeting_analysis(
        parsed,
        TEST_TRANSCRIPT,
    )

    print(
        json.dumps(
            validated,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()