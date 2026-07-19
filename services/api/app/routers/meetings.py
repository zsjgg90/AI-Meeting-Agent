import asyncio
import base64
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.analysis_contract import build_summary_metadata
from app.database import SessionLocal, get_db
from app.models import AudioFile, Meeting, MeetingSummary, TranscriptSegment, TranscriptionTask
from app.models import SpeakerMapping
from app.schemas import (
    AudioUploaded,
    AudioChunkUploaded,
    MeetingBulkDelete,
    MeetingBulkDeleteResult,
    MeetingCreate,
    MeetingCreated,
    MeetingListItem,
    MeetingRead,
    MeetingUpdate,
    ProcessStarted,
    SummaryRead,
    SpeakerMappingRead,
    SpeakerMappingUpdate,
    TranscriptRead,
)
from app.services.storage import AudioStorageError, UnsupportedAudioFileError, save_upload_file
from app.services.volcengine_realtime import RealtimeAsrError, extract_segments, new_realtime_client
from app.services.meeting_exports import create_export_file

router = APIRouter(prefix="/meetings", tags=["meetings"])


def meeting_detail_options():
    return (
        selectinload(Meeting.audio_files),
        selectinload(Meeting.transcript_segments),
        selectinload(Meeting.summary).selectinload(MeetingSummary.action_items),
        selectinload(Meeting.action_items),
        selectinload(Meeting.speaker_mappings),
        selectinload(Meeting.tasks),
        selectinload(Meeting.output),
        selectinload(Meeting.chunks),
    )


def get_meeting_or_404(db: Session, meeting_id: str) -> Meeting:
    meeting = db.scalars(select(Meeting).where(Meeting.id == meeting_id).options(*meeting_detail_options())).first()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


def remove_meeting_storage(meeting_id: str) -> None:
    storage_root = (Path(get_settings().storage_dir).resolve() / "meetings").resolve()
    meeting_dir = (storage_root / meeting_id).resolve()
    try:
        meeting_dir.relative_to(storage_root)
    except ValueError:
        return
    if meeting_dir.exists():
        shutil.rmtree(meeting_dir, ignore_errors=True)


@router.post("", response_model=MeetingCreated, status_code=201)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db)) -> MeetingCreated:
    meeting = Meeting(
        title=payload.title,
        status="created",
        start_at=payload.start_at,
        end_at=payload.end_at,
        location=payload.location.strip() if payload.location else None,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return MeetingCreated(id=meeting.id, title=meeting.title, status=meeting.status)


@router.get("", response_model=list[MeetingListItem])
def list_meetings(db: Session = Depends(get_db)) -> list[Meeting]:
    return list(db.scalars(select(Meeting).order_by(Meeting.created_at.desc())).all())


@router.post("/bulk-delete", response_model=MeetingBulkDeleteResult)
def bulk_delete_meetings(payload: MeetingBulkDelete, db: Session = Depends(get_db)) -> MeetingBulkDeleteResult:
    meetings = list(db.scalars(select(Meeting).where(Meeting.id.in_(payload.meeting_ids))).all())
    for meeting in meetings:
        db.delete(meeting)
    db.commit()

    for meeting in meetings:
        remove_meeting_storage(meeting.id)

    return MeetingBulkDeleteResult(deleted_count=len(meetings))


@router.get("/{meeting_id}", response_model=MeetingRead)
def get_meeting(meeting_id: str, db: Session = Depends(get_db)) -> Meeting:
    return get_meeting_or_404(db, meeting_id)


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: str, db: Session = Depends(get_db)) -> None:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    db.delete(meeting)
    db.commit()
    remove_meeting_storage(meeting_id)


@router.patch("/{meeting_id}", response_model=MeetingRead)
def update_meeting(meeting_id: str, payload: MeetingUpdate, db: Session = Depends(get_db)) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "start_at" in updates:
        meeting.start_at = updates["start_at"]
    if "end_at" in updates:
        meeting.end_at = updates["end_at"]
    if "location" in updates:
        location = updates["location"]
        meeting.location = location.strip() if location else None

    db.commit()
    return get_meeting_or_404(db, meeting_id)


