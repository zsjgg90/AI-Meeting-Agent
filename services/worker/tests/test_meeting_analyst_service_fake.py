import json
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.meeting_analyst_service import MeetingAnalystService
from app.rag_retriever import RagContext


class FakeRetriever:
    def build_context_payload(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> RagContext:
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


class DimensionAwareFakeRetriever:
    max_context_chars = 12000

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_context_payload(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> RagContext:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "transcript": transcript,
                "meeting_type": meeting_type,
                "meeting_type_confidence": meeting_type_confidence,
                "target_dimension": target_dimension,
            }
        )

        chunk_ids_by_dimension = {
            "Action": [
                "boundary_speaker_owner_001",
                "exp500_action_boundary_001",
                "exp500_action_neg_003",
            ],
            "Decision": [
                "boundary_rule_008",
                "exp500_decision_boundary_001",
                "exp500_decision_neg_001",
            ],
            "Unresolved": [
                "definition_005",
                "boundary_rule_009",
                "exp500_unresolved_neg_002",
            ],
            "Risk": [
                "definition_006",
                "exp500_risk_boundary_001",
                "exp500_risk_neg_008",
            ],
        }
        chunk_ids = chunk_ids_by_dimension.get(
            target_dimension or "",
            ["global_001"],
        )
        chunks = [
            {
                "chunk_id": chunk_id,
                "title": chunk_id,
                "section": "boundary",
                "knowledge_type": "boundary_rule"
                if "boundary" in chunk_id or chunk_id.startswith("definition")
                else "negative_example",
                "content": f"content for {chunk_id}",
                "distance": 0.1,
                "retrieval_pool": "fixed_policy"
                if chunk_id.startswith(("boundary_", "definition"))
                else "scenario_example",
                "scenario": "all",
                "dimension": target_dimension or "global",
            }
            for chunk_id in chunk_ids
        ]

        return RagContext(
            text="\n".join(
                chunk["content"] for chunk in chunks
            ),
            chunks=chunks,
            chunk_ids=chunk_ids,
            retrieved_chunk_ids=chunk_ids,
            collection_name="meeting_analyst_rules_v3_2_0",
            embedding_model="fake-embedding",
            dataset_version="meeting_analyst_rag_v3_2_0",
            chunk_schema_version="rag-chunk-v3.2",
            retrieval_version="meeting-rag-retrieval-v2",
            scenario_taxonomy_version="meeting-scenario-9-v1",
            retrieval_strategy="v3_dimension_pool_routing"
            if target_dimension
            else "v3_compatible_top_k",
            retrieval_buckets={
                "V3_FIXED_POLICY": [chunk_ids[0]],
                "V3_VECTOR": chunk_ids[1:],
            },
            retrieval_trace={
                "query": query,
                "target_dimension": target_dimension,
                "retrieved_chunk_ids": chunk_ids,
                "final_selected_chunk_ids": chunk_ids,
                "final_selected_chunks": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "retrieval_pool": chunk["retrieval_pool"],
                        "scenario": chunk["scenario"],
                        "knowledge_type": chunk["knowledge_type"],
                    }
                    for chunk in chunks
                ],
                "fallback_reason": None,
            },
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
                "meeting_type": "release_review",
                "meeting_type_confidence": 0.86,
                "meeting_title_candidate": "上线范围与接口风险确认",
                "title_basis": ["会议整体围绕上线范围确认", "会议总结涉及接口风险和联调安排"],
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


class InvalidTitleFakeOllamaClient(FakeOllamaClient):
    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        payload = json.loads(super().chat(prompt, system_prompt))
        payload["meeting_type"] = "project_weekly"
        payload["meeting_type_confidence"] = 0.93
        payload["meeting_title_candidate"] = "后端接口优化需在明天上午完成"
        payload["title_basis"] = ["会议整体同步项目周进度", "议程覆盖版本排期和风险对齐"]
        return json.dumps(payload, ensure_ascii=False)


