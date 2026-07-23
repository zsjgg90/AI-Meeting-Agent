from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ActionItem,
    Meeting,
    MeetingKnowledgeItem,
    MeetingKnowledgeSync,
    MeetingSummary,
    TranscriptSegment,
)
from app.observability import log_event, safe_error

DEFAULT_TENANT_ID = "default-tenant"
DEFAULT_PROJECT_ID = "default-project"
KNOWLEDGE_ITEM_STATUSES = {"active", "stale", "deleted"}
KNOWLEDGE_SYNC_STATUSES = {"pending", "indexing", "completed", "failed"}
EVIDENCE_PREFIX_RE = re.compile(
    r"^\s*(?P<speaker>[^（(:：]+?)\s*[（(](?P<start>\d+(?:\.\d+)?)\s*-\s*(?P<end>\d+(?:\.\d+)?)\s*[）)]\s*[:：]\s*(?P<text>.+)\s*$",
    re.DOTALL,
)


@dataclass(frozen=True)
class KnowledgeDraft:
    content_type: str
    source_item_key: str
    title: str
    content: str
    evidence_text: str | None = None
    source_segment_id: str | None = None
    speaker_label: str | None = None
    start_time: float | None = None
    end_time: float | None = None

    @property
    def content_hash(self) -> str:
        payload = "\n".join(
            [
                self.content_type,
                self.source_item_key,
                self.title,
                self.content,
                self.evidence_text or "",
                self.source_segment_id or "",
                self.speaker_label or "",
                "" if self.start_time is None else str(self.start_time),
                "" if self.end_time is None else str(self.end_time),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParsedEvidence:
    text: str | None = None
    speaker_label: str | None = None
    start_time: float | None = None
    end_time: float | None = None


def sync_meeting_knowledge(db: Session, meeting_id: str) -> MeetingKnowledgeSync:
    started_at = utc_now()
    sync = db.get(MeetingKnowledgeSync, meeting_id)
    if sync is None:
        sync = MeetingKnowledgeSync(meeting_id=meeting_id, status="pending", source_version="", item_count=0)
        db.add(sync)
        db.flush()
    sync.status = "indexing"
    sync.sync_error = None
    sync.started_at = started_at
    sync.completed_at = None
    sync.updated_at = started_at
    db.commit()

    try:
        meeting = db.get(Meeting, meeting_id)
        summary = db.scalars(select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)).first()
        if meeting is None or summary is None:
            raise ValueError("Meeting and completed formal summary are required for knowledge sync.")

        source_version = _source_version(summary)
        tenant_id, project_id = _resolve_scope(db, meeting_id)
        transcripts = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.meeting_id == meeting_id)
                .order_by(TranscriptSegment.segment_index.asc(), TranscriptSegment.start_time.asc())
            ).all()
        )
        actions = list(
            db.scalars(
                select(ActionItem)
                .where(ActionItem.meeting_id == meeting_id)
                .order_by(ActionItem.created_at.asc(), ActionItem.id.asc())
            ).all()
        )
        drafts = _build_drafts(meeting, summary, actions, transcripts)
        active_keys = {(draft.content_type, draft.source_item_key) for draft in drafts}

        existing = {
            (item.content_type, item.source_item_key): item
            for item in db.scalars(select(MeetingKnowledgeItem).where(MeetingKnowledgeItem.meeting_id == meeting_id)).all()
        }

        now = utc_now()
        for draft in drafts:
            row = existing.get((draft.content_type, draft.source_item_key))
            if row is None:
                row = MeetingKnowledgeItem(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    meeting_id=meeting_id,
                    content_type=draft.content_type,
                    source_item_key=draft.source_item_key,
                    content_hash=draft.content_hash,
                    title=draft.title,
                    content=draft.content,
                    evidence_text=draft.evidence_text,
                    source_segment_id=draft.source_segment_id,
                    speaker_label=draft.speaker_label,
                    start_time=draft.start_time,
                    end_time=draft.end_time,
                    status="active",
                    source_version=source_version,
                )
                db.add(row)
                continue

            row.tenant_id = tenant_id
            row.project_id = project_id
            row.content_hash = draft.content_hash
            row.title = draft.title
            row.content = draft.content
            row.evidence_text = draft.evidence_text
            row.source_segment_id = draft.source_segment_id
            row.speaker_label = draft.speaker_label
            row.start_time = draft.start_time
            row.end_time = draft.end_time
            row.status = "active"
            row.source_version = source_version
            row.deleted_at = None
            row.updated_at = now

        for key, row in existing.items():
            if row.status == "deleted":
                continue
            if key not in active_keys:
                row.status = "stale"
                row.source_version = source_version
                row.updated_at = now

        sync = db.get(MeetingKnowledgeSync, meeting_id) or sync
        sync.status = "completed"
        sync.source_version = source_version
        sync.item_count = len(drafts)
        sync.sync_error = None
        sync.completed_at = now
        sync.updated_at = now
        db.commit()
        log_event("knowledge_sync.completed", meeting_id=meeting_id, item_count=len(drafts), source_version=source_version)
        return sync
    except Exception as exc:
        db.rollback()
        sync = db.get(MeetingKnowledgeSync, meeting_id)
        if sync is None:
            sync = MeetingKnowledgeSync(meeting_id=meeting_id, status="failed", source_version="", item_count=0)
            db.add(sync)
        sync.status = "failed"
        sync.sync_error = safe_error(exc)
        sync.completed_at = utc_now()
        sync.updated_at = sync.completed_at
        db.commit()
        log_event("knowledge_sync.failed", level="error", meeting_id=meeting_id, error_message=safe_error(exc))
        return sync


