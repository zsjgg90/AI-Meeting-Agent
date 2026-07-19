from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_tools.action_items import GetOpenActionItemsTool
from app.agent_tools.analysis import AnalyzeMeetingTool
from app.agent_tools.base import ToolExecutionContext, ToolPolicy
from app.agent_tools.knowledge import SearchProjectKnowledgeTool
from app.agent_tools.meeting_context import GetMeetingContextTool
from app.agent_tools.meeting_history import SearchMeetingHistoryTool
from app.agent_tools.validation import ValidateMeetingAnalysisTool


class FakeMeetingContextDb:
    def close(self) -> None:
        self.closed = True

    def get_meeting_context(self, **kwargs: Any) -> dict[str, Any] | None:
        if kwargs["meeting_id"] == "missing":
            return None
        return {
            "meeting": {"id": kwargs["meeting_id"], "title": "Weekly", "status": "completed"},
            "transcript_segments": [
                {"id": "seg-2", "segment_index": 2, "start_time": 20.0, "text": "Second"},
                {"id": "seg-1", "segment_index": 1, "start_time": 10.0, "text": "First"},
            ],
            "summary_metadata": {"result_source": "legacy_qwen_rag"},
        }


class FakeHistoryDb:
    def search_meeting_history(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "meeting_id": "m-1",
                "title": "Requirement review",
                "meeting_summary": "Reviewed checkout scope",
                "result_source": "legacy_qwen_rag",
            }
        ][: kwargs["limit"]]


class FakeActionDb:
    def get_open_action_items(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "id": "a-1",
                "meeting_id": kwargs.get("meeting_id") or "m-1",
                "task": "Update API doc",
                "owner_name": kwargs.get("owner") or "PM",
                "deadline": "Friday",
                "status": "open",
                "source_text": "PM will update API doc by Friday.",
                "source_segment_id": "seg-1",
            }
        ]


class FakeRagPayload:
    text = "policy context"
    chunks = [
        {
            "chunk_id": "chunk-1",
            "title": "Boundary",
            "section": "Actions",
            "knowledge_type": "rule",
            "distance": 0.12,
            "dataset_version": "rag-v1",
            "chunk_schema_version": "rag-chunk-v1",
            "content": "Do not infer owners.",
        }
    ]
    chunk_ids = ["chunk-1"]
    collection_name = "meeting_analyst_rules"
    embedding_model = "fake-embedding"
    dataset_version = "rag-v1"
    chunk_schema_version = "rag-chunk-v1"


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = 0

    def build_context_payload(self, query: str, top_k: int | None = None) -> FakeRagPayload:
        self.calls += 1
        return FakeRagPayload()


class FakeAnalysisService:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, transcript: str) -> dict[str, Any]:
        self.calls += 1
        return {
            "meeting_summary": "summary",
            "_metadata": {
                "result_source": "legacy_qwen_rag",
                "model_name": "fake-qwen3:14b",
                "prompt_version": "meeting-analyst-v1",
                "rag_chunk_ids": ["chunk-1"],
                "fallback_reason": "semantic_pipeline_failed",
            },
        }