class NonContractFakeOllamaClient(FakeOllamaClient):
    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        return json.dumps(
            {
                "会议纪要": {
                    "主要决定": {"scope": "V2.5 scope frozen"},
                    "任务分配": {"frontend": "fix search flicker"},
                }
            },
            ensure_ascii=False,
        )


class EmptyIssueReasonFakeOllamaClient(FakeOllamaClient):
    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        return json.dumps(
            {
                "meeting_summary": "The interface schedule remains unresolved.",
                "meeting_agenda": ["Review interface schedule"],
                "key_conclusions": [],
                "action_items": [],
                "unresolved_issues": [
                    {
                        "issue": "Interface schedule is not confirmed",
                        "reason": "",
                        "source_text": "Backend has not confirmed the interface schedule.",
                    }
                ],
                "risks_and_focus": [],
            },
            ensure_ascii=False,
        )


class MeetingAnalystServiceFakeTest(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

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
        self.assertEqual(result["meeting_type"], "release_review")
        self.assertEqual(result["meeting_title_candidate"], "上线范围与接口风险确认")
        self.assertTrue(result["meeting_summary"])
        self.assertEqual(result["action_items"][0]["owner_name"], "产品")

    def test_invalid_title_candidate_does_not_affect_six_dimension_result(self) -> None:
        transcript = "\n".join(
            [
                "speaker_0：产品确认按当前方案推进上线。",
                "speaker_0：产品本周补充验收标准。",
                "speaker_1：后端还没有确认接口排期。",
                "speaker_1：如果接口延期，可能影响联调。",
            ]
        )
        service = MeetingAnalystService(retriever=FakeRetriever(), llm_client=InvalidTitleFakeOllamaClient())

        result = service.analyze(transcript)

        self.assertEqual(result["meeting_title_candidate"], "后端接口优化需在明天上午完成")
        self.assertTrue(result["meeting_summary"])
        self.assertEqual(result["key_conclusions"][0]["conclusion"], "按当前方案推进上线")
        self.assertEqual(result["action_items"][0]["task"], "补充验收标准")


    def test_v3_formal_analysis_uses_dimension_aware_retrieval(self) -> None:
        transcript = "\n".join(
            [
                "PM: This is a quoted example, not a real action.",
                "Engineer: The API migration was completed yesterday.",
                "PM: I propose we delay export, but nobody confirmed it.",
                "QA: Is the retry policy confirmed?",
            ]
        )
        retriever = DimensionAwareFakeRetriever()

        with patch.dict(
            "os.environ",
            {
                "RAG_V3_RETRIEVAL_ENABLED": "true",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            service = MeetingAnalystService(
                retriever=retriever,
                llm_client=FakeOllamaClient(),
            )
            result = service.analyze(transcript)

        self.assertEqual(
            [
                call["target_dimension"]
                for call in retriever.calls
            ],
            [
                "Action",
                "Decision",
                "Unresolved",
                "Risk",
            ],
        )

        query_by_dimension = {
            str(call["target_dimension"]): str(call["query"])
            for call in retriever.calls
        }
        self.assertIn(
            "quoted examples",
            query_by_dimension["Action"],
        )
        self.assertIn(
            "progress updates",
            query_by_dimension["Action"],
        )
        self.assertIn(
            "proposal-vs-decision",
            query_by_dimension["Decision"],
        )
        self.assertIn(
            "question-vs-unresolved",
            query_by_dimension["Unresolved"],
        )

        metadata = result["_metadata"]
        self.assertEqual(
            metadata["rag_retrieval_strategy"],
            "v3_formal_dimension_aware",
        )
        self.assertIn(
            "exp500_action_boundary_001",
            metadata["retrieved_chunk_ids"],
        )
        self.assertIn(
            "exp500_action_neg_003",
            metadata["retrieved_chunk_ids"],
        )
        self.assertIn(
            "exp500_decision_boundary_001",
            metadata["retrieved_chunk_ids"],
        )
        self.assertIn(
            "exp500_decision_neg_001",
            metadata["retrieved_chunk_ids"],
        )
        self.assertIn(
            "boundary_rule_009",
            metadata["retrieved_chunk_ids"],
        )
        self.assertIn(
            "exp500_unresolved_neg_002",
            metadata["retrieved_chunk_ids"],
        )
        self.assertEqual(
            sorted(metadata["rag_dimension_traces"]),
            [
                "action_items",
                "key_conclusions",
                "risks_and_focus",
                "unresolved_issues",
            ],
        )

    def test_title_validator_accepts_supported_meeting_titles(self) -> None:
        from app.meeting_title import is_valid_ai_title, maybe_apply_ai_title

        class MeetingStub:
            title = "2026-07-29 15:30 实时录音"
            title_source = "fallback"

        payloads = [
            {
                "meeting_type": "project_weekly",
                "meeting_type_confidence": 0.91,
                "meeting_title_candidate": "项目周进度同步会",
                "title_basis": ["会议整体同步项目周进度", "议程覆盖版本排期和风险对齐"],
            },
            {
                "meeting_type": "requirement_review",
                "meeting_type_confidence": 0.95,
                "meeting_title_candidate": "V3.2版本迭代启动会",
                "title_basis": ["会议原文提及V3.2版本迭代启动会", "会议议程包含需求范围对齐与排期确认"],
            },
            {
                "meeting_type": "requirement_review",
                "meeting_type_confidence": 0.88,
                "meeting_title_candidate": "智能总结模块需求评审",
                "title_basis": ["会议整体评审智能总结模块需求", "会议总结覆盖范围和验收标准"],
            },
            {
                "meeting_type": "project_retrospective",
                "meeting_type_confidence": 0.9,
                "meeting_title_candidate": "版本延期项目复盘会",
                "title_basis": ["会议整体复盘版本延期原因", "议程覆盖流程问题和改进措施"],
            },
        ]

        for payload in payloads:
            with self.subTest(title=payload["meeting_title_candidate"]):
                self.assertTrue(is_valid_ai_title(payload["meeting_title_candidate"]))
                meeting = MeetingStub()
                applied = maybe_apply_ai_title(meeting, payload)
                self.assertEqual(applied, payload["meeting_title_candidate"])
                self.assertEqual(meeting.title_source, "ai_generated")

    def test_title_validator_rejects_invalid_candidates(self) -> None:
        from app.meeting_title import is_valid_ai_title, maybe_apply_ai_title

        class MeetingStub:
            title = "2026-07-29 15:30 实时录音"
            title_source = "fallback"

        base_payload = {
            "meeting_type": "project_weekly",
            "meeting_type_confidence": 0.91,
            "title_basis": ["会议整体同步项目周进度", "议程覆盖版本排期和风险对齐"],
        }

        self.assertFalse(is_valid_ai_title("项目会议"))
        self.assertFalse(is_valid_ai_title("工作讨论"))
        self.assertFalse(is_valid_ai_title("会议总结"))
        self.assertFalse(is_valid_ai_title("后端接口优化需在明天上午完成"))
        self.assertFalse(is_valid_ai_title("后端接口优化确认会"))
        self.assertFalse(is_valid_ai_title("本次会议主要讨论接口优化"))
        self.assertFalse(is_valid_ai_title("会议.总结讨论会"))
        self.assertFalse(is_valid_ai_title('{"title":"项目周会"}'))

        for title in ["会议总结", "后端接口优化需在明天上午完成", "后端接口优化确认会", "本次会议主要讨论接口优化"]:
            payload = {**base_payload, "meeting_title_candidate": title}
            meeting = MeetingStub()
            self.assertIsNone(maybe_apply_ai_title(meeting, payload))
            self.assertEqual(meeting.title, "2026-07-29 15:30 实时录音")

    def test_title_validator_requires_basis_confidence_and_preserves_user_title(self) -> None:
        from app.meeting_title import maybe_apply_ai_title

        class MeetingStub:
            title = "2026-07-29 15:30 实时录音"
            title_source = "fallback"

        valid_payload = {
            "meeting_type": "requirement_review",
            "meeting_type_confidence": 0.88,
            "meeting_title_candidate": "智能总结模块需求评审",
            "title_basis": ["会议整体评审智能总结模块需求", "会议总结覆盖范围和验收标准"],
        }

        meeting = MeetingStub()
        self.assertIsNone(maybe_apply_ai_title(meeting, {**valid_payload, "meeting_type_confidence": 0.69}))
        self.assertEqual(meeting.title, "2026-07-29 15:30 实时录音")

        meeting = MeetingStub()
        self.assertIsNone(maybe_apply_ai_title(meeting, {**valid_payload, "title_basis": ["只有一条依据"]}))
        self.assertEqual(meeting.title, "2026-07-29 15:30 实时录音")

        meeting = MeetingStub()
        applied = maybe_apply_ai_title(meeting, valid_payload)
        self.assertEqual(applied, "智能总结模块需求评审")

        meeting.title = "用户手动标题"
        meeting.title_source = "user_edited"
        applied = maybe_apply_ai_title(meeting, valid_payload)
        self.assertIsNone(applied)
        self.assertEqual(meeting.title, "用户手动标题")

    def test_title_update_keeps_default_for_invalid_and_repeat_analysis(self) -> None:
        from app.meeting_title import maybe_apply_ai_title

        class MeetingStub:
            title = "2026-07-29 15:30 文件导入"
            title_source = "fallback"

        meeting = MeetingStub()
        self.assertIsNone(maybe_apply_ai_title(meeting, {"meeting_title_candidate": "会议总结"}))
        self.assertEqual(meeting.title, "2026-07-29 15:30 文件导入")
        self.assertEqual(meeting.title_source, "fallback")

        self.assertIsNone(maybe_apply_ai_title(meeting, {"meeting_title_candidate": ""}))
        self.assertEqual(meeting.title, "2026-07-29 15:30 文件导入")

        meeting.title = "智能总结模块需求评审"
        meeting.title_source = "ai_generated"
        self.assertIsNone(maybe_apply_ai_title(meeting, {
            "meeting_type": "solution_review",
            "meeting_type_confidence": 0.88,
            "meeting_title_candidate": "订单系统重构方案讨论",
            "title_basis": ["会议整体讨论订单系统重构", "会议总结覆盖方案取舍"],
        }))
        self.assertEqual(meeting.title, "智能总结模块需求评审")


    def test_non_contract_model_output_is_rejected(self) -> None:
        service = MeetingAnalystService(retriever=FakeRetriever(), llm_client=NonContractFakeOllamaClient())

        with self.assertRaises(ValueError) as raised:
            service.analyze("Product confirmed V2.5 scope; frontend fixes search flicker.")

        self.assertIn("empty_analysis_result", str(raised.exception))
        self.assertIn("invalid_model_output_contract", str(raised.exception))

    def test_validation_payload_omits_default_empty_issue_fields(self) -> None:
        service = MeetingAnalystService(retriever=FakeRetriever(), llm_client=EmptyIssueReasonFakeOllamaClient())

        result = service.analyze("Backend has not confirmed the interface schedule.")

        self.assertIn("unresolved_issues", result)

    def test_text_debug_title_can_be_replaced_by_valid_ai_title(self) -> None:
        from app.meeting_title import maybe_apply_ai_title

        class MeetingStub:
            title = "APP_V2.5项目周会_真实模拟会议_最终版"
            title_source = "text_debug"

        payload = {
            "meeting_type": "project_weekly",
            "meeting_type_confidence": 0.91,
            "meeting_title_candidate": "项目周进度同步会",
            "title_basis": ["会议整体同步项目周进度", "议程覆盖版本排期和风险对齐"],
        }

        meeting = MeetingStub()
        applied = maybe_apply_ai_title(meeting, payload)

        self.assertEqual(applied, "项目周进度同步会")
        self.assertEqual(meeting.title, "项目周进度同步会")
        self.assertEqual(meeting.title_source, "ai_generated")


if __name__ == "__main__":
    unittest.main()