def mark_meeting_knowledge_deleted(db: Session, meeting_id: str) -> int:
    now = utc_now()
    rows = list(
        db.scalars(
            select(MeetingKnowledgeItem).where(
                MeetingKnowledgeItem.meeting_id == meeting_id,
                MeetingKnowledgeItem.status != "deleted",
            )
        ).all()
    )
    for row in rows:
        row.status = "deleted"
        row.deleted_at = now
        row.updated_at = now
    sync = db.get(MeetingKnowledgeSync, meeting_id)
    if sync is not None:
        sync.status = "completed"
        sync.item_count = 0
        sync.completed_at = now
        sync.updated_at = now
    db.commit()
    return len(rows)


def run_knowledge_sync_safely(meeting_id: str, session_factory) -> None:  # noqa: ANN001
    db = session_factory()
    try:
        sync_meeting_knowledge(db, meeting_id)
    except Exception as exc:
        log_event("knowledge_sync.unhandled", level="error", meeting_id=meeting_id, error_message=safe_error(exc))
    finally:
        db.close()


def _build_drafts(
    meeting: Meeting,
    summary: MeetingSummary,
    actions: list[ActionItem],
    transcripts: list[TranscriptSegment],
) -> list[KnowledgeDraft]:
    drafts: list[KnowledgeDraft] = []
    meeting_title = meeting.title or "Untitled meeting"
    summary_text = _clean(summary.meeting_summary or summary.overview)
    if summary_text:
        drafts.append(
            KnowledgeDraft(
                content_type="meeting_summary",
                source_item_key="meeting_summary:0",
                title=meeting_title,
                content=summary_text,
            )
        )

    drafts.extend(
        _drafts_from_summary_array(
            content_type="meeting_agenda",
            items=summary.meeting_agenda or summary.agenda,
            title_prefix="会议议程",
            content_keys=("item", "title", "summary"),
            evidence_keys=("source_text", "source", "summary"),
            transcripts=transcripts,
        )
    )
    drafts.extend(
        _drafts_from_summary_array(
            content_type="key_decision",
            items=summary.key_conclusions or summary.decisions,
            title_prefix="关键决策",
            content_keys=("conclusion", "decision", "title", "summary"),
            evidence_keys=("source_text", "source"),
            transcripts=transcripts,
        )
    )
    drafts.extend(_drafts_from_actions(actions, transcripts))
    drafts.extend(
        _drafts_from_summary_array(
            content_type="unresolved_issue",
            items=summary.unresolved_issues or summary.open_questions,
            title_prefix="遗留问题",
            content_keys=("issue", "question", "title", "summary"),
            evidence_keys=("source_text", "source", "reason", "blocker"),
            transcripts=transcripts,
        )
    )
    drafts.extend(
        _drafts_from_summary_array(
            content_type="risk",
            items=summary.risks_and_focus or summary.risks,
            title_prefix="风险记录",
            content_keys=("risk", "title", "summary", "focus_area"),
            evidence_keys=("source_text", "source", "impact", "mitigation"),
            transcripts=transcripts,
        )
    )
    drafts.extend(_drafts_from_transcripts(transcripts, meeting_title))
    return drafts


def _drafts_from_summary_array(
    *,
    content_type: str,
    items: Any,
    title_prefix: str,
    content_keys: tuple[str, ...],
    evidence_keys: tuple[str, ...],
    transcripts: list[TranscriptSegment],
) -> list[KnowledgeDraft]:
    if not isinstance(items, list):
        return []
    drafts: list[KnowledgeDraft] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            content = _clean(item)
            evidence = None
            segment_id = None
        elif isinstance(item, dict):
            content = _first_text(item, content_keys)
            if content_type == "risk":
                impact = _clean(item.get("impact"))
                mitigation = _clean(item.get("mitigation"))
                extras = []
                if impact:
                    extras.append(f"潜在影响：{impact}")
                if mitigation:
                    extras.append(f"缓解措施：{mitigation}")
                if extras:
                    content = "\n".join([content, *extras])
            evidence = _first_text(item, evidence_keys) or None
            segment_id = _clean(item.get("source_segment_id")) or None
        else:
            continue
        if not content:
            continue
        parsed = _parse_evidence_prefix(evidence)
        segment = _segment_by_id_or_text(transcripts, segment_id, evidence or content)
        drafts.append(
            KnowledgeDraft(
                content_type=content_type,
                source_item_key=f"{content_type}:{index}",
                title=f"{title_prefix} {index + 1}",
                content=content,
                evidence_text=evidence,
                source_segment_id=segment.id if segment else segment_id,
                speaker_label=segment.speaker_label if segment else parsed.speaker_label,
                start_time=segment.start_time if segment else parsed.start_time,
                end_time=segment.end_time if segment else parsed.end_time,
            )
        )
    return drafts


