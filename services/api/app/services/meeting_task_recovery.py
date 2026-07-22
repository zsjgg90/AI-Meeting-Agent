from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import AudioFile, Meeting, MeetingSummary, TranscriptSegment, TranscriptionTask


logger = logging.getLogger(__name__)

ACTIVE_TASK_STATUSES = {"queued", "running"}
RECOVERABLE_MEETING_STATUSES = {"processing", "transcribing", "transcribed", "summarizing"}
STALE_TASK_ERROR = "Recovered after API startup; background tasks do not survive service restart."


def recover_stale_meeting_tasks(db: Session) -> int:
    tasks = list(
        db.scalars(
            select(TranscriptionTask)
            .where(TranscriptionTask.status.in_(ACTIVE_TASK_STATUSES))
            .order_by(TranscriptionTask.created_at.asc())
        )
    )
    if not tasks:
        return 0

    now = datetime.now(timezone.utc)
    recovered = 0
    for task in tasks:
        meeting = db.get(Meeting, task.meeting_id)
        task.status = "failed"
        task.error_message = STALE_TASK_ERROR
        task.completed_at = now
        recovered += 1

        if meeting is None or meeting.status not in RECOVERABLE_MEETING_STATUSES:
            continue

        meeting.status = _recovered_meeting_status(db, meeting)
        meeting.updated_at = now

    db.commit()
    return recovered


def recover_stale_meeting_tasks_on_startup(session_factory) -> None:
    db = session_factory()
    try:
        recovered = recover_stale_meeting_tasks(db)
        if recovered:
            logger.warning("Recovered %s stale meeting task(s) during API startup.", recovered)
    except Exception:
        db.rollback()
        logger.exception("Failed to recover stale meeting tasks during API startup.")
    finally:
        db.close()


def _recovered_meeting_status(db: Session, meeting: Meeting) -> str:
    if db.scalar(select(exists().where(MeetingSummary.meeting_id == meeting.id))):
        return "completed"
    if db.scalar(select(exists().where(TranscriptSegment.meeting_id == meeting.id))):
        return "summary_failed" if meeting.status == "summarizing" else "transcribed"
    if db.scalar(select(exists().where(AudioFile.meeting_id == meeting.id))):
        return "audio_uploaded"
    return "failed"
