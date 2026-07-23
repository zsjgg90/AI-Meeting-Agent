import unittest
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.summary_agent import SummaryAgentError


class WorkerContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
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

    def test_worker_routes_are_registered(self) -> None:
        for path, method in [
            ("/warmup", "post"),
            ("/meetings/{meeting_id}/process", "post"),
            ("/meetings/{meeting_id}/analyze", "post"),
            ("/meetings/{meeting_id}/transcribe-chunk", "post"),
        ]:
            with self.subTest(path=path, method=method):
                self.assert_route_exists(path, method)

    def test_analyze_returns_structured_summary_error(self) -> None:
        with patch("app.main.summarize_meeting", side_effect=SummaryAgentError("schema validation failed")):
            response = self.client.post("/meetings/meeting-error/analyze")

        self.assertEqual(response.status_code, 400)
        detail = response.json()["detail"]
        self.assertEqual(detail["error_stage"], "summary")
        self.assertEqual(detail["error_code"], "contract_validation_failed")
        self.assertEqual(detail["error_message"], "schema validation failed")

    def test_process_returns_structured_unknown_error_without_stack(self) -> None:
        with patch("app.main.OrchestratorAgent") as orchestrator_cls:
            orchestrator_cls.return_value.run.side_effect = RuntimeError("unexpected failure")
            response = self.client.post("/meetings/meeting-error/process")

        self.assertEqual(response.status_code, 500)
        detail = response.json()["detail"]
        self.assertEqual(detail["error_stage"], "process")
        self.assertEqual(detail["error_code"], "unknown_worker_error")
        self.assertEqual(detail["error_message"], "unexpected failure")
        self.assertNotIn("Traceback", str(detail))


if __name__ == "__main__":
    unittest.main()
