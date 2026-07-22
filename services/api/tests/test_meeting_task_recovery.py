import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AudioFile, Meeting, MeetingSummary, TranscriptSegment, TranscriptionTask
from app.services.meeting_task_recovery import STALE_TASK_ERROR, recover_stale_meeting_tasks


@compiles(JSONB, "sqlite")
def compile_jsonb_for_sqlite(_type, compiler, **kw):  # noqa: ANN001, ARG001
    return "JSON"


class MeetingTaskRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_recover_processing_task_returns_uploaded_meeting_to_retryable_state(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(id="meeting-uploaded", title="Uploaded", status="processing")
            db.add(meeting)
            db.add(
                AudioFile(
                    id="audio-uploaded",
                    meeting_id=meeting.id,
                    filename="meeting.wav",
                    path="storage/meeting.wav",
                    file_size_bytes=128,
                )
            )
            db.add(TranscriptionTask(id="task-uploaded", meeting_id=meeting.id, status="running"))
            db.commit()

            recovered = recover_stale_meeting_tasks(db)

            self.assertEqual(recovered, 1)
            recovered_meeting = db.get(Meeting, meeting.id)
            recovered_task = db.get(TranscriptionTask, "task-uploaded")
            self.assertEqual(recovered_meeting.status, "audio_uploaded")
            self.assertEqual(recovered_task.status, "failed")
            self.assertEqual(recovered_task.error_message, STALE_TASK_ERROR)
            self.assertIsNotNone(recovered_task.completed_at)
        finally:
            db.close()

    def test_recover_summarizing_task_marks_summary_failed_without_losing_transcript(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(id="meeting-summary", title="Summary", status="summarizing")
            db.add(meeting)
            db.add(
                TranscriptSegment(
                    id="segment-summary",
                    meeting_id=meeting.id,
                    segment_index=0,
                    start_time=0,
                    end_time=1,
                    text="hello",
                )
            )
            db.add(TranscriptionTask(id="task-summary", meeting_id=meeting.id, status="queued"))
            db.commit()

            recovered = recover_stale_meeting_tasks(db)

            self.assertEqual(recovered, 1)
            self.assertEqual(db.get(Meeting, meeting.id).status, "summary_failed")
            self.assertEqual(db.scalar(select(TranscriptSegment.text).where(TranscriptSegment.meeting_id == meeting.id)), "hello")
        finally:
            db.close()

    def test_recover_prefers_completed_when_summary_exists(self) -> None:
        db = self.SessionLocal()
        try:
            meeting = Meeting(id="meeting-completed", title="Completed", status="summarizing")
            db.add(meeting)
            db.add(
                MeetingSummary(
                    id="summary-completed",
                    meeting_id=meeting.id,
                    overview="done",
                    agenda=[],
                    topics=[],
                    speaker_summaries=[],
                    decisions=[],
                    risks=[],
                    open_questions=[],
                    next_steps=[],
                    meeting_agenda=[],
                    key_conclusions=[],
                    unresolved_issues=[],
                    risks_and_focus=[],
                    rag_chunk_ids=[],
                )
            )
            db.add(TranscriptionTask(id="task-completed", meeting_id=meeting.id, status="running"))
            db.commit()

            recovered = recover_stale_meeting_tasks(db)

            self.assertEqual(recovered, 1)
            self.assertEqual(db.get(Meeting, meeting.id).status, "completed")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
