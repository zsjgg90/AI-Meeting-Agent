import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import ActionItem, Meeting, TaskAttachment
from app.schemas import TaskAttachmentRead, TaskListItem, TaskListRead, TaskStatusUpdate, TaskUpdate
from app.services.storage import (
    TaskAttachmentStorageError,
    UnsupportedTaskAttachmentError,
    save_task_attachment_file,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


SEARCH_SPLIT_PATTERN = re.compile(r"[\s,，。；;、|/\\]+")
SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "高": ("high",),
    "高优先级": ("high",),
    "high": ("高优先级",),
    "中": ("medium",),
    "中优先级": ("medium",),
    "medium": ("中优先级",),
    "低": ("low",),
    "低优先级": ("low",),
    "low": ("低优先级",),
    "完成": ("completed", "done", "closed", "finished"),
    "已完成": ("completed", "done", "closed", "finished"),
    "completed": ("已完成",),
    "done": ("已完成",),
    "进行中": ("in_progress", "running"),
    "in_progress": ("进行中",),
    "running": ("进行中",),
    "待办": ("open", "todo", "pending"),
    "待处理": ("open", "todo", "pending"),
    "open": ("待处理",),
    "todo": ("待办",),
    "pending": ("待处理",),
}
TASK_WRITE_STATUSES = {"open", "completed"}
TASK_WRITE_PRIORITIES = {"high", "medium", "low"}
TASK_REMINDER_OFFSETS = {60, 180, 300}
TASK_REMINDER_CHANNELS = {"sms"}


def task_search_terms(query: str) -> list[str]:
    raw_terms = [query.strip(), *SEARCH_SPLIT_PATTERN.split(query.strip())]
    terms: list[str] = []
    seen: set[str] = set()

    for raw_term in raw_terms:
        term = raw_term.strip()
        if not term:
            continue
        candidates = [term, *SEARCH_ALIASES.get(term.lower(), ()), *SEARCH_ALIASES.get(term, ())]
        for candidate in candidates:
            normalized = candidate.strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                terms.append(normalized)

    return terms


def task_attachment_download_url(task_id: str, attachment_id: str) -> str:
    return f"/tasks/{task_id}/attachments/{attachment_id}"


def to_task_attachment_read(item: TaskAttachment) -> TaskAttachmentRead:
    url = task_attachment_download_url(item.task_id, item.id)
    return TaskAttachmentRead(
        id=item.id,
        task_id=item.task_id,
        filename=item.filename,
        content_type=item.content_type,
        file_size_bytes=item.file_size_bytes,
        download_url=url,
        url=url,
        uploaded_at=item.uploaded_at,
    )


