from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_security import AgentPrincipal
from app.models import ActionItem, AgentActionProposalRecord, Meeting, MeetingSummary, TranscriptSegment


SUPPORTED_FIELDS = ("owner", "due_date", "priority", "status")
DEFAULT_MIN_MATCH_CONFIDENCE = 0.72


@dataclass
class ProposalGenerationDiagnostic:
    action_item_id: str
    task: str
    matched_object_id: str | None = None
    match_reason: str = ""
    confidence: float = 0.0
    field_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    generated: bool = False
    proposal_id: str | None = None
    skip_reason: str | None = None

    def to_read_model(self) -> dict[str, Any]:
        return {
            "action_item_id": self.action_item_id,
            "task": self.task,
            "matched_object_id": self.matched_object_id,
            "match_reason": self.match_reason,
            "confidence": self.confidence,
            "field_changes": self.field_changes,
            "evidence": self.evidence,
            "generated": self.generated,
            "proposal_id": self.proposal_id,
            "skip_reason": self.skip_reason,
        }


def generate_action_item_proposals_for_meeting(
    db: Session,
    meeting_id: str,
    *,
    principal: AgentPrincipal | None = None,
    persist: bool = True,
) -> list[ProposalGenerationDiagnostic]:
    meeting = db.get(Meeting, meeting_id)
    summary = db.scalars(select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)).first()
    if meeting is None or summary is None:
        return []

    current_items = list(
        db.scalars(
            select(ActionItem)
            .where(ActionItem.meeting_id == meeting_id)
            .order_by(ActionItem.created_at.asc(), ActionItem.id.asc())
        ).all()
    )
    if not current_items:
        return []

    tenant_ids = {item.tenant_id for item in current_items if item.tenant_id}
    project_ids = {item.project_id for item in current_items if item.project_id}
    historical_items = list(
        db.scalars(
            select(ActionItem)
            .where(ActionItem.meeting_id != meeting_id)
            .where(ActionItem.tenant_id.in_(tenant_ids or {"default-tenant"}))
            .where(ActionItem.project_id.in_(project_ids or {"default-project"}))
            .order_by(ActionItem.created_at.desc(), ActionItem.id.asc())
        ).all()
    )
    transcript_segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.segment_index.asc())
        ).all()
    )

    diagnostics: list[ProposalGenerationDiagnostic] = []
    for item in current_items:
        diagnostic = ProposalGenerationDiagnostic(action_item_id=item.id, task=item.task)
        if not historical_items:
            diagnostic.skip_reason = "new_object"
            diagnostics.append(diagnostic)
            continue

        match, match_reason, confidence, ambiguous = _best_historical_match(item, historical_items)
        diagnostic.matched_object_id = match.id if match else None
        diagnostic.match_reason = match_reason
        diagnostic.confidence = confidence
        if ambiguous:
            diagnostic.skip_reason = "ambiguous_match"
            diagnostics.append(diagnostic)
            continue
        if match is None:
            diagnostic.skip_reason = "no_historical_match"
            diagnostics.append(diagnostic)
            continue

        field_changes = _field_changes(match, item)
        if not field_changes:
            diagnostic.skip_reason = "no_field_change"
            diagnostics.append(diagnostic)
            continue

        evidence = _evidence_for_changes(item, field_changes, transcript_segments)
        if not evidence:
            diagnostic.field_changes = field_changes
            diagnostic.skip_reason = "insufficient_evidence"
            diagnostics.append(diagnostic)
            continue

        proposal_id = deterministic_proposal_id(meeting_id, match.id, field_changes)
        diagnostic.field_changes = field_changes
        diagnostic.evidence = evidence
        diagnostic.proposal_id = proposal_id
        if db.get(AgentActionProposalRecord, proposal_id) is not None:
            diagnostic.skip_reason = "duplicate_proposal"
            diagnostics.append(diagnostic)
            continue

        if persist:
            proposal = AgentActionProposalRecord(
                id=proposal_id,
                action_type="update",
                target_object_type="AgentActionItem",
                target_object_id=match.id,
                expected_object_version=str(match.version),
                title=f"更新待办：{match.task}",
                description=_proposal_description(field_changes),
                proposed_changes=field_changes,
                evidence=evidence,
                confidence=round(confidence, 4),
                risk_level=_risk_level(field_changes),
                requires_confirmation=True,
                status="pending",
                reason="真实会议纪要识别到已有待办字段变化，等待人工确认。",
                metadata_={
                    "tenant_id": match.tenant_id,
                    "project_id": match.project_id,
                    "source_meeting_id": meeting_id,
                    "source_summary_id": summary.id,
                    "source_action_item_id": item.id,
                    "generated_by": "real_meeting_action_item_proposal_generator",
                    "match_reason": match_reason,
                    "field_signature": _stable_json(field_changes),
                    "diagnostic": {
                        "matched_object_id": match.id,
                        "confidence": round(confidence, 4),
                        "generated": True,
                    },
                },
            )
            db.add(proposal)
            db.flush()
        diagnostic.generated = True
        diagnostics.append(diagnostic)

    if persist:
        db.commit()
    return diagnostics


