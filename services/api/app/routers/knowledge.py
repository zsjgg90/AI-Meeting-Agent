from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, false, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Meeting, MeetingKnowledgeItem, MeetingKnowledgeSync, MeetingSummary, TranscriptSegment
from app.schemas import (
    KnowledgeItemRead,
    KnowledgeListRead,
    KnowledgeMeetingItemRead,
    KnowledgeMeetingListRead,
    KnowledgeOverviewRead,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

STRUCTURED_CONTENT_TYPES = {
    "meeting_summary",
    "meeting_agenda",
    "key_decision",
    "action_item",
    "unresolved_issue",
    "risk",
    "transcript",
}

SEARCH_PRIORITY = {
    "key_decision": 10,
    "unresolved_issue": 20,
    "risk": 21,
    "meeting_summary": 30,
    "meeting_agenda": 31,
    "action_item": 40,
    "transcript": 50,
}


@router.get("/overview", response_model=KnowledgeOverviewRead)
def overview(db: Session = Depends(get_db)) -> KnowledgeOverviewRead:
    active = _active_item_filter()
    meeting_count = db.scalar(
        select(func.count(Meeting.id)).join(MeetingSummary, MeetingSummary.meeting_id == Meeting.id).where(Meeting.status == "completed")
    ) or 0
    decision_count = db.scalar(select(func.count(MeetingKnowledgeItem.id)).where(*active, MeetingKnowledgeItem.content_type == "key_decision")) or 0
    issue_count = db.scalar(select(func.count(MeetingKnowledgeItem.id)).where(*active, MeetingKnowledgeItem.content_type == "unresolved_issue")) or 0
    risk_count = db.scalar(select(func.count(MeetingKnowledgeItem.id)).where(*active, MeetingKnowledgeItem.content_type == "risk")) or 0
    all_count = db.scalar(select(func.count(MeetingKnowledgeItem.id)).where(*active)) or 0
    sync_rows = db.execute(select(MeetingKnowledgeSync.status, func.count(MeetingKnowledgeSync.meeting_id)).group_by(MeetingKnowledgeSync.status)).all()
    return KnowledgeOverviewRead(
        meeting_count=meeting_count,
        decision_count=decision_count,
        unresolved_issue_count=issue_count,
        risk_count=risk_count,
        all_count=all_count,
        sync_status={status: count for status, count in sync_rows},
    )


@router.get("/meetings", response_model=KnowledgeMeetingListRead)
def meetings(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None),
    meeting_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeMeetingListRead:
    filters = _meeting_filters(query=query, meeting_type=meeting_type, date_from=date_from, date_to=date_to)
    base = select(Meeting).join(MeetingSummary, MeetingSummary.meeting_id == Meeting.id).where(Meeting.status == "completed", *filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(db.scalars(base.order_by(Meeting.created_at.desc(), Meeting.id.desc()).offset(offset).limit(limit)).all())
    meeting_ids = [row.id for row in rows]
    counts = _knowledge_counts_by_meeting(db, meeting_ids)
    durations = _duration_by_meeting(db, meeting_ids)
    items = [
        KnowledgeMeetingItemRead(
            meeting_id=row.id,
            title=row.title,
            meeting_type=None,
            meeting_time=row.start_at or row.created_at,
            duration=_meeting_duration(row, durations.get(row.id)),
            summary_status=row.status,
            conclusion_count=counts.get(row.id, {}).get("key_decision", 0),
            action_count=counts.get(row.id, {}).get("action_item", 0),
            unresolved_issue_count=counts.get(row.id, {}).get("unresolved_issue", 0),
            risk_count=counts.get(row.id, {}).get("risk", 0),
        )
        for row in rows
    ]
    return KnowledgeMeetingListRead(items=items, total=total, limit=limit, offset=offset, has_more=offset + len(items) < total)


@router.get("/decisions", response_model=KnowledgeListRead)
def decisions(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None),
    meeting_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeListRead:
    return _list_items(
        db,
        content_types=["key_decision"],
        query=query,
        meeting_type=meeting_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/issues", response_model=KnowledgeListRead)
def issues(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None),
    meeting_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeListRead:
    return _list_items(
        db,
        content_types=["unresolved_issue"],
        query=query,
        meeting_type=meeting_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/risks", response_model=KnowledgeListRead)
def risks(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None),
    meeting_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeListRead:
    return _list_items(
        db,
        content_types=["risk"],
        query=query,
        meeting_type=meeting_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=KnowledgeListRead)
def search(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    meeting_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeListRead:
    content_types = None
    if content_type and content_type != "all":
        content_types = [item.strip() for item in content_type.split(",") if item.strip() in STRUCTURED_CONTENT_TYPES]
    return _list_items(
        db,
        content_types=content_types,
        query=query,
        meeting_type=meeting_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        priority_order=True,
    )


def _list_items(
    db: Session,
    *,
    content_types: list[str] | None,
    query: str | None,
    meeting_type: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
    priority_order: bool = False,
) -> KnowledgeListRead:
    filters = [
        *_active_item_filter(),
        *_meeting_filters(query=None, meeting_type=meeting_type, date_from=date_from, date_to=date_to),
    ]
    keyword = (query or "").strip()
    if content_types:
        filters.append(MeetingKnowledgeItem.content_type.in_(content_types))
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                MeetingKnowledgeItem.title.ilike(pattern),
                MeetingKnowledgeItem.content.ilike(pattern),
                MeetingKnowledgeItem.evidence_text.ilike(pattern),
                Meeting.title.ilike(pattern),
            )
        )

    base = (
        select(MeetingKnowledgeItem, Meeting.title, Meeting.start_at, Meeting.created_at)
        .join(Meeting, Meeting.id == MeetingKnowledgeItem.meeting_id)
        .join(MeetingSummary, MeetingSummary.meeting_id == Meeting.id)
        .where(Meeting.status == "completed", *filters)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    if priority_order:
        order_expr = case(SEARCH_PRIORITY, value=MeetingKnowledgeItem.content_type, else_=90)
        base = base.order_by(order_expr.asc(), Meeting.created_at.desc(), MeetingKnowledgeItem.id.desc())
    else:
        base = base.order_by(Meeting.created_at.desc(), MeetingKnowledgeItem.id.desc())
    rows = db.execute(base.offset(offset).limit(limit)).all()
    items = [
        _read_item(row, meeting_title, meeting_start_at or meeting_created_at, keyword)
        for row, meeting_title, meeting_start_at, meeting_created_at in rows
    ]
    return KnowledgeListRead(items=items, total=total, limit=limit, offset=offset, has_more=offset + len(items) < total)


def _read_item(row: MeetingKnowledgeItem, meeting_title: str, meeting_date: datetime | None, keyword: str) -> KnowledgeItemRead:
    return KnowledgeItemRead(
        id=row.id,
        content_type=row.content_type,
        title=row.title,
        content=row.content,
        meeting_id=row.meeting_id,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        evidence_text=row.evidence_text,
        source_segment_id=row.source_segment_id,
        speaker_label=row.speaker_label,
        start_time=row.start_time,
        end_time=row.end_time,
        highlight=_highlight(row.content, row.evidence_text, keyword),
    )


def _active_item_filter() -> list:
    return [MeetingKnowledgeItem.status == "active", MeetingKnowledgeItem.deleted_at.is_(None)]


def _meeting_filters(
    *,
    query: str | None,
    meeting_type: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list:
    filters = []
    keyword = (query or "").strip()
    if keyword:
        filters.append(Meeting.title.ilike(f"%{keyword}%"))
    if meeting_type and meeting_type != "all":
        filters.append(false())
    if date_from is not None:
        filters.append(func.coalesce(Meeting.start_at, Meeting.created_at) >= date_from)
    if date_to is not None:
        filters.append(func.coalesce(Meeting.start_at, Meeting.created_at) <= date_to)
    return filters


def _knowledge_counts_by_meeting(db: Session, meeting_ids: list[str]) -> dict[str, dict[str, int]]:
    if not meeting_ids:
        return {}
    rows = db.execute(
        select(MeetingKnowledgeItem.meeting_id, MeetingKnowledgeItem.content_type, func.count(MeetingKnowledgeItem.id))
        .where(MeetingKnowledgeItem.meeting_id.in_(meeting_ids), *_active_item_filter())
        .group_by(MeetingKnowledgeItem.meeting_id, MeetingKnowledgeItem.content_type)
    ).all()
    result: dict[str, dict[str, int]] = {}
    for meeting_id, content_type, count in rows:
        result.setdefault(meeting_id, {})[content_type] = count
    return result


def _duration_by_meeting(db: Session, meeting_ids: list[str]) -> dict[str, float]:
    if not meeting_ids:
        return {}
    rows = db.execute(
        select(TranscriptSegment.meeting_id, func.max(TranscriptSegment.end_time))
        .where(TranscriptSegment.meeting_id.in_(meeting_ids))
        .group_by(TranscriptSegment.meeting_id)
    ).all()
    return {meeting_id: float(duration or 0.0) for meeting_id, duration in rows}


def _meeting_duration(meeting: Meeting, transcript_duration: float | None) -> float | None:
    if meeting.start_at and meeting.end_at and meeting.end_at > meeting.start_at:
        return (meeting.end_at - meeting.start_at).total_seconds()
    return transcript_duration if transcript_duration and transcript_duration > 0 else None


def _highlight(content: str, evidence: str | None, keyword: str) -> str | None:
    if not keyword:
        return None
    haystacks = [content, evidence or ""]
    lower_keyword = keyword.lower()
    for value in haystacks:
        index = value.lower().find(lower_keyword)
        if index >= 0:
            start = max(0, index - 24)
            end = min(len(value), index + len(keyword) + 36)
            return value[start:end]
    return None
