import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analyst_service import MeetingAnalystService
from app.rag_retriever import RagContext


class FakeRetriever:
    def build_context_payload(self, query: str, top_k: int | None = None) -> RagContext:
        return RagContext(
            text="规则：只从原文提取结论、待办、问题和风险。",
            chunks=[
                {
                    "chunk_id": "boundary_001",
                    "title": "边界规则",
                    "section": "六维分析",
                    "knowledge_type": "rule",
                    "content": "只从原文提取。",
                    "distance": 0.1,
                }
            ],
            chunk_ids=["boundary_001"],
            collection_name="meeting_analyst_rules",
            embedding_model="fake-embedding",
            dataset_version="meeting_analyst_rag_v1",
            chunk_schema_version="rag-chunk-v1",
        )


class FakeOllamaClient:
    model = "fake-qwen3:14b"
    base_url = "http://fake-ollama"
    temperature = 0.0
    top_p = 0.2
    num_ctx = 8192
    seed = 42
    response_format = "json"
    timeout = 600.0

    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        return json.dumps(
            {
                "meeting_agenda": ["讨论上线范围"],
                "meeting_summary": "本次会议围绕上线范围、任务分工和潜在延期风险进行确认，最终明确按当前方案推进。",
                "key_conclusions": [
                    {
                        "conclusion": "按当前方案推进上线",
                        "source_text": "产品确认按当前方案推进上线。",
                        "confidence": 0.92,
                    }
                ],
                "action_items": [
                    {
                        "owner_name": "产品",
                        "task": "补充验收标准",
                        "deadline": None,
                        "priority": "high",
                        "source_text": "产品本周补充验收标准。",
                        "confidence": 0.91,
                    }
                ],
                "unresolved_issues": [
                    {
                        "issue": "接口排期尚未确认",
                        "reason": "后端还没有确认接口排期。",
                        "source_text": "后端还没有确认接口排期。",
                        "confidence": 0.88,
                    }
                ],
                "risks_and_focus": [
                    {
                        "risk": "如果接口延期，可能影响联调",
                        "impact": "联调时间被压缩",
                        "focus_area": "接口排期",
                        "mitigation": "提前确认接口排期",
                        "source_text": "如果接口延期，可能影响联调。",
                        "confidence": 0.89,
                    }
                ],
                "topics": [
                    {
                        "title": "上线范围确认",
                        "summary": "确认上线范围和风险。",
                        "start_time": 0,
                        "end_time": 20,
                        "related_segment_ids": ["seg-1"],
                        "speakers": ["speaker_0"],
                    }
                ],
            },
            ensure_ascii=False,
        )


class MeetingAnalystServiceFakeTest(unittest.TestCase):
    def test_analyze_uses_fake_llm_and_preserves_metadata(self) -> None:
        transcript = "\n".join(
            [
                "speaker_0：产品确认按当前方案推进上线。",
                "speaker_0：产品本周补充验收标准。",
                "speaker_1：后端还没有确认接口排期。",
                "speaker_1：如果接口延期，可能影响联调。",
            ]
        )
        service = MeetingAnalystService(retriever=FakeRetriever(), llm_client=FakeOllamaClient())

        result = service.analyze(transcript)

        self.assertEqual(result["_metadata"]["prompt_version"], "meeting-analyst-v1")
        self.assertEqual(result["_metadata"]["rag_chunk_ids"], ["boundary_001"])
        self.assertEqual(result["_metadata"]["rag_dataset_version"], "meeting_analyst_rag_v1")
        self.assertEqual(result["_metadata"]["rag_collection_name"], "meeting_analyst_rules")
        self.assertEqual(result["_metadata"]["result_source"], "legacy_qwen_rag")
        self.assertTrue(result["meeting_summary"])
        self.assertEqual(result["action_items"][0]["owner_name"], "产品")


if __name__ == "__main__":
    unittest.main()