def _best_historical_match(
    item: ActionItem,
    candidates: list[ActionItem],
) -> tuple[ActionItem | None, str, float, bool]:
    scored: list[tuple[float, ActionItem]] = []
    normalized_task = _normalize_text(item.task)
    for candidate in candidates:
        score = SequenceMatcher(None, normalized_task, _normalize_text(candidate.task)).ratio()
        scored.append((score, candidate))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] < DEFAULT_MIN_MATCH_CONFIDENCE:
        return None, "title_similarity_below_threshold", scored[0][0] if scored else 0.0, False
    ambiguous = len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05
    return scored[0][1], "title_similarity", scored[0][0], ambiguous


def _field_changes(before: ActionItem, after: ActionItem) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for field_name in SUPPORTED_FIELDS:
        before_value = _field_value(before, field_name)
        after_value = _field_value(after, field_name)
        if after_value is None or before_value == after_value:
            continue
        changes[field_name] = {"from": before_value, "to": after_value}
    return changes


def _field_value(item: ActionItem, field_name: str) -> str | None:
    if field_name == "owner":
        value = item.owner_name or item.owner
    elif field_name == "due_date":
        value = item.due_date or item.deadline
    else:
        value = getattr(item, field_name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _evidence_for_changes(
    item: ActionItem,
    changes: dict[str, dict[str, Any]],
    transcript_segments: list[TranscriptSegment],
) -> list[dict[str, Any]]:
    source_text = (item.source_text or item.source or "").strip()
    if not source_text:
        return []
    missing = [
        field_name
        for field_name, change in changes.items()
        if not _is_after_value_supported(field_name, str(change.get("to") or ""), source_text)
    ]
    if missing:
        return []

    segment = _matching_segment(source_text, transcript_segments)
    evidence = {
        "source_text": source_text,
        "source_meeting_id": item.meeting_id,
        "speaker": (segment.speaker_name or segment.speaker_label) if segment else None,
        "start_time": segment.start_time if segment else None,
        "end_time": segment.end_time if segment else None,
        "source_segment_id": segment.id if segment else item.source_segment_id,
    }
    return [evidence]


def _is_after_value_supported(field_name: str, value: str, source_text: str) -> bool:
    normalized_source = _normalize_text(source_text)
    normalized_value = _normalize_text(value)
    if not normalized_value:
        return False
    if field_name == "status":
        return normalized_value in normalized_source or any(
            marker in normalized_source for marker in ("已完成", "完成了", "完成", "done", "closed", "resolved")
        )
    if field_name == "priority":
        priority_markers = {
            "high": ("高", "加急", "优先", "紧急", "high"),
            "medium": ("中", "正常", "medium"),
            "low": ("低", "不急", "low"),
        }
        return normalized_value in normalized_source or any(
            marker in normalized_source for marker in priority_markers.get(normalized_value, ())
        )
    return normalized_value in normalized_source


def _matching_segment(source_text: str, segments: list[TranscriptSegment]) -> TranscriptSegment | None:
    normalized_source = _normalize_text(source_text)
    for segment in segments:
        if normalized_source and normalized_source in _normalize_text(segment.text):
            return segment
    if not segments:
        return None
    return max(segments, key=lambda segment: SequenceMatcher(None, normalized_source, _normalize_text(segment.text)).ratio())


def deterministic_proposal_id(meeting_id: str, target_object_id: str, field_changes: dict[str, Any]) -> str:
    stable = f"{meeting_id}:{target_object_id}:{_stable_json(field_changes)}"
    return f"agent-proposal-{uuid.uuid5(uuid.NAMESPACE_URL, stable)}"


def _risk_level(field_changes: dict[str, Any]) -> str:
    return "medium" if any(field_name in field_changes for field_name in ("owner", "due_date", "priority")) else "low"


def _proposal_description(field_changes: dict[str, dict[str, Any]]) -> str:
    labels = {"owner": "负责人", "due_date": "截止时间", "priority": "优先级", "status": "状态"}
    return "；".join(
        f"{labels.get(field_name, field_name)}：{change.get('from') or '未设置'} -> {change.get('to')}"
        for field_name, change in field_changes.items()
    )


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())
