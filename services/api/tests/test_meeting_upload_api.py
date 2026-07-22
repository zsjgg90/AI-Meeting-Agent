import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.models import AudioFile, Meeting


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class MeetingUploadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp_parent = Path(__file__).resolve().parents[3] / "storage" / "test_uploads"
        tmp_parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=tmp_parent)
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.app = create_app()

        def override_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def test_recording_upload_accepts_expo_m4a_and_marks_meeting_uploaded(self) -> None:
        meeting = self.client.post("/meetings", json={"title": "upload smoke"}).json()

        with self.storage_settings():
            response = self.client.post(
                f"/meetings/{meeting['id']}/audio",
                files={"file": ("recording.m4a", b"synthetic audio bytes", "audio/x-m4a")},
                data={"ended_at": "2026-07-23T02:00:00Z"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["meeting_id"], meeting["id"])
        self.assertEqual(body["filename"], "recording.m4a")
        self.assertGreater(body["file_size_bytes"], 0)

        db = self.SessionLocal()
        try:
            stored_meeting = db.get(Meeting, meeting["id"])
            stored_audio = db.get(AudioFile, body["audio_file_id"])
            self.assertEqual(stored_meeting.status, "audio_uploaded")
            self.assertIsNotNone(stored_meeting.end_at)
            self.assertEqual(stored_audio.content_type, "audio/x-m4a")
            self.assertTrue(Path(stored_audio.path).exists())
        finally:
            db.close()

    def test_recording_upload_rejects_empty_file_without_losing_meeting(self) -> None:
        meeting = self.client.post("/meetings", json={"title": "empty upload"}).json()

        with self.storage_settings():
            response = self.client.post(
                f"/meetings/{meeting['id']}/audio",
                files={"file": ("empty.m4a", b"", "audio/x-m4a")},
            )

        self.assertEqual(response.status_code, 400, response.text)
        db = self.SessionLocal()
        try:
            stored_meeting = db.get(Meeting, meeting["id"])
            self.assertEqual(stored_meeting.status, "created")
        finally:
            db.close()

    def storage_settings(self):
        return patch(
            "app.services.storage.get_settings",
            return_value=Settings(database_url="sqlite://", storage_dir=self.tmp.name),
        )


if __name__ == "__main__":
    unittest.main()
