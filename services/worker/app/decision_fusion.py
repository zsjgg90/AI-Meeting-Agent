from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.decision_ranking import RankedDecisionCandidate
from app.meeting_analysis_postprocessor import normalize_text, similarity
from app.meeting_analysis_schema import KeyConclusion, MeetingAnalysisSchema


MAX_SEMANTIC_DECISIONS = 4
MIN_OBJECT_OVERLAP = 0.72

ALLOWED_DECISION_TYPES = {"confirmed", "rejection", "scope_change"}
CONFIRMATION_MARKERS = (
    "decided",
    "decision",
    "confirmed",
    "approved",
    "agreed",
    "final",
    "finalize",
    "locked",
    "go with",
    "will use",
)
REJECTION_MARKERS = (
    "reject",
    "rejected",
    "not approve",
    "won't do",
    "will not do",
    "decided not to",
)
SCOPE_MARKERS = (
    "scope change",
    "out of scope",
    "de-scope",
    "descope",
    "scope freeze",
    "freeze scope",
    "next phase",
    "postpone",
    "defer",
    "cancel",
    "not in v1",
    "for v2",
)
PROPOSAL_MARKERS = (
    "suggest",
    "proposal",
    "propose",
    "recommend",
    "consider",
    "maybe",
    "could",
)
QUESTION_MARKERS = (
    "?",
    "should we",
    "can we",
    "whether",
    "do we",
)
ACTION_ONLY_MARKERS = (
    "need to",
    "will update",
    "will fix",
    "follow up",
    "submit",
    "send",
)
OBJECT_STOP_TERMS = (
    *CONFIRMATION_MARKERS,
    *REJECTION_MARKERS,
    *SCOPE_MARKERS,
    "we",
    "the",
    "a",
    "an",
    "to",
    "for",
    "is",
    "are",
    "be",
    "this",
    "that",
    "request",
    "plan",
)


@dataclass(frozen=True)
class _FusionCandidate:
    conclusion: KeyConclusion
    score: float
    decision_object: str
    decision_type: str
    polarity: str
    source_index: int


def fuse_key_conclusions_with_decisions(
    analysis: MeetingAnalysisSchema,
    semantic_decision_candidates: Iterable[RankedDecisionCandidate | dict[str, Any]] | None,
    *,
    max_semantic_decisions: int = MAX_SEMANTIC_DECISIONS,
) -> MeetingAnalysisSchema:
    result = analysis.model_copy(deep=True)
    if not semantic_decision_candidates or max_semantic_decisions <= 0:
        return result

    merged = list(result.key_conclusions)
    ranked_candidates = _rank_candidates(semantic_decision_candidates)
    appended = 0
    for candidate in ranked_candidates:
        if appended >= max_semantic_decisions:
            break
        if _duplicates_existing(candidate, merged):
            continue
        merged.append(candidate.conclusion)
        appended += 1

    result.key_conclusions = merged
    return result