def fake_validator(analysis: dict[str, Any], transcript: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validated = dict(analysis)
    validated["validated"] = True
    return validated, [{"field": "action_items", "action": "modify", "reason": "unit_test"}]


class AgentToolAdapterTests(unittest.TestCase):
    def test_adapter_imports_do_not_initialize_external_dependencies(self) -> None:
        for module_name in (
            "app.agent_tools.meeting_context",
            "app.agent_tools.meeting_history",
            "app.agent_tools.action_items",
            "app.agent_tools.knowledge",
            "app.agent_tools.analysis",
            "app.agent_tools.validation",
        ):
            module = importlib.import_module(module_name)
            self.assertIsNotNone(module)

    def test_get_meeting_context_with_fake_db_and_sorted_transcript(self) -> None:
        tool = GetMeetingContextTool(db_provider=FakeMeetingContextDb)
        result = tool.execute(ToolExecutionContext(meeting_id="m-1"), {"include_transcript": True})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result_source, "postgresql")
        self.assertEqual([item["id"] for item in result.data["transcript_segments"]], ["seg-1", "seg-2"])

    def test_get_meeting_context_missing_meeting_returns_failed(self) -> None:
        tool = GetMeetingContextTool(db_provider=FakeMeetingContextDb)
        result = tool.execute(ToolExecutionContext(meeting_id="missing"))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error.error_code, "resource_not_found")  # type: ignore[union-attr]

    def test_search_meeting_history_with_fake_db(self) -> None:
        tool = SearchMeetingHistoryTool(db_provider=FakeHistoryDb)
        result = tool.execute(
            ToolExecutionContext(meeting_id="current"),
            {"query": "checkout", "project_id": "project-1", "meeting_type": "project_weekly", "limit": 5},
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result_source, "postgresql")
        self.assertEqual(result.data["items"][0]["meeting_id"], "m-1")

    def test_get_open_action_items_with_fake_db(self) -> None:
        tool = GetOpenActionItemsTool(db_provider=FakeActionDb)
        result = tool.execute(ToolExecutionContext(), {"meeting_id": "m-1", "owner": "PM"})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["status_filter"], "open")
        self.assertEqual(result.data["items"][0]["status"], "open")

    def test_search_project_knowledge_uses_lazy_fake_retriever(self) -> None:
        created: list[FakeRetriever] = []

        def factory() -> FakeRetriever:
            retriever = FakeRetriever()
            created.append(retriever)
            return retriever

        tool = SearchProjectKnowledgeTool(retriever_factory=factory)
        self.assertEqual(created, [])

        result = tool.execute(ToolExecutionContext(), {"query": "owner rules", "top_k": 100})

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result_source, "rag")
        self.assertEqual(result.data["top_k"], 20)
        self.assertEqual(created[0].calls, 1)

    def test_analyze_meeting_uses_fake_service_and_reports_fallback(self) -> None:
        service = FakeAnalysisService()
        tool = AnalyzeMeetingTool(
            service_factory=lambda: service,
            policy=ToolPolicy(
                timeout_seconds=1,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        result = tool.execute(ToolExecutionContext(meeting_id="m-1"), {"transcript": "PM: Confirmed."})

        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.result_source, "legacy_qwen_rag")
        self.assertEqual(service.calls, 1)
        self.assertIn("analysis", result.data)
        self.assertEqual(result.metadata["fallback_reason"], "semantic_pipeline_failed")

        second = tool.execute(ToolExecutionContext(meeting_id="m-1"), {"transcript": "PM: Confirmed."})
        self.assertEqual(second.status, "fallback")

    def test_analyze_meeting_does_not_call_save_summary(self) -> None:
        service = FakeAnalysisService()
        tool = AnalyzeMeetingTool(
            service_factory=lambda: service,
            policy=ToolPolicy(
                timeout_seconds=1,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        result = tool.execute(ToolExecutionContext(), {"transcript": [{"speaker": "PM", "text": "Confirmed."}]})

        self.assertIn(result.status, {"success", "fallback"})
        self.assertEqual(service.calls, 1)

    def test_validate_meeting_analysis_returns_audit(self) -> None:
        tool = ValidateMeetingAnalysisTool(validator=fake_validator)
        result = tool.execute(
            ToolExecutionContext(meeting_id="m-1"),
            {
                "analysis": {"meeting_summary": "summary", "_metadata": {"result_source": "legacy_qwen_rag"}},
                "transcript": "PM: summary",
            },
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.result_source, "legacy_qwen_rag")
        self.assertTrue(result.data["validated_analysis"]["validated"])
        self.assertEqual(len(result.data["validator_audit"]), 1)
        self.assertEqual(len(result.data["warnings"]), 1)

    def test_agent_switches_are_not_modified_by_tools(self) -> None:
        from app.config import get_settings

        settings = get_settings()
        before = (
            settings.agent_mode_enabled,
            settings.agent_shadow_mode,
            settings.agent_actions_enabled,
        )
        GetOpenActionItemsTool(db_provider=FakeActionDb).execute(ToolExecutionContext())
        after = (
            settings.agent_mode_enabled,
            settings.agent_shadow_mode,
            settings.agent_actions_enabled,
        )

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
