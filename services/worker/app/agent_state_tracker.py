from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.agent_contract import (
    AgentActionItem,
    AgentActionProposal,
    AgentContext,
    AgentStateChangeType,
    EvidenceRef,
    Requirement,
    Risk,
    RiskLevel,
)


AGENT_STATE_TRACKER_SCHEMA_VERSION = "agent-state-tracker-v1"

TrackedObjectType = Literal["Requirement", "AgentActionItem", "Risk"]
TrackedObject = Requirement | AgentActionItem | Risk

_TERMINAL_BY_TYPE: dict[TrackedObjectType, set[str]] = {
    "Requirement": {"implemented"},
    "AgentActionItem": {"completed"},
    "Risk": {"mitigated", "accepted", "closed"},
}
_DEFERRED_STATUSES = {"deferred"}
_CANCELLED_STATUSES = {"cancelled"}
_FORMAL_STATUS_FIELDS = {"status"}


class NormalizedAgentObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_type: TrackedObjectType
    object_id: str = ""
    project_id: str = ""
    title: str = ""
    normalized_title: str = ""
    keywords: set[str] = Field(default_factory=set)
    owner: str | None = None
    source_meeting_id: str = ""
    status: str = "unknown"
    evidence: list[EvidenceRef] = Field(default_factory=list)
    due_date: str | None = None
    raw: TrackedObject


class ObjectMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current_object: NormalizedAgentObject
    candidate: NormalizedAgentObject | None = None
    candidates_considered: list[dict[str, Any]] = Field(default_factory=list)
    match_type: AgentStateChangeType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_review: bool = False
    reason: str = ""
    conflict_reasons: list[str] = Field(default_factory=list)


class CrossMeetingStateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = AGENT_STATE_TRACKER_SCHEMA_VERSION
    proposals: list[AgentActionProposal] = Field(default_factory=list)
    matches: list[ObjectMatch] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistoricalObjectReader:
    def read(
        self,
        *,
        context: AgentContext,
        historical_objects: list[TrackedObject | dict[str, Any]] | None = None,
    ) -> list[TrackedObject]:
        objects: list[TrackedObject] = []
        for value in historical_objects or []:
            coerced = coerce_tracked_object(value)
            if coerced is not None:
                objects.append(coerced)
        objects.extend(context.requirements)
        objects.extend(context.open_action_items)
        objects.extend(context.active_risks)
        objects.extend(_objects_from_meeting_history(context.meeting_history))
        return objects


class CrossMeetingStateTracker:
    def __init__(self, *, reader: HistoricalObjectReader | None = None) -> None:
        self.reader = reader or HistoricalObjectReader()

    def analyze(
        self,
        *,
        context: AgentContext,
        current_objects: list[TrackedObject | dict[str, Any]],
        historical_objects: list[TrackedObject | dict[str, Any]] | None = None,
    ) -> CrossMeetingStateResult:
        history = self.reader.read(context=context, historical_objects=historical_objects)
        normalized_history = [
            normalize_agent_object(item, default_project_id=context.project_id)
            for item in history
        ]
        normalized_current = [
            normalize_agent_object(item, default_project_id=context.project_id)
            for item in current_objects
            if coerce_tracked_object(item) is not None
        ]

        matches = [
            match_current_object(current=current, candidates=normalized_history)
            for current in normalized_current
        ]
        proposals = [build_action_proposal(match) for match in matches]
        proposals = validate_action_proposals(proposals, matches)
        return CrossMeetingStateResult(
            proposals=proposals,
            matches=matches,
            metadata={
                "current_object_count": len(normalized_current),
                "historical_candidate_count": len(normalized_history),
                "schema_version": AGENT_STATE_TRACKER_SCHEMA_VERSION,
                "writes_performed": False,
                "external_calls_performed": False,
            },
        )


def normalize_agent_object(
    value: TrackedObject | dict[str, Any],
    *,
    default_project_id: str = "",
) -> NormalizedAgentObject:
    obj = coerce_tracked_object(value)
    if obj is None:
        raise ValueError("Unsupported Agent object type.")
    object_type = object_type_for(obj)
    title = _object_title(obj)
    evidence = list(getattr(obj, "evidence", []) or [])
    return NormalizedAgentObject(
        object_type=object_type,
        object_id=_object_id(obj),
        project_id=_object_project_id(obj, default_project_id=default_project_id),
        title=title,
        normalized_title=normalize_title(title),
        keywords=extract_keywords(title, getattr(obj, "description", "")),
        owner=_normalize_optional(getattr(obj, "owner", None)),
        source_meeting_id=str(getattr(obj, "source_meeting_id", "") or ""),
        status=str(getattr(obj, "status", "unknown") or "unknown"),
        evidence=evidence,
        due_date=_normalize_optional(getattr(obj, "due_date", None)),
        raw=obj,
    )


