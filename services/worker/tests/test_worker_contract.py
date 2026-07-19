import unittest
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


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


if __name__ == "__main__":
    unittest.main()
