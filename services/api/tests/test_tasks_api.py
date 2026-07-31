import unittest
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import create_app
from app.models import ActionItem, Meeting


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class TasksApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.storage_tmp = TemporaryDirectory()
        self.storage_patch = patch(
            "app.services.storage.get_settings",
            return_value=SimpleNamespace(storage_dir=self.storage_tmp.name),
        )
        self.storage_patch.start()
        self.app = create_app()

        def override_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)
        self.seed_tasks()

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.storage_patch.stop()
        self.storage_tmp.cleanup()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def seed_tasks(self) -> None:
        now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        db = self.SessionLocal()
        try:
            chinese_meeting = Meeting(
                id="task-search-meeting-cn",
                title="Order API Review",
                status="completed",
                created_at=now,
                updated_at=now,
            )
            english_meeting = Meeting(
                id="task-search-meeting-en",
                title="Mobile Release Review",
                status="completed",
                created_at=now,
                updated_at=now,
            )
            db.add_all(
                [
                    chinese_meeting,
                    english_meeting,
                    ActionItem(
                        id="task-search-cn",
                        meeting_id=chinese_meeting.id,
                        task="Add API pressure test report",
                        owner="pm",
                        owner_name="Product owner",
                        description="Initial description",
                        due_date="2026-07-30",
                        priority="high",
                        reminder_offset_minutes=60,
                        reminder_channel="sms",
                        status="open",
                        source_text="API performance needs more benchmark data",
                        created_at=now,
                        updated_at=now,
                    ),
                    ActionItem(
                        id="task-search-en",
                        meeting_id=english_meeting.id,
                        task="Update release checklist",
                        owner="Alice",
                        owner_name="Alice",
                        due_date="2026-08-01",
                        priority="medium",
                        status="completed",
                        source_text="Review release checklist before launch",
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

    def task_ids_for_query(self, query: str) -> set[str]:
        response = self.client.get("/tasks", params={"q": query, "limit": 15})
        self.assertEqual(response.status_code, 200, response.text)
        return {item["id"] for item in response.json()["items"]}

    def test_task_search_is_fuzzy_for_keywords(self) -> None:
        self.assertIn("task-search-cn", self.task_ids_for_query("pressure"))
        self.assertIn("task-search-en", self.task_ids_for_query("review"))

    def test_task_search_splits_mixed_keywords(self) -> None:
        ids = self.task_ids_for_query("pressure review")

        self.assertIn("task-search-cn", ids)
        self.assertIn("task-search-en", ids)

    def test_task_search_supports_status_and_priority_aliases(self) -> None:
        self.assertIn("task-search-cn", self.task_ids_for_query("high"))
        self.assertIn("task-search-en", self.task_ids_for_query("completed"))

    def test_task_status_can_be_updated_through_formal_tasks_api(self) -> None:
        completed = self.client.patch("/tasks/task-search-cn/status", json={"status": "completed"})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "completed")

        reopened = self.client.patch("/tasks/task-search-cn/status", json={"status": "open"})
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["status"], "open")

    def test_task_status_update_rejects_unsupported_status(self) -> None:
        response = self.client.patch("/tasks/task-search-cn/status", json={"status": "in_progress"})

        self.assertEqual(response.status_code, 400, response.text)

    def test_task_list_returns_detail_fields_and_attachments(self) -> None:
        response = self.client.get("/tasks", params={"q": "pressure", "limit": 15})

        self.assertEqual(response.status_code, 200, response.text)
        task = next(item for item in response.json()["items"] if item["id"] == "task-search-cn")
        self.assertEqual(task["description"], "Initial description")
        self.assertEqual(task["reminder_offset_minutes"], 60)
        self.assertEqual(task["reminder_channel"], "sms")
        self.assertEqual(task["attachments"], [])

    def test_task_detail_fields_can_be_updated_through_formal_tasks_api(self) -> None:
        response = self.client.patch(
            "/tasks/task-search-cn",
            json={
                "task": "Updated title",
                "description": "Updated description",
                "owner": "Bob",
                "due_date": "2026-07-15 14:00",
                "priority": "medium",
                "reminder_offset_minutes": 180,
                "reminder_channel": "sms",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["task"], "Updated title")
        self.assertEqual(payload["description"], "Updated description")
        self.assertEqual(payload["owner"], "Bob")
        self.assertIsNone(payload["owner_name"])
        self.assertEqual(payload["due_date"], "2026-07-15 14:00")
        self.assertIsNone(payload["deadline"])
        self.assertEqual(payload["priority"], "medium")
        self.assertEqual(payload["reminder_offset_minutes"], 180)
        self.assertEqual(payload["reminder_channel"], "sms")

    def test_task_update_rejects_unsupported_values(self) -> None:
        bad_priority = self.client.patch("/tasks/task-search-cn", json={"priority": "urgent"})
        self.assertEqual(bad_priority.status_code, 400, bad_priority.text)

        bad_reminder = self.client.patch("/tasks/task-search-cn", json={"reminder_offset_minutes": 30})
        self.assertEqual(bad_reminder.status_code, 400, bad_reminder.text)

        bad_channel = self.client.patch("/tasks/task-search-cn", json={"reminder_channel": "email"})
        self.assertEqual(bad_channel.status_code, 400, bad_channel.text)

    def test_task_attachment_can_be_uploaded_listed_and_downloaded(self) -> None:
        uploaded = self.client.post(
            "/tasks/task-search-cn/attachments",
            files={"file": ("task-note.md", b"# note", "text/markdown")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        attachment = uploaded.json()
        self.assertEqual(attachment["task_id"], "task-search-cn")
        self.assertEqual(attachment["filename"], "task-note.md")
        self.assertEqual(attachment["content_type"], "text/markdown")
        self.assertEqual(attachment["file_size_bytes"], 6)
        self.assertEqual(attachment["download_url"], f"/tasks/task-search-cn/attachments/{attachment['id']}")

        listed = self.client.get("/tasks", params={"q": "pressure", "limit": 15})
        self.assertEqual(listed.status_code, 200, listed.text)
        task = next(item for item in listed.json()["items"] if item["id"] == "task-search-cn")
        self.assertEqual(len(task["attachments"]), 1)
        self.assertEqual(task["attachments"][0]["filename"], "task-note.md")

        downloaded = self.client.get(attachment["download_url"])
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        self.assertEqual(downloaded.content, b"# note")

    def test_task_attachment_upload_rejects_unsupported_files(self) -> None:
        response = self.client.post(
            "/tasks/task-search-cn/attachments",
            files={"file": ("payload.exe", b"bad", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 400, response.text)


if __name__ == "__main__":
    unittest.main()