def _drafts_from_actions(actions: list[ActionItem], transcripts: list[TranscriptSegment]) -> list[KnowledgeDraft]:
    drafts: list[KnowledgeDraft] = []
    for index, item in enumerate(actions):
        content = _clean(item.task)
        if not content:
            continue
        evidence = _clean(item.source_text or item.source) or None
        parsed = _parse_evidence_prefix(evidence)
        segment = _segment_by_id_or_text(transcripts, item.source_segment_id, evidence or content)
        drafts.append(
            KnowledgeDraft(
                content_type="action_item",
                source_item_key=f"action_item:{index}",
                title=f"待办 {index + 1}",
                content=content,
                evidence_text=evidence,
                source_segment_id=segment.id if segment else item.source_segment_id,
                speaker_label=segment.speaker_label if segment else parsed.speaker_label,
                start_time=segment.start_time if segment else parsed.start_time,
                end_time=segment.end_time if segment else parsed.end_time,
            )
        )
    return drafts


def _drafts_from_transcripts(transcripts: list[TranscriptSegment], meeting_title: str) -> list[KnowledgeDraft]:
    drafts: list[KnowledgeDraft] = []
    for segment in transcripts:
        content = _clean(segment.text)
        if not content:
            continue
        drafts.append(
            KnowledgeDraft(
                content_type="transcript",
                source_item_key=f"transcript:{segment.id}",
                title=meeting_title,
                content=content,
                evidence_text=content,
                source_segment_id=segment.id,
                speaker_label=segment.speaker_label,
                start_time=segment.start_time,
                end_time=segment.end_time,
            )
        )
    return drafts


def _resolve_scope(db: Session, meeting_id: str) -> tuple[str, str]:
    rows = list(db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id)).all())
    tenant_ids = {row.tenant_id for row in rows if row.tenant_id and row.tenant_id != DEFAULT_TENANT_ID}
    project_ids = {row.project_id for row in rows if row.project_id and row.project_id != DEFAULT_PROJECT_ID}
    tenant_id = next(iter(tenant_ids)) if len(tenant_ids) == 1 else DEFAULT_TENANT_ID
    project_id = next(iter(project_ids)) if len(project_ids) == 1 else DEFAULT_PROJECT_ID
    return tenant_id, project_id


def _segment_by_id_or_text(
    transcripts: list[TranscriptSegment],
    source_segment_id: str | None,
    source_text: str | None,
) -> TranscriptSegment | None:
    if source_segment_id:
        for segment in transcripts:
            if segment.id == source_segment_id:
                return segment
    parsed = _parse_evidence_prefix(source_text)
    if parsed.start_time is not None and parsed.end_time is not None:
        for segment in transcripts:
            if _times_match(segment.start_time, parsed.start_time) and _times_match(segment.end_time, parsed.end_time):
                return segment
    normalized_source = _normalize(parsed.text or source_text or "")
    if not normalized_source:
        return None
    for segment in transcripts:
        normalized_segment = _normalize(segment.text)
        if normalized_segment and (
            normalized_segment in normalized_source or normalized_source in normalized_segment
        ):
            return segment
    return None


def _parse_evidence_prefix(source_text: str | None) -> ParsedEvidence:
    value = _clean(source_text)
    if not value:
        return ParsedEvidence()
    match = EVIDENCE_PREFIX_RE.match(value)
    if not match:
        return ParsedEvidence(text=value)
    try:
        start_time = float(match.group("start"))
        end_time = float(match.group("end"))
    except ValueError:
        start_time = None
        end_time = None
    return ParsedEvidence(
        text=_clean(match.group("text")) or value,
        speaker_label=_clean(match.group("speaker")) or None,
        start_time=start_time,
        end_time=end_time,
    )


def _times_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) < 0.05


def _source_version(summary: MeetingSummary) -> str:
    updated = summary.updated_at or summary.created_at
    return f"{summary.id}:{updated.isoformat() if updated else ''}"


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean(item.get(key))
        if value:
            return value
    return ""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: str) -> str:
    return "".join(str(value or "").split()).lower()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