def match_current_object(
    *,
    current: NormalizedAgentObject,
    candidates: list[NormalizedAgentObject],
) -> ObjectMatch:
    scored: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if candidate.object_type != current.object_type:
            continue
        if current.project_id and candidate.project_id and current.project_id != candidate.project_id:
            continue
        score, reasons = score_candidate(current=current, candidate=candidate)
        if score <= 0:
            continue
        scored.append(
            {
                "object_id": candidate.object_id,
                "candidate_index": index,
                "object_type": candidate.object_type,
                "score": round(score, 4),
                "reasons": reasons,
                "status": candidate.status,
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)

    if not scored:
        return ObjectMatch(
            current_object=current,
            match_type="new",
            confidence=0.6 if has_sufficient_evidence(current) else 0.35,
            needs_review=not has_sufficient_evidence(current),
            reason="no historical candidate matched deterministic filters",
        )

    top = scored[0]
    candidate = candidates[int(top["candidate_index"])]
    conflicts = conflict_reasons(current=current, candidate=candidate)
    if float(top["score"]) < 0.4:
        return ObjectMatch(
            current_object=current,
            candidate=candidate,
            candidates_considered=scored,
            match_type="uncertain",
            confidence=float(top["score"]),
            needs_review=True,
            reason="best candidate score is below the reliable threshold",
            conflict_reasons=conflicts,
        )
    if len(scored) > 1 and _is_duplicate_cluster(scored):
        return ObjectMatch(
            current_object=current,
            candidate=candidate,
            candidates_considered=scored,
            match_type="duplicate",
            confidence=float(top["score"]),
            needs_review=bool(conflicts),
            reason="multiple strong candidates matched the same normalized object",
            conflict_reasons=conflicts,
        )

    change = determine_state_change(current=current, candidate=candidate)
    if conflicts:
        change = "uncertain"
    return ObjectMatch(
        current_object=current,
        candidate=candidate,
        candidates_considered=scored,
        match_type=change,
        confidence=float(top["score"]),
        needs_review=change == "uncertain" or not has_sufficient_evidence(current) or bool(conflicts),
        reason=reason_for_change(change, current=current, candidate=candidate),
        conflict_reasons=conflicts,
    )


def score_candidate(*, current: NormalizedAgentObject, candidate: NormalizedAgentObject) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if current.object_id and candidate.object_id and current.object_id == candidate.object_id:
        return 1.0, ["object_id_exact"]
    if current.normalized_title and current.normalized_title == candidate.normalized_title:
        score += 0.45
        reasons.append("normalized_title_exact")
    overlap = keyword_overlap(current.keywords, candidate.keywords)
    if overlap > 0:
        score += min(0.2, 0.2 * overlap)
        reasons.append("keyword_overlap")
    if current.owner and candidate.owner and current.owner == candidate.owner:
        score += 0.15
        reasons.append("owner_exact")
    if current.source_meeting_id and candidate.source_meeting_id and current.source_meeting_id == candidate.source_meeting_id:
        score += 0.05
        reasons.append("source_meeting_exact")
    if current.status and candidate.status and current.status == candidate.status:
        score += 0.05
        reasons.append("status_exact")
    similarity = SequenceMatcher(None, current.normalized_title, candidate.normalized_title).ratio()
    if similarity >= 0.55:
        score += min(0.1, similarity * 0.1)
        reasons.append("title_similarity")
    return min(score, 0.99), reasons


def determine_state_change(
    *,
    current: NormalizedAgentObject,
    candidate: NormalizedAgentObject,
) -> AgentStateChangeType:
    current_status = current.status.lower()
    if current_status in _TERMINAL_BY_TYPE[current.object_type]:
        return "complete"
    if current_status in _DEFERRED_STATUSES:
        return "defer"
    if current_status in _CANCELLED_STATUSES:
        return "cancel"
    changes = proposed_changes(current=current, candidate=candidate)
    if not changes:
        return "duplicate"
    return "update"


def build_action_proposal(match: ObjectMatch) -> AgentActionProposal:
    current = match.current_object
    candidate = match.candidate
    changes = (
        {"create": _object_dump(current.raw)}
        if match.match_type == "new"
        else proposed_changes(current=current, candidate=candidate) if candidate is not None else {}
    )
    confirmation_reasons = confirmation_reasons_for(match=match, proposed_changes=changes)
    requires_confirmation = bool(confirmation_reasons)
    return AgentActionProposal(
        proposal_id=proposal_id_for(match),
        action_type=match.match_type,
        target_object_type=current.object_type,
        target_object_id=None if match.match_type == "new" else (candidate.object_id if candidate else None),
        title=current.title,
        description=description_for(match),
        proposed_changes=changes,
        evidence=current.evidence,
        confidence=round(match.confidence, 4),
        risk_level=risk_level_for(match),
        requires_confirmation=requires_confirmation,
        needs_confirmation=requires_confirmation,
        status="proposed",
        reason=match.reason,
        metadata={
            "schema_version": AGENT_STATE_TRACKER_SCHEMA_VERSION,
            "needs_review": match.needs_review or requires_confirmation,
            "confirmation_reasons": confirmation_reasons,
            "match_candidates": match.candidates_considered,
            "conflict_reasons": match.conflict_reasons,
            "writes_performed": False,
        },
    )


def validate_action_proposals(
    proposals: list[AgentActionProposal],
    matches: list[ObjectMatch],
) -> list[AgentActionProposal]:
    validated: list[AgentActionProposal] = []
    for proposal, match in zip(proposals, matches, strict=False):
        metadata = dict(proposal.metadata)
        reasons = set(metadata.get("confirmation_reasons") or [])
        if proposal.action_type == "uncertain":
            reasons.add("uncertain_match")
        if not has_sufficient_evidence(match.current_object):
            reasons.add("insufficient_evidence")
        if match.conflict_reasons:
            reasons.add("historical_conflict")
        requires_confirmation = bool(reasons)
        metadata["confirmation_reasons"] = sorted(reasons)
        metadata["needs_review"] = bool(metadata.get("needs_review") or requires_confirmation)
        validated.append(
            proposal.model_copy(
                update={
                    "requires_confirmation": requires_confirmation,
                    "needs_confirmation": requires_confirmation,
                    "metadata": metadata,
                }
            )
        )
    return validated


def proposed_changes(
    *,
    current: NormalizedAgentObject,
    candidate: NormalizedAgentObject | None,
) -> dict[str, Any]:
    if candidate is None:
        return {}
    changes: dict[str, Any] = {}
    for field in ("title", "owner", "status", "due_date"):
        before = getattr(candidate, field)
        after = getattr(current, field)
        if _normalize_optional(before) != _normalize_optional(after):
            changes[field] = {"from": before, "to": after}
    for field in ("description", "priority", "target_version", "level", "impact", "probability", "mitigation"):
        before = getattr(candidate.raw, field, None)
        after = getattr(current.raw, field, None)
        if before != after:
            changes[field] = {"from": before, "to": after}
    return changes


def confirmation_reasons_for(
    *,
    match: ObjectMatch,
    proposed_changes: dict[str, Any],
) -> list[str]:
    reasons: set[str] = set()
    if "owner" in proposed_changes:
        reasons.add("owner_change")
    if "due_date" in proposed_changes:
        reasons.add("deadline_change")
    if "status" in proposed_changes and "status" in _FORMAL_STATUS_FIELDS:
        reasons.add("formal_status_change")
    if match.match_type == "cancel" and match.current_object.object_type == "Requirement":
        reasons.add("cancel_requirement")
    if _closes_high_risk(match):
        reasons.add("close_high_risk")
    if match.match_type == "uncertain":
        reasons.add("uncertain_match")
    if not has_sufficient_evidence(match.current_object):
        reasons.add("insufficient_evidence")
    if match.conflict_reasons:
        reasons.add("historical_conflict")
    return sorted(reasons)


def conflict_reasons(
    *,
    current: NormalizedAgentObject,
    candidate: NormalizedAgentObject,
) -> list[str]:
    reasons: list[str] = []
    if current.status == "unknown" or candidate.status == "unknown":
        reasons.append("status_unknown")
    if candidate.status in _TERMINAL_BY_TYPE[candidate.object_type] and current.status not in _TERMINAL_BY_TYPE[current.object_type]:
        reasons.append("terminal_status_conflict")
    if candidate.status in _CANCELLED_STATUSES and current.status not in _CANCELLED_STATUSES:
        reasons.append("cancelled_status_conflict")
    return reasons


def has_sufficient_evidence(value: NormalizedAgentObject) -> bool:
    return any(str(evidence.source_text or "").strip() for evidence in value.evidence)


def reason_for_change(
    change: AgentStateChangeType,
    *,
    current: NormalizedAgentObject,
    candidate: NormalizedAgentObject,
) -> str:
    if change == "complete":
        return f"{current.object_type} moved from {candidate.status} to terminal status {current.status}"
    if change == "defer":
        return f"{current.object_type} is deferred in the current meeting"
    if change == "cancel":
        return f"{current.object_type} is cancelled in the current meeting"
    if change == "duplicate":
        return f"{current.object_type} matches history with no material field changes"
    if change == "uncertain":
        return "matched candidate conflicts with current meeting facts"
    return f"{current.object_type} matched historical candidate and has material changes"


def risk_level_for(match: ObjectMatch) -> RiskLevel:
    current = match.current_object
    candidate = match.candidate
    if current.object_type == "Risk":
        level = str(getattr(current.raw, "level", "unknown") or "unknown")
        if level in {"critical", "high", "medium", "low"}:
            return level  # type: ignore[return-value]
    if _closes_high_risk(match) or match.match_type in {"cancel", "uncertain"}:
        return "high"
    if match.match_type in {"update", "complete", "defer"}:
        return "medium"
    return "low"


def description_for(match: ObjectMatch) -> str:
    target = match.candidate.object_id if match.candidate else "new object"
    return f"{match.match_type} proposal for {match.current_object.object_type} {target}"


def proposal_id_for(match: ObjectMatch) -> str:
    candidate_id = match.candidate.object_id if match.candidate else ""
    stable = "|".join(
        [
            AGENT_STATE_TRACKER_SCHEMA_VERSION,
            match.current_object.object_type,
            match.current_object.object_id,
            candidate_id,
            match.current_object.normalized_title,
            match.match_type,
        ]
    )
    return f"proposal-{uuid5(NAMESPACE_URL, stable)}"


def normalize_title(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values)
    text = re.sub(r"[\W_]+", " ", text.lower(), flags=re.UNICODE)
    return " ".join(text.split())


def extract_keywords(*values: Any) -> set[str]:
    text = normalize_title(*values)
    tokens = {token for token in text.split() if len(token) >= 2}
    compact = "".join(text.split())
    if _contains_cjk(compact):
        tokens.update(compact[index : index + 2] for index in range(max(0, len(compact) - 1)))
    return tokens


def keyword_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def coerce_tracked_object(value: TrackedObject | dict[str, Any]) -> TrackedObject | None:
    if isinstance(value, (Requirement, AgentActionItem, Risk)):
        return value
    if not isinstance(value, dict):
        return None
    object_type = value.get("object_type") or value.get("target_object_type") or value.get("type")
    try:
        if object_type == "Requirement" or "requirement_id" in value:
            return Requirement.model_validate(value)
        if object_type == "AgentActionItem" or "action_item_id" in value:
            return AgentActionItem.model_validate(value)
        if object_type == "Risk" or "risk_id" in value:
            return Risk.model_validate(value)
    except Exception:
        return None
    return None


def object_type_for(value: TrackedObject) -> TrackedObjectType:
    if isinstance(value, Requirement):
        return "Requirement"
    if isinstance(value, AgentActionItem):
        return "AgentActionItem"
    return "Risk"


def _object_id(value: TrackedObject) -> str:
    if isinstance(value, Requirement):
        return value.requirement_id
    if isinstance(value, AgentActionItem):
        return value.action_item_id
    return value.risk_id


def _object_title(value: TrackedObject) -> str:
    return str(getattr(value, "title", "") or "")


def _object_project_id(value: TrackedObject, *, default_project_id: str) -> str:
    direct = getattr(value, "project_id", None)
    if direct:
        return str(direct)
    for evidence in getattr(value, "evidence", []) or []:
        project_id = evidence.metadata.get("project_id") if isinstance(evidence.metadata, dict) else None
        if project_id:
            return str(project_id)
    return default_project_id


def _objects_from_meeting_history(history: list[dict[str, Any]]) -> list[TrackedObject]:
    objects: list[TrackedObject] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        for key in ("requirements", "action_items", "risks"):
            values = item.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                coerced = coerce_tracked_object(value)
                if coerced is not None:
                    objects.append(coerced)
    return objects


def _object_dump(value: TrackedObject) -> dict[str, Any]:
    return value.model_dump(mode="json")


def _normalize_optional(value: Any) -> str | None:
    text = str(value).strip().lower() if value is not None else ""
    return text or None


def _is_duplicate_cluster(scored: list[dict[str, Any]]) -> bool:
    return len([item for item in scored if float(item["score"]) >= 0.8]) >= 2


def _closes_high_risk(match: ObjectMatch) -> bool:
    candidate = match.candidate
    if not candidate or candidate.object_type != "Risk":
        return False
    old_level = str(getattr(candidate.raw, "level", "unknown") or "unknown")
    return old_level in {"high", "critical"} and match.match_type == "complete"


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


__all__ = [
    "AGENT_STATE_TRACKER_SCHEMA_VERSION",
    "CrossMeetingStateResult",
    "CrossMeetingStateTracker",
    "HistoricalObjectReader",
    "NormalizedAgentObject",
    "ObjectMatch",
    "TrackedObject",
    "TrackedObjectType",
    "build_action_proposal",
    "determine_state_change",
    "match_current_object",
    "normalize_agent_object",
    "normalize_title",
    "validate_action_proposals",
]