def to_task_list_item(item: ActionItem, meeting_title: str) -> TaskListItem:
    return TaskListItem(
        id=item.id,
        meeting_id=item.meeting_id,
        meeting_title=meeting_title,
        task=item.task,
        owner=item.owner,
        owner_name=item.owner_name,
        description=item.description,
        due_date=item.due_date,
        deadline=item.deadline,
        priority=item.priority,
        reminder_offset_minutes=item.reminder_offset_minutes,
        reminder_channel=item.reminder_channel,
        status=item.status,
        source=item.source,
        source_text=item.source_text,
        source_segment_id=item.source_segment_id,
        confidence=item.confidence,
        attachments=[to_task_attachment_read(attachment) for attachment in item.attachments],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def get_task_row_or_404(db: Session, task_id: str) -> tuple[ActionItem, str]:
    row = db.execute(
        select(ActionItem, Meeting.title)
        .join(Meeting, Meeting.id == ActionItem.meeting_id)
        .options(selectinload(ActionItem.attachments))
        .where(ActionItem.id == task_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return row


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


@router.get("", response_model=TaskListRead)
def list_tasks(
    limit: int = Query(default=15, ge=1, le=15),
    offset: int = Query(default=0, ge=0),
    meeting_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> TaskListRead:
    filters = []
    if meeting_id and meeting_id != "all":
        filters.append(ActionItem.meeting_id == meeting_id)

    keyword = q.strip() if q else ""
    if keyword:
        term_filters = []
        for term in task_search_terms(keyword):
            pattern = f"%{term}%"
            term_filters.extend(
                [
                    ActionItem.task.ilike(pattern),
                    ActionItem.source_text.ilike(pattern),
                    ActionItem.owner.ilike(pattern),
                    ActionItem.owner_name.ilike(pattern),
                    ActionItem.priority.ilike(pattern),
                    ActionItem.status.ilike(pattern),
                    Meeting.title.ilike(pattern),
                ]
            )
        filters.append(
            or_(
                *term_filters,
            )
        )

    base_query = select(ActionItem, Meeting.title).join(Meeting, Meeting.id == ActionItem.meeting_id).options(selectinload(ActionItem.attachments))
    count_query = select(func.count(ActionItem.id)).join(Meeting, Meeting.id == ActionItem.meeting_id)
    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0
    rows = db.execute(
        base_query.order_by(ActionItem.created_at.desc(), ActionItem.id.desc()).offset(offset).limit(limit)
    ).all()

    items = [to_task_list_item(item, meeting_title) for item, meeting_title in rows]

    return TaskListRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.patch("/{task_id}", response_model=TaskListItem)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> TaskListItem:
    item, meeting_title = get_task_row_or_404(db, task_id)
    fields = payload.model_fields_set

    if "task" in fields:
        next_task = normalize_optional_text(payload.task)
        if not next_task:
            raise HTTPException(status_code=400, detail={"reason": "task_title_required"})
        item.task = next_task
    if "description" in fields:
        item.description = normalize_optional_text(payload.description)
    if "owner" in fields:
        item.owner = normalize_optional_text(payload.owner)
        item.owner_name = None
    if "due_date" in fields:
        item.due_date = normalize_optional_text(payload.due_date)
        item.deadline = None
    if "priority" in fields:
        priority = normalize_optional_text(payload.priority)
        if priority is not None and priority not in TASK_WRITE_PRIORITIES:
            raise HTTPException(status_code=400, detail={"reason": "unsupported_task_priority", "allowed": sorted(TASK_WRITE_PRIORITIES)})
        item.priority = priority
    if "reminder_offset_minutes" in fields:
        if payload.reminder_offset_minutes is not None and payload.reminder_offset_minutes not in TASK_REMINDER_OFFSETS:
            raise HTTPException(status_code=400, detail={"reason": "unsupported_task_reminder_offset", "allowed": sorted(TASK_REMINDER_OFFSETS)})
        item.reminder_offset_minutes = payload.reminder_offset_minutes
    if "reminder_channel" in fields:
        channel = normalize_optional_text(payload.reminder_channel)
        if channel is not None and channel not in TASK_REMINDER_CHANNELS:
            raise HTTPException(status_code=400, detail={"reason": "unsupported_task_reminder_channel", "allowed": sorted(TASK_REMINDER_CHANNELS)})
        item.reminder_channel = channel

    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return to_task_list_item(item, meeting_title)


@router.patch("/{task_id}/status", response_model=TaskListItem)
def update_task_status(
    task_id: str,
    payload: TaskStatusUpdate,
    db: Session = Depends(get_db),
) -> TaskListItem:
    next_status = payload.status.strip().lower()
    if next_status not in TASK_WRITE_STATUSES:
        raise HTTPException(status_code=400, detail={"reason": "unsupported_task_status", "allowed": sorted(TASK_WRITE_STATUSES)})

    item, meeting_title = get_task_row_or_404(db, task_id)
    item.status = next_status
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return to_task_list_item(item, meeting_title)


@router.post("/{task_id}/attachments", response_model=TaskAttachmentRead)
def upload_task_attachment(
    task_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> TaskAttachmentRead:
    item = db.get(ActionItem, task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    try:
        path, file_size_bytes = save_task_attachment_file(task_id, file)
    except UnsupportedTaskAttachmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TaskAttachmentStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    attachment = TaskAttachment(
        task_id=task_id,
        filename=path.name,
        content_type=file.content_type,
        path=str(path),
        file_size_bytes=file_size_bytes,
        uploaded_at=datetime.now(timezone.utc),
    )
    item.updated_at = datetime.now(timezone.utc)
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return to_task_attachment_read(attachment)


@router.get("/{task_id}/attachments/{attachment_id}")
def get_task_attachment(
    task_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    attachment = db.scalars(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id,
        )
    ).first()
    if attachment is None:
        raise HTTPException(status_code=404, detail="task_attachment_not_found")

    path = Path(attachment.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="task_attachment_missing_from_storage")

    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.filename,
    )
