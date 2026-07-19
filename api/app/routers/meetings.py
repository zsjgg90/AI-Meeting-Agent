from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal, get_db
from app.models import AudioFile, Meeting, MeetingChunk, MeetingOutput, TranscriptionTask
from app.schemas import AudioUploaded, MeetingCreate, MeetingCreated, MeetingRead, TaskCreated
from app.services.meeting_analysis import analyze_meeting
from app.services.storage import save_upload_file
from app.services.transcription import transcribe_audio

router = APIRouter(prefix="/meetings", tags=["meetings"])


def load_meeting(db: Session, meeting_id: str) -> Meeting | None:
    statement = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(
            selectinload(Meeting.audio_files),
            selectinload(Meeting.tasks),
            selectinload(Meeting.output),
            selectinload(Meeting.chunks),
        )
    )
    return db.scalars(statement).first()


@router.post("", response_model=MeetingCreated)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db)) -> MeetingCreated:
    meeting = Meeting(title=payload.title, status="created")
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return MeetingCreated(meeting_id=meeting.id, status=meeting.status)


@router.get("/{meeting_id}", response_model=MeetingRead)
def get_meeting(meeting_id: str, db: Session = Depends(get_db)) -> Meeting:
    meeting = load_meeting(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


@router.post("/{meeting_id}/audio", response_model=AudioUploaded)
def upload_audio(
    meeting_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AudioUploaded:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    path = save_upload_file(meeting_id, file)
    audio_file = AudioFile(
        meeting_id=meeting_id,
        filename=path.name,
        content_type=file.content_type,
        path=str(path),
    )
    meeting.status = "audio_uploaded"
    db.add(audio_file)
    db.commit()
    db.refresh(audio_file)
    return AudioUploaded(audio_file_id=audio_file.id, meeting_id=meeting_id, filename=audio_file.filename)


@router.post("/{meeting_id}/transcription-tasks", response_model=TaskCreated)
def create_transcription_task(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> TaskCreated:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    audio_file = db.scalars(
        select(AudioFile).where(AudioFile.meeting_id == meeting_id).order_by(AudioFile.uploaded_at.desc())
    ).first()
    if audio_file is None:
        raise HTTPException(status_code=400, detail="Upload audio before creating a transcription task.")

    task = TranscriptionTask(meeting_id=meeting_id, status="queued")
    meeting.status = "processing"
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(run_transcription_task, task.id)
    return TaskCreated(task_id=task.id, meeting_id=meeting_id, status=task.status)


def run_transcription_task(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(TranscriptionTask, task_id)
        if task is None:
            return

        meeting = db.get(Meeting, task.meeting_id)
        audio_file = db.scalars(
            select(AudioFile).where(AudioFile.meeting_id == task.meeting_id).order_by(AudioFile.uploaded_at.desc())
        ).first()
        if meeting is None or audio_file is None:
            task.status = "failed"
            task.error_message = "Meeting or audio file not found."
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        meeting.status = "processing"
        db.commit()

        raw_transcript = transcribe_audio(audio_file.path)
        analysis = analyze_meeting(raw_transcript)

        old_output = db.scalars(select(MeetingOutput).where(MeetingOutput.meeting_id == meeting.id)).first()
        if old_output is not None:
            db.delete(old_output)
        for chunk in db.scalars(select(MeetingChunk).where(MeetingChunk.meeting_id == meeting.id)).all():
            db.delete(chunk)
        db.flush()

        output = MeetingOutput(
            meeting_id=meeting.id,
            raw_transcript=raw_transcript,
            speaker_segments=analysis["speaker_segments"],
            summary=analysis["summary"],
            action_items=analysis["action_items"],
            decisions=analysis["decisions"],
        )
        db.add(output)

        for chunk in analysis["rag_chunks"]:
            db.add(
                MeetingChunk(
                    meeting_id=meeting.id,
                    speaker=chunk.get("speaker") or None,
                    content=chunk["content"],
                    metadata_=chunk.get("metadata") or {},
                )
            )

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = None
        meeting.status = "completed"
        db.commit()
    except Exception as exc:
        db.rollback()
        task = db.get(TranscriptionTask, task_id)
        if task is not None:
            task.status = "failed"
            task.error_message = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            meeting = db.get(Meeting, task.meeting_id)
            if meeting is not None:
                meeting.status = "failed"
            db.commit()
    finally:
        db.close()
