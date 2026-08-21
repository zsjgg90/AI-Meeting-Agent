from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.meeting_analysis_postprocessor import normalize_text, similarity
from app.meeting_analysis_schema import MeetingAnalysisSchema, UnresolvedIssue
from app.unresolved_ranking import RankedUnresolvedCandidate


MAX_SEMANTIC_UNRESOLVED = 3
MIN_ISSUE_SIMILARITY = 0.86
MIN_OBJECT_OVERLAP = 0.66


@dataclass(frozen=True)
class _FusionCandidate:
    issue: UnresolvedIssue
    score: float
    issue_object: str
    source_index: int


def fuse_unresolved_issues(
    analysis: MeetingAnalysisSchema,
    semantic_unresolved_candidates: Iterable[RankedUnresolvedCandidate | dict[str, Any]] | None,
    *,
    max_semantic_unresolved: int = MAX_SEMANTIC_UNRESOLVED,
) -> MeetingAnalysisSchema:
    result = analysis.model_copy(deep=True)
    if not semantic_unresolved_candidates or max_semantic_unresolved <= 0:
        return result

    merged = list(result.unresolved_issues)
    ranked_candidates = _rank_candidates(semantic_unresolved_candidates)
    appended = 0
    for candidate in ranked_candidates:
        if appended >= max_semantic_unresolved:
            break
        if _duplicates_existing(candidate, merged):
            continue
        merged.append(candidate.issue)
        appended += 1

    result.unresolved_issues = merged
    return result


def _rank_candidates(
    semantic_unresolved_candidates: Iterable[RankedUnresolvedCandidate | dict[str, Any]],
) -> list[_FusionCandidate]:
    selected: list[_FusionCandidate] = []
    for index, raw_candidate in enumerate(semantic_unresolved_candidates):
        candidate = _candidate_to_fusion_candidate(raw_candidate, index)
        if candidate is None:
            continue

        duplicate_index = next(
            (
                existing_index
                for existing_index, existing in enumerate(selected)
                if _same_semantic_issue(candidate, existing)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(candidate)
            continue

        existing = selected[duplicate_index]
        if (candidate.score, -candidate.source_index) > (existing.score, -existing.source_index):
            selected[duplicate_index] = candidate

    selected.sort(key=lambda item: (-item.score, item.source_index))
    return selected


def _candidate_to_fusion_candidate(
    raw_candidate: RankedUnresolvedCandidate | dict[str, Any],
    source_index: int,
) -> _FusionCandidate | None:
    if isinstance(raw_candidate, RankedUnresolvedCandidate):
        candidate = raw_candidate.candidate
        issue = _text(candidate.issue)
        source_text = _text(candidate.source_text)
        score = _float(raw_candidate.score, candidate.confidence, 0.0)
        issue_object = _text(raw_candidate.issue_object)
    elif isinstance(raw_candidate, dict):
        issue = _text(raw_candidate.get("issue"))
        source_text = _text(raw_candidate.get("source_text") or raw_candidate.get("source"))
        score = _float(raw_candidate.get("score"), raw_candidate.get("confidence"), 0.0)
        issue_object = _text(raw_candidate.get("issue_object"))
    else:
        return None

    if not issue or not source_text:
        return None
    if _is_rejected_surface(raw_candidate):
        return None

    return _FusionCandidate(
        issue=UnresolvedIssue(
            issue=issue,
            source_text=source_text,
            confidence=max(0.0, min(1.0, score or 0.7)),
        ),
        score=score,
        issue_object=issue_object or _issue_object(issue),
        source_index=source_index,
    )


def _duplicates_existing(candidate: _FusionCandidate, existing_items: Iterable[UnresolvedIssue]) -> bool:
    for existing in existing_items:
        if _same_issue_text(candidate.issue.issue, existing.issue):
            return True
        if _same_source_text(candidate.issue.source_text, existing.source_text):
            return True
        existing_object = _issue_object(existing.issue)
        if _same_issue_object(candidate.issue_object, existing_object):
            return True
    return False


def _same_semantic_issue(left: _FusionCandidate, right: _FusionCandidate) -> bool:
    if _same_issue_text(left.issue.issue, right.issue.issue):
        return True
    if _same_source_text(left.issue.source_text, right.issue.source_text):
        return True
    return _same_issue_object(left.issue_object, right.issue_object)


def _same_issue_text(left: str, right: str) -> bool:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    return similarity(left, right) >= MIN_ISSUE_SIMILARITY


def _same_source_text(left: str, right: str) -> bool:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def _same_issue_object(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return _overlap(left, right) >= MIN_OBJECT_OVERLAP


def _is_rejected_surface(raw_candidate: RankedUnresolvedCandidate | dict[str, Any]) -> bool:
    if isinstance(raw_candidate, RankedUnresolvedCandidate):
        reasons = set(raw_candidate.candidate.recall_reason)
        combined = f"{raw_candidate.candidate.issue} {raw_candidate.candidate.source_text}"
    elif isinstance(raw_candidate, dict):
        reasons_value = raw_candidate.get("recall_reason") or raw_candidate.get("merged_recall_reasons") or []
        reasons = {str(reason) for reason in reasons_value} if isinstance(reasons_value, list) else set()
        combined = f"{raw_candidate.get('issue') or ''} {raw_candidate.get('source_text') or ''}"
    else:
        return True

    rejected_reasons = {"action_like", "risk_like", "meeting_question", "proposal_like"}
    if reasons & rejected_reasons:
        return True
    return _looks_like_action(combined) or _looks_like_risk(combined) or _looks_like_meeting_question(combined)


def _issue_object(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    compact = normalized.replace(" ", "")
    if any(term in compact for term in ("payment", "signature", "callback", "sdk")):
        return "payment_external_dependency"
    tokens = _tokens(normalized)
    if not tokens:
        return normalized
    return "|".join(sorted(tokens)[:10])


def _looks_like_action(text: object) -> bool:
    normalized = str(text or "").lower()
    return any(term in normalized for term in ("todo", "action", "follow up", "fix", "submit", "update")) and any(
        term in normalized for term in ("owner", "by tomorrow", "next week", "deadline")
    )


def _looks_like_risk(text: object) -> bool:
    normalized = str(text or "").lower()
    return any(term in normalized for term in ("risk", "may delay", "could impact", "if "))


def _looks_like_meeting_question(text: object) -> bool:
    normalized = str(text or "").lower().strip()
    return "any other questions" in normalized or "anything else" in normalized


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9_+\-.]{1,}", str(value or "").lower()))


def _overlap(a: object, b: object) -> float:
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _text(value: object) -> str:
    return str(value or "").strip()


def _float(*values: object) -> float:
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


__all__ = [
    "MAX_SEMANTIC_UNRESOLVED",
    "fuse_unresolved_issues",
]