def _rank_candidates(
    semantic_decision_candidates: Iterable[RankedDecisionCandidate | dict[str, Any]],
) -> list[_FusionCandidate]:
    selected: list[_FusionCandidate] = []
    for index, raw_candidate in enumerate(semantic_decision_candidates):
        candidate = _candidate_to_fusion_candidate(raw_candidate, index)
        if candidate is None:
            continue

        duplicate_index = next(
            (
                existing_index
                for existing_index, existing in enumerate(selected)
                if _same_semantic_decision(candidate, existing)
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
    raw_candidate: RankedDecisionCandidate | dict[str, Any],
    source_index: int,
) -> _FusionCandidate | None:
    if isinstance(raw_candidate, RankedDecisionCandidate):
        candidate = raw_candidate.candidate
        conclusion = _text(candidate.conclusion)
        source_text = _text(candidate.source_text or conclusion)
        decision_type = _text(candidate.decision_type or "confirmed")
        polarity = _text(raw_candidate.polarity or _polarity(decision_type, conclusion, source_text))
        decision_object = _text(raw_candidate.decision_object or _decision_object(conclusion))
        score = _float(raw_candidate.score, candidate.confidence)
    elif isinstance(raw_candidate, dict):
        conclusion = _text(raw_candidate.get("conclusion") or raw_candidate.get("decision"))
        source_text = _text(raw_candidate.get("source_text") or raw_candidate.get("source") or conclusion)
        decision_type = _text(raw_candidate.get("decision_type") or raw_candidate.get("type") or "confirmed")
        polarity = _text(raw_candidate.get("polarity") or _polarity(decision_type, conclusion, source_text))
        decision_object = _text(raw_candidate.get("decision_object") or _decision_object(conclusion))
        score = _float(raw_candidate.get("score"), raw_candidate.get("confidence"), 0.7)
    else:
        return None

    if not conclusion or not source_text:
        return None
    if decision_type not in ALLOWED_DECISION_TYPES:
        return None
    if _is_rejected_surface(decision_type, conclusion, source_text):
        return None

    return _FusionCandidate(
        conclusion=KeyConclusion(
            conclusion=conclusion,
            source_text=source_text,
            confidence=max(0.0, min(1.0, score)),
        ),
        score=score,
        decision_object=decision_object,
        decision_type=decision_type,
        polarity=polarity,
        source_index=source_index,
    )


def _duplicates_existing(candidate: _FusionCandidate, existing_items: Iterable[KeyConclusion]) -> bool:
    for existing in existing_items:
        if _same_conclusion_text(candidate.conclusion.conclusion, existing.conclusion):
            return True

        existing_type = _legacy_decision_type(existing)
        existing_polarity = _polarity(existing_type, existing.conclusion, existing.source_text)
        existing_object = _decision_object(existing.conclusion)
        if (
            candidate.decision_type == existing_type
            and candidate.polarity == existing_polarity
            and _same_decision_object(candidate.decision_object, existing_object)
        ):
            return True
    return False


def _same_semantic_decision(left: _FusionCandidate, right: _FusionCandidate) -> bool:
    return (
        left.decision_type == right.decision_type
        and left.polarity == right.polarity
        and _same_decision_object(left.decision_object, right.decision_object)
    )


def _same_decision_object(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return _overlap(left, right) >= MIN_OBJECT_OVERLAP


def _same_conclusion_text(left: str, right: str) -> bool:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm


def _legacy_decision_type(item: KeyConclusion) -> str:
    combined = f"{item.conclusion} {item.source_text}"
    if _contains_any(combined, SCOPE_MARKERS):
        return "scope_change"
    if _contains_any(combined, REJECTION_MARKERS):
        return "rejection"
    return "confirmed"


def _is_rejected_surface(decision_type: str, conclusion: str, source_text: str) -> bool:
    combined = f"{conclusion} {source_text}"
    if _contains_any(combined, QUESTION_MARKERS):
        return True
    if decision_type == "confirmed" and _contains_any(combined, PROPOSAL_MARKERS):
        return True
    if decision_type == "confirmed" and _contains_any(combined, ACTION_ONLY_MARKERS):
        return True
    return False


def _decision_object(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    tokens = _tokens(normalized)
    stop_tokens = {token for term in OBJECT_STOP_TERMS for token in _tokens(term)}
    object_tokens = {token for token in tokens if token not in stop_tokens}
    if not object_tokens:
        return normalized.strip()
    return "|".join(sorted(object_tokens)[:10])


def _polarity(decision_type: str, conclusion: str, source_text: str) -> str:
    combined = f"{conclusion} {source_text}"
    if decision_type == "rejection" or _contains_any(combined, REJECTION_MARKERS):
        return "negative"
    if decision_type == "scope_change":
        return "scope_change"
    return "positive"


def _tokens(value: object) -> set[str]:
    text = str(value or "").strip().lower()
    return set(re.findall(r"[a-z0-9][a-z0-9_+-]*", text))


def _overlap(a: object, b: object) -> float:
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _contains_any(text: object, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").strip().lower()
    return any(term in lowered for term in terms)


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
    "MAX_SEMANTIC_DECISIONS",
    "fuse_key_conclusions_with_decisions",
]