@router.put("/{meeting_id}/speakers/{speaker_label}", response_model=SpeakerMappingRead)
def update_speaker_mapping(
    meeting_id: str,
    speaker_label: str,
    payload: SpeakerMappingUpdate,
    db: Session = Depends(get_db),
) -> SpeakerMapping:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    clean_display_name = payload.display_name.strip()
    if not clean_display_name:
        raise HTTPException(status_code=400, detail="display_name cannot be empty.")

    mapping = db.scalars(
        select(SpeakerMapping).where(
            SpeakerMapping.meeting_id == meeting_id,
            SpeakerMapping.speaker_label == speaker_label,
        )
    ).first()
    if mapping is None:
        mapping = SpeakerMapping(
            meeting_id=meeting_id,
            speaker_label=speaker_label,
            display_name=clean_display_name,
            note=payload.note.strip() if payload.note else None,
        )
        db.add(mapping)
    else:
        mapping.display_name = clean_display_name
        mapping.note = payload.note.strip() if payload.note else None

    db.commit()
    db.refresh(mapping)
    return mapping


@router.post("/{meeting_id}/audio", response_model=AudioUploaded)
def upload_audio(
    meeting_id: str,
    file: UploadFile = File(...),
    ended_at: datetime | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AudioUploaded:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    try:
        path, file_size_bytes = save_upload_file(meeting_id, file)
    except UnsupportedAudioFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AudioStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    audio_file = AudioFile(
        meeting_id=meeting_id,
        filename=path.name,
        content_type=file.content_type,
        path=str(path),
        file_size_bytes=file_size_bytes,
    )
    meeting.status = "audio_uploaded"
    if ended_at is not None:
        meeting.end_at = ended_at
    db.add(audio_file)
    db.commit()
    db.refresh(audio_file)
    return AudioUploaded(
        audio_file_id=audio_file.id,
        meeting_id=meeting_id,
        filename=audio_file.filename,
        path=audio_file.path,
        file_size_bytes=audio_file.file_size_bytes,
    )


@router.post("/{meeting_id}/audio-chunks", response_model=AudioChunkUploaded)
def upload_audio_chunk(
    meeting_id: str,
    file: UploadFile = File(...),
    start_offset_seconds: float = Form(default=0.0),
    ended_at: datetime | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AudioChunkUploaded:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    try:
        path, file_size_bytes = save_upload_file(meeting_id, file)
    except UnsupportedAudioFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AudioStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    audio_file = AudioFile(
        meeting_id=meeting_id,
        filename=path.name,
        content_type=file.content_type,
        path=str(path),
        file_size_bytes=file_size_bytes,
    )
    meeting.status = "transcribing"
    if ended_at is not None:
        meeting.end_at = ended_at
    db.add(audio_file)
    db.commit()
    db.refresh(audio_file)

    transcript_segment_count = 0
    try:
        worker_url = get_settings().worker_url.rstrip("/")
        response = httpx.post(
            f"{worker_url}/meetings/{meeting_id}/transcribe-chunk",
            json={
                "audio_file_id": audio_file.id,
                "start_offset_seconds": start_offset_seconds,
            },
            timeout=None,
        )
        response.raise_for_status()
        transcript_segment_count = int(response.json().get("transcript_segment_count", 0))
    except Exception as exc:
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "transcription_failed"
            db.commit()
        raise HTTPException(
            status_code=503,
            detail="Realtime chunk transcription failed. Please confirm the worker service is running.",
        ) from exc

    return AudioChunkUploaded(
        audio_file_id=audio_file.id,
        meeting_id=meeting_id,
        filename=audio_file.filename,
        path=audio_file.path,
        file_size_bytes=audio_file.file_size_bytes,
        start_offset_seconds=start_offset_seconds,
        transcript_segment_count=transcript_segment_count,
    )


@router.get("/{meeting_id}/audio/{audio_file_id}")
def get_audio_file(meeting_id: str, audio_file_id: str, db: Session = Depends(get_db)) -> FileResponse:
    audio_file = db.scalars(
        select(AudioFile).where(
            AudioFile.id == audio_file_id,
            AudioFile.meeting_id == meeting_id,
        )
    ).first()
    if audio_file is None:
        raise HTTPException(status_code=404, detail="Audio file not found.")

    path = Path(audio_file.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file is missing from storage.")

    return FileResponse(
        path,
        media_type=audio_file.content_type or "application/octet-stream",
        filename=audio_file.filename,
    )


@router.websocket("/{meeting_id}/realtime-stream")
async def realtime_stream(meeting_id: str, websocket: WebSocket) -> None:
    await websocket.accept()

    db = SessionLocal()
    client = new_realtime_client()
    receive_task = None
    seen_keys: set[tuple[str, float, float, str]] = set()

    def persist_segments(segments: list[dict]) -> list[dict]:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise RealtimeAsrError("Meeting not found.")

        existing_count = db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)).all()
        next_index = len(existing_count)
        saved_segments: list[dict] = []

        for segment in segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            start_time = float(segment.get("start_time") or 0.0)
            end_time = float(segment.get("end_time") or start_time + 0.1)
            speaker_label = segment.get("speaker_label")
            key = (speaker_label or "", round(start_time, 2), round(end_time, 2), text)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            row = TranscriptSegment(
                meeting_id=meeting_id,
                audio_file_id=None,
                segment_index=next_index,
                start_time=start_time,
                end_time=max(end_time, start_time + 0.1),
                text=text,
                speaker_label=speaker_label,
                speaker_gender=segment.get("speaker_gender"),
            )
            db.add(row)
            db.flush()
            next_index += 1
            saved_segments.append(
                {
                    "id": row.id,
                    "audio_file_id": row.audio_file_id,
                    "segment_index": row.segment_index,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "text": row.text,
                    "speaker_label": row.speaker_label,
                    "speaker_gender": row.speaker_gender,
                    "created_at": row.created_at.isoformat(),
                }
            )

        if saved_segments:
            meeting.status = "transcribing"
            db.commit()
        else:
            db.rollback()
        return saved_segments

    async def receive_volcengine() -> None:
        async for payload in client.receive():
            segments = extract_segments(payload)
            saved_segments = persist_segments(segments)
            await websocket.send_json(
                {
                    "type": "partial" if saved_segments else "heartbeat",
                    "segments": saved_segments,
                    "raw": payload,
                }
            )

    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            await websocket.send_json({"type": "error", "detail": "Meeting not found."})
            return

        await client.connect()
        receive_task = asyncio.create_task(receive_volcengine())
        await websocket.send_json({"type": "ready", "sample_rate": 16000, "chunk_ms": 200})

        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            message_type = data.get("type")
            if message_type == "audio":
                chunk_base64 = data.get("pcm_base64") or data.get("data")
                if not isinstance(chunk_base64, str) or not chunk_base64:
                    continue
                await client.send_audio(base64.b64decode(chunk_base64), is_last=False)
            elif message_type == "end":
                await client.send_audio(b"", is_last=True)
                await websocket.send_json({"type": "ending"})
                break

        if receive_task is not None:
            try:
                await asyncio.wait_for(receive_task, timeout=8)
            except asyncio.TimeoutError:
                receive_task.cancel()
        await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
        await client.close()
        db.close()


@router.post("/{meeting_id}/process", response_model=ProcessStarted)
def process_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessStarted:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    audio_file = db.scalars(
        select(AudioFile).where(AudioFile.meeting_id == meeting_id).order_by(AudioFile.uploaded_at.desc())
    ).first()
    if audio_file is None:
        raise HTTPException(status_code=400, detail="Upload audio before processing the meeting.")

    active_task = db.scalars(
        select(TranscriptionTask)
        .where(
            TranscriptionTask.meeting_id == meeting_id,
            TranscriptionTask.status.in_(["queued", "running"]),
        )
        .order_by(TranscriptionTask.created_at.desc())
    ).first()
    if active_task is not None:
        return ProcessStarted(task_id=active_task.id, meeting_id=meeting_id, status=active_task.status)

    task = TranscriptionTask(meeting_id=meeting_id, status="queued")
    meeting.status = "processing"
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(run_meeting_processing_task, task.id)
    return ProcessStarted(task_id=task.id, meeting_id=meeting_id, status=task.status)


@router.post("/{meeting_id}/analyze", response_model=ProcessStarted)
def analyze_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ProcessStarted:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    segments = db.scalars(select(TranscriptSegment.id).where(TranscriptSegment.meeting_id == meeting_id)).all()
    if not segments:
        raise HTTPException(status_code=400, detail="Transcript segments are required before analysis.")

    active_task = db.scalars(
        select(TranscriptionTask)
        .where(
            TranscriptionTask.meeting_id == meeting_id,
            TranscriptionTask.status.in_(["queued", "running"]),
        )
        .order_by(TranscriptionTask.created_at.desc())
    ).first()
    if active_task is not None:
        return ProcessStarted(task_id=active_task.id, meeting_id=meeting_id, status=active_task.status)

    task = TranscriptionTask(meeting_id=meeting_id, status="queued")
    meeting.status = "summarizing"
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(run_meeting_analysis_task, task.id)
    return ProcessStarted(task_id=task.id, meeting_id=meeting_id, status=task.status)



@router.get("/{meeting_id}/transcript", response_model=TranscriptRead)
def get_transcript(meeting_id: str, db: Session = Depends(get_db)) -> TranscriptRead:
    meeting = get_meeting_or_404(db, meeting_id)
    output = meeting.output
    return TranscriptRead(
        meeting_id=meeting.id,
        status=meeting.status,
        raw_transcript=output.raw_transcript if output else None,
        segments=meeting.transcript_segments,
        speaker_segments=output.speaker_segments if output else [],
    )


@router.get("/{meeting_id}/summary", response_model=SummaryRead)
def get_summary(meeting_id: str, db: Session = Depends(get_db)) -> SummaryRead:
    meeting = get_meeting_or_404(db, meeting_id)
    if meeting.summary is not None:
        metadata = build_summary_metadata(
            model_name=meeting.summary.model_name,
            confidence_score=meeting.summary.confidence_score,
            generated_at=meeting.summary.updated_at.isoformat() if meeting.summary.updated_at else "",
            prompt_version=meeting.summary.prompt_version,
            rag_chunk_ids=meeting.summary.rag_chunk_ids,
            rag_dataset_version=meeting.summary.rag_dataset_version,
            rag_chunk_schema_version=meeting.summary.rag_chunk_schema_version,
            rag_collection_name=meeting.summary.rag_collection_name,
            rag_embedding_model=meeting.summary.rag_embedding_model,
        )
        return SummaryRead(
            meeting_id=meeting.id,
            status=meeting.status,
            overview=meeting.summary.overview,
            agenda=meeting.summary.agenda,
            topics=meeting.summary.topics,
            speaker_summaries=meeting.summary.speaker_summaries,
            summary=meeting.summary.overview,
            action_items=[
                {
                    "task": item.task,
                    "owner": item.owner or item.owner_name or "",
                    "owner_name": item.owner_name,
                    "due_date": item.due_date or item.deadline or "",
                    "deadline": item.deadline,
                    "priority": item.priority or "medium",
                    "status": item.status,
                    "source": item.source or item.source_text or "",
                    "source_text": item.source_text,
                    "source_segment_id": item.source_segment_id,
                    "confidence": item.confidence,
                }
                for item in meeting.action_items
            ],
            decisions=meeting.summary.decisions,
            risks=meeting.summary.risks,
            open_questions=meeting.summary.open_questions,
            next_steps=meeting.summary.next_steps,
            meeting_agenda=meeting.summary.meeting_agenda or meeting.summary.agenda,
            meeting_summary=meeting.summary.meeting_summary or meeting.summary.overview,
            key_conclusions=meeting.summary.key_conclusions or meeting.summary.decisions,
            unresolved_issues=meeting.summary.unresolved_issues or meeting.summary.open_questions,
            risks_and_focus=meeting.summary.risks_and_focus or meeting.summary.risks,
            metadata=metadata,
        )

    output = meeting.output
    return SummaryRead(
        meeting_id=meeting.id,
        status=meeting.status,
        overview=output.summary if output else None,
        agenda=[],
        topics=[],
        speaker_summaries=[],
        summary=output.summary if output else None,
        action_items=output.action_items if output else [],
        decisions=output.decisions if output else [],
        risks=[],
        open_questions=[],
        next_steps=[],
        meeting_agenda=[],
        meeting_summary=output.summary if output else "",
        key_conclusions=output.decisions if output else [],
        unresolved_issues=[],
        risks_and_focus=[],
        metadata={},
    )


@router.get("/{meeting_id}/exports/{kind}.{file_format}")
def export_meeting_file(
    meeting_id: str,
    kind: str,
    file_format: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    meeting = get_meeting_or_404(db, meeting_id)
    try:
        path = create_export_file(meeting, kind, file_format.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_types = {
        "md": "text/markdown; charset=utf-8",
        "markdown": "text/markdown; charset=utf-8",
        "txt": "text/plain; charset=utf-8",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return FileResponse(path, media_type=media_types.get(file_format.lower()), filename=path.name)


def run_meeting_processing_task(task_id: str) -> None:
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

        settings = get_settings()
        worker_url = settings.worker_url.rstrip("/")
        response = httpx.post(
            f"{worker_url}/meetings/{meeting.id}/process",
            timeout=settings.worker_request_timeout_seconds,
        )
        response.raise_for_status()

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = None
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


def run_meeting_analysis_task(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(TranscriptionTask, task_id)
        if task is None:
            return

        meeting = db.get(Meeting, task.meeting_id)
        if meeting is None:
            task.status = "failed"
            task.error_message = "Meeting not found."
            task.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        meeting.status = "summarizing"
        db.commit()

        settings = get_settings()
        worker_url = settings.worker_url.rstrip("/")
        response = httpx.post(
            f"{worker_url}/meetings/{meeting.id}/analyze",
            timeout=settings.worker_request_timeout_seconds,
        )
        response.raise_for_status()

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
                meeting.status = "summary_failed"
            db.commit()
    finally:
        db.close()
