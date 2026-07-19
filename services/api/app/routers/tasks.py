from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ActionItem, Meeting
from app.schemas import TaskListItem, TaskListRead

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                ActionItem.task.ilike(pattern),
                ActionItem.source_text.ilike(pattern),
                Meeting.title.ilike(pattern),
            )
        )

    base_query = select(ActionItem, Meeting.title).join(Meeting, Meeting.id == ActionItem.meeting_id)
    count_query = select(func.count(ActionItem.id)).join(Meeting, Meeting.id == ActionItem.meeting_id)
    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0
    rows = db.execute(
        base_query.order_by(ActionItem.created_at.desc(), ActionItem.id.desc()).offset(offset).limit(limit)
    ).all()

    items = [
        TaskListItem(
            id=item.id,
            meeting_id=item.meeting_id,
            meeting_title=meeting_title,
            task=item.task,
            owner=item.owner,
            owner_name=item.owner_name,
            due_date=item.due_date,
            deadline=item.deadline,
            priority=item.priority,
            status=item.status,
            source=item.source,
            source_text=item.source_text,
            source_segment_id=item.source_segment_id,
            confidence=item.confidence,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item, meeting_title in rows
    ]

    return TaskListRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )
