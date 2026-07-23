import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.models import AudioFile, Meeting, TranscriptionTask, TranscriptSegment
from app.routers.meetings import run_meeting_analysis_task, run_meeting_processing_task


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

    def test_processing_task_saves_structured_worker_error(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(id="meeting-process-error", title="process error", status="processing")
            audio = AudioFile(
                id="audio-process-error",
                meeting_id=meeting.id,
                filename="recording.m4a",
                content_type="audio/x-m4a",
                path="storage/test-recording.m4a",
                file_size_bytes=10,
            )
            task = TranscriptionTask(id="task-process-error", meeting_id=meeting.id, status="queued")
            db.add_all([meeting, audio, task])
            db.commit()
        finally:
            db.close()

        response = httpx.Response(
            500,
            json={
                "detail": {
                    "error_code": "unknown_worker_error",
                    "error_stage": "transcription",
                    "error_message": "转写失败，请稍后重试。",
                }
            },
            request=httpx.Request("POST", "http://worker/meetings/meeting-process-error/process"),
        )

        with patch("app.routers.meetings.SessionLocal", self.SessionLocal), patch("app.routers.meetings.httpx.post", return_value=response):
            run_meeting_processing_task("task-process-error")

        db = self.SessionLocal()
        try:
            stored_task = db.get(TranscriptionTask, "task-process-error")
            stored_meeting = db.get(Meeting, "meeting-process-error")
            self.assertEqual(stored_task.status, "failed")
            self.assertIn('"error_code": "unknown_worker_error"', stored_task.error_message)
            self.assertIn('"error_stage": "transcription"', stored_task.error_message)
            self.assertEqual(stored_meeting.status, "transcription_failed")
        finally:
            db.close()

    def test_analysis_task_saves_summary_stage_error_without_losing_transcript(self) -> None:
        db = self.SessionLocal()
        try:
            meeting_id = "meeting-analysis-error"
            meeting = Meeting(id="meeting-analysis-error", title="analysis error", status="summarizing")
            task = TranscriptionTask(id="task-analysis-error", meeting_id=meeting.id, status="queued")
            segment = TranscriptSegment(
                id="segment-analysis-error",
                meeting_id=meeting_id,
                audio_file_id=None,
                segment_index=0,
                start_time=0,
                end_time=1,
                text="大家确认后端接口需要优化。",
                speaker_label="speaker_1",
            )
            db.add_all([meeting, task, segment])
            db.commit()
        finally:
            db.close()

        response = httpx.Response(
            500,
            json={
                "detail": {
                    "error_code": "unknown_worker_error",
                    "error_stage": "summary",
                    "error_message": "会议纪要生成失败，请重新分析。",
                }
            },
            request=httpx.Request("POST", "http://worker/meetings/meeting-analysis-error/analyze"),
        )

        with patch("app.routers.meetings.SessionLocal", self.SessionLocal), patch("app.routers.meetings.httpx.post", return_value=response):
            run_meeting_analysis_task("task-analysis-error")

        db = self.SessionLocal()
        try:
            stored_task = db.get(TranscriptionTask, "task-analysis-error")
            stored_meeting = db.get(Meeting, "meeting-analysis-error")
            transcript_count = db.query(TranscriptSegment).filter_by(meeting_id=meeting_id).count()
            self.assertEqual(stored_task.status, "failed")
            self.assertIn('"error_code": "unknown_worker_error"', stored_task.error_message)
            self.assertIn('"error_stage": "summary"', stored_task.error_message)
            self.assertEqual(stored_meeting.status, "summary_failed")
            self.assertEqual(transcript_count, 1)
        finally:
            db.close()

    def storage_settings(self):
        return patch(
            "app.services.storage.get_settings",
            return_value=Settings(database_url="sqlite://", storage_dir=self.tmp.name),
        )


if __name__ == "__main__":
    unittest.main()
