import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.analysis_contract import ANALYSIS_SCHEMA_VERSION, build_summary_metadata
from app.models import MeetingOutput
from app.routers.meetings import fallback_summary_metadata


class ApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app())
        cls.openapi = cls.client.get("/openapi.json").json()

    def assert_route_exists(self, path: str, method: str) -> None:
        self.assertIn(path, self.openapi["paths"])
        self.assertIn(method.lower(), self.openapi["paths"][path])

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_endpoint_is_registered(self) -> None:
        self.assert_route_exists("/ready", "get")

    def test_meeting_routes_are_registered(self) -> None:
        routes = [
            ("/meetings", "post"),
            ("/meetings", "get"),
            ("/meetings/bulk-delete", "post"),
            ("/meetings/{meeting_id}", "get"),
            ("/meetings/{meeting_id}", "patch"),
            ("/meetings/{meeting_id}", "delete"),
            ("/meetings/{meeting_id}/audio", "post"),
            ("/meetings/{meeting_id}/audio-chunks", "post"),
            ("/meetings/{meeting_id}/audio/{audio_file_id}", "get"),
            ("/meetings/{meeting_id}/process", "post"),
            ("/meetings/{meeting_id}/analyze", "post"),
            ("/meetings/{meeting_id}/transcript", "get"),
            ("/meetings/{meeting_id}/summary", "get"),
            ("/meetings/{meeting_id}/exports/{kind}.{file_format}", "get"),
            ("/meetings/{meeting_id}/speakers/{speaker_label}", "put"),
        ]

        for path, method in routes:
            with self.subTest(path=path, method=method):
                self.assert_route_exists(path, method)

    def test_meeting_list_supports_bounded_pagination_params(self) -> None:
        parameters = self.openapi["paths"]["/meetings"]["get"].get("parameters", [])
        names = {item["name"] for item in parameters}

        self.assertIn("limit", names)
        self.assertIn("offset", names)

    def test_task_and_feedback_routes_are_registered(self) -> None:
        self.assert_route_exists("/tasks", "get")
        self.assert_route_exists("/tasks/{task_id}", "patch")
        self.assert_route_exists("/tasks/{task_id}/status", "patch")
        self.assert_route_exists("/tasks/{task_id}/attachments", "post")
        self.assert_route_exists("/tasks/{task_id}/attachments/{attachment_id}", "get")
        self.assert_route_exists("/feedback", "post")

    def test_knowledge_routes_are_registered(self) -> None:
        routes = [
            ("/knowledge/overview", "get"),
            ("/knowledge/meetings", "get"),
            ("/knowledge/decisions", "get"),
            ("/knowledge/issues", "get"),
            ("/knowledge/risks", "get"),
            ("/knowledge/search", "get"),
            ("/meetings/{meeting_id}/knowledge/reindex", "post"),
        ]

        for path, method in routes:
            with self.subTest(path=path, method=method):
                self.assert_route_exists(path, method)

    def test_knowledge_list_contract_exposes_pagination(self) -> None:
        schemas = self.openapi["components"]["schemas"]
        list_schema = schemas["KnowledgeListRead"]
        meeting_list_schema = schemas["KnowledgeMeetingListRead"]

        for schema in [list_schema, meeting_list_schema]:
            properties = schema["properties"]
            for field in ["items", "total", "limit", "offset", "has_more"]:
                with self.subTest(field=field):
                    self.assertIn(field, properties)

    def test_summary_contract_exposes_six_dimensions(self) -> None:
        schemas = self.openapi["components"]["schemas"]
        summary_schema = schemas["SummaryRead"]
        properties = summary_schema["properties"]

        for field in [
            "meeting_agenda",
            "meeting_summary",
            "key_conclusions",
            "action_items",
            "unresolved_issues",
            "risks_and_focus",
            "topics",
            "metadata",
        ]:
            with self.subTest(field=field):
                self.assertIn(field, properties)

    def test_summary_metadata_has_schema_version_constant(self) -> None:
        self.assertEqual(ANALYSIS_SCHEMA_VERSION, "meeting-analysis-v1")

    def test_summary_metadata_exposes_prompt_and_rag_trace(self) -> None:
        metadata = build_summary_metadata(
            model_name="qwen3:14b+rag",
            confidence_score=0.8,
            generated_at="2026-07-15T00:00:00Z",
            prompt_version="meeting-analyst-v1",
            rag_chunk_ids=["definition_001"],
            rag_dataset_version="meeting_analyst_rag_v1",
            rag_chunk_schema_version="rag-chunk-v1",
            rag_collection_name="meeting_analyst_rules",
            rag_embedding_model="BAAI/bge-small-zh-v1.5",
        )

        self.assertEqual(metadata["prompt_version"], "meeting-analyst-v1")
        self.assertEqual(metadata["result_source"], "legacy_qwen_rag")
        self.assertEqual(metadata["rag_chunk_ids"], ["definition_001"])
        self.assertEqual(metadata["rag_dataset_version"], "meeting_analyst_rag_v1")

    def test_summary_metadata_marks_manual_fixture_source(self) -> None:
        metadata = build_summary_metadata(
            model_name="fixture-gold-standard",
            confidence_score=None,
            generated_at="2026-07-17T00:00:00Z",
            prompt_version="manual-expo-test",
        )

        self.assertEqual(metadata["result_source"], "fixture")

    def test_legacy_output_summary_fallback_has_display_metadata(self) -> None:
        output = MeetingOutput(
            id="legacy-output-1",
            meeting_id="meeting-legacy-output-1",
            raw_transcript="raw",
            speaker_segments=[],
            summary="legacy summary",
            action_items=[],
            decisions=[],
            created_at=datetime(2026, 7, 23, 1, 40, tzinfo=timezone.utc),
        )

        metadata = fallback_summary_metadata(output)

        self.assertEqual(metadata["schema_version"], ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(metadata["result_source"], "legacy_qwen_rag")
        self.assertEqual(metadata["prompt_version"], "legacy-meeting-output")
        self.assertEqual(metadata["generated_at"], "2026-07-23T01:40:00+00:00")

    def test_task_list_contract_exposes_pagination(self) -> None:
        schemas = self.openapi["components"]["schemas"]
        task_list_schema = schemas["TaskListRead"]
        properties = task_list_schema["properties"]

        for field in ["items", "total", "limit", "offset", "has_more"]:
            with self.subTest(field=field):
                self.assertIn(field, properties)


if __name__ == "__main__":
    unittest.main()
