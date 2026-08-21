from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.decision_candidate_recall import DecisionCandidate


ALLOWED_DECISION_TYPES = {"confirmed", "rejection", "scope_change"}
MIN_DECISION_SCORE = 0.45
MIN_OBJECT_OVERLAP = 0.72
MIN_OBJECT_SIMILARITY = 0.88

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
    "确定",
    "确认",
    "决定",
    "原则",
)
REJECTION_MARKERS = (
    "reject",
    "rejected",
    "not approve",
    "won't do",
    "will not do",
    "decided not to",
    "不上实际能力",
    "不新增",
    "不支持",
    "取消",
    "延后",
    "不能强制绑定",
    "不得强绑",
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
    "冻结范围",
    "范围锁定",
    "这版不做",
    "本版本不做",
    "这版不上",
    "不进v2.5",
    "不进 v2.5",
    "放v2.6",
    "放 v2.6",
    "后续版本再做",
    "先放",
    "先放一下",
    "暂缓",
    "先不要急",
    "等版本稳定",
    "版本稳定以后再看",
    "以后再看",
)
PROPOSAL_MARKERS = (
    "suggest",
    "proposal",
    "propose",
    "recommend",
    "consider",
    "maybe",
    "could",
    "建议",
    "可以考虑",
    "要不",
    "倾向",
    "最好",
    "尝试",
)
QUESTION_MARKERS = (
    "?",
    "？",
    "should we",
    "can we",
    "whether",
    "do we",
    "是不是",
    "是否",
    "要不要",
    "能不能",
    "能否",
    "有没有",
    "怎么",
    "为什么",
)
ACTION_ONLY_MARKERS = (
    "need to",
    "will update",
    "will fix",
    "follow up",
    "submit",
    "send",
    "必须修",
    "要修",
    "我今天查",
    "给结果",
    "修复",
    "跟进",
    "更新",
    "提交",
    "验证",
)
POLICY_CONSTRAINT_MARKERS = (
    "低置信度不能强制绑定",
    "不能强制绑定真人名字",
    "不能强制绑定",
    "不得强绑",
)
MEETING_CONTROL_MARKERS = (
    "先说功能问题",
    "ui后面统一看",
    "ui 后面统一看",
    "先别争这个",
)
TECHNICAL_ACTION_MARKERS = (
    "取消旧请求",
    "request id",
    "debounce",
)
GENERIC_SCOPE_ONLY_MARKERS = (
    "以后放v2.6",
    "以后放 v2.6",
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
class RankedDecisionCandidate:
    candidate: DecisionCandidate
    score: float
    confirmation_score: float
    evidence_score: float
    semantic_decision_score: float
    scope_decision_score: float
    decision_object: str
    polarity: str
    source_index: int = 0

    def to_dict(self) -> dict[str, object]:
        payload = self.candidate.to_dict()
        payload.update(
            {
                "score": self.score,
                "confirmation_score": self.confirmation_score,
                "evidence_score": self.evidence_score,
                "semantic_decision_score": self.semantic_decision_score,
                "scope_decision_score": self.scope_decision_score,
                "decision_object": self.decision_object,
                "polarity": self.polarity,
            }
        )
        return payload


def rank_and_deduplicate_decisions(
    candidates: Iterable[DecisionCandidate],
) -> list[RankedDecisionCandidate]:
    selected: list[RankedDecisionCandidate] = []
    for index, candidate in enumerate(candidates):
        scored = _score_candidate(candidate, index)
        if scored is None or scored.score < MIN_DECISION_SCORE:
            continue

        duplicate_index = next(
            (
                existing_index
                for existing_index, existing in enumerate(selected)
                if _same_decision_key(scored, existing)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(scored)
            continue

        existing = selected[duplicate_index]
        if (scored.score, -scored.source_index) > (existing.score, -existing.source_index):
            selected[duplicate_index] = scored

    selected.sort(key=lambda item: (-item.score, item.source_index))
    return selected


def _score_candidate(candidate: DecisionCandidate, source_index: int) -> RankedDecisionCandidate | None:
    if candidate.decision_type not in ALLOWED_DECISION_TYPES:
        return None

    combined = f"{candidate.conclusion} {candidate.source_text}"
    if _is_rejected_surface(candidate, combined):
        return None

    confirmation_score = _confirmation_score(candidate, combined)
    evidence_score = _evidence_score(candidate)
    semantic_decision_score = _semantic_decision_score(candidate, combined)
    scope_decision_score = _scope_decision_score(candidate, combined)
    score = round(
        confirmation_score * 0.32
        + evidence_score * 0.26
        + semantic_decision_score * 0.30
        + scope_decision_score * 0.12,
        4,
    )

    return RankedDecisionCandidate(
        candidate=candidate,
        score=score,
        confirmation_score=confirmation_score,
        evidence_score=evidence_score,
        semantic_decision_score=semantic_decision_score,
        scope_decision_score=scope_decision_score,
        decision_object=_decision_object(candidate),
        polarity=_polarity(candidate, combined),
        source_index=source_index,
    )


def _confirmation_score(candidate: DecisionCandidate, combined: str) -> float:
    score = 0.0
    if candidate.decision_type == "confirmed":
        score += 0.45
    if candidate.decision_type in {"rejection", "scope_change"}:
        score += 0.35
    if _contains_any(combined, CONFIRMATION_MARKERS + REJECTION_MARKERS):
        score += 0.35
    if any("confirmed" in reason or "decision_marker" in reason for reason in candidate.recall_reason):
        score += 0.15
    score += 0.05 * _bounded_confidence(candidate.confidence)
    return _bounded_score(score)


def _evidence_score(candidate: DecisionCandidate) -> float:
    score = 0.0
    if candidate.source_text:
        score += 0.35
    if candidate.source_event_ids:
        score += 0.25
    if candidate.source_segment_id:
        score += 0.20
    if candidate.topic_id:
        score += 0.10
    if candidate.source_text and _similarity(candidate.conclusion, candidate.source_text) >= 0.45:
        score += 0.10
    return _bounded_score(score)


def _semantic_decision_score(candidate: DecisionCandidate, combined: str) -> float:
    score = 0.25 * _bounded_confidence(candidate.confidence)
    if candidate.decision_type in ALLOWED_DECISION_TYPES:
        score += 0.35
    if _contains_any(combined, CONFIRMATION_MARKERS + REJECTION_MARKERS):
        score += 0.25
    if candidate.recall_reason:
        score += 0.15
    return _bounded_score(score)


def _scope_decision_score(candidate: DecisionCandidate, combined: str) -> float:
    if candidate.decision_type != "scope_change":
        return 0.0
    score = 0.65
    if _contains_any(combined, SCOPE_MARKERS):
        score += 0.25
    if any("scope" in reason for reason in candidate.recall_reason):
        score += 0.10
    return _bounded_score(score)


def _is_rejected_surface(candidate: DecisionCandidate, combined: str) -> bool:
    lower = _normalize(combined)
    if candidate.decision_type not in ALLOWED_DECISION_TYPES:
        return True
    if _contains_any(lower, MEETING_CONTROL_MARKERS):
        return True
    if _contains_any(lower, TECHNICAL_ACTION_MARKERS):
        return True
    if _is_generic_scope_only(lower):
        return True
    if _contains_any(lower, QUESTION_MARKERS):
        return True
    has_strong_signal = _contains_any(
        lower,
        SCOPE_MARKERS + REJECTION_MARKERS + POLICY_CONSTRAINT_MARKERS + CONFIRMATION_MARKERS,
    )
    if candidate.decision_type == "confirmed" and _contains_any(lower, PROPOSAL_MARKERS) and not has_strong_signal:
        return True
    if candidate.decision_type == "confirmed" and _contains_any(lower, ACTION_ONLY_MARKERS) and not has_strong_signal:
        return True
    return False


def _same_decision_key(left: RankedDecisionCandidate, right: RankedDecisionCandidate) -> bool:
    if left.candidate.decision_type != right.candidate.decision_type:
        return False
    if left.polarity != right.polarity:
        return False
    if left.decision_object and left.decision_object == right.decision_object:
        return True
    if _similarity(left.decision_object, right.decision_object) >= MIN_OBJECT_SIMILARITY:
        return True
    return _overlap(left.decision_object, right.decision_object) >= MIN_OBJECT_OVERLAP


def _decision_object(candidate: DecisionCandidate) -> str:
    text = _normalize(candidate.conclusion or candidate.source_text)
    compact = text.replace(" ", "")
    if any(term in compact for term in ("飞书", "邮箱", "短信", "推送")):
        return "push_channels"
    if any(term in compact for term in ("agentmemory", "我的记忆", "完整记忆")):
        return "agent_memory"
    if any(term in compact for term in ("声纹", "低置信度", "真人名字", "强制绑定")):
        return "voiceprint_identity"
    if any(term in compact for term in ("v2.5", "冻结范围", "新需求")):
        return "v25_scope_freeze"
    if "标题" in compact and "优化" in compact:
        return "title_defer"
    if "性能优化" in compact or ("版本稳定" in compact and "优化" in compact):
        return "performance_defer"
    for term in sorted(OBJECT_STOP_TERMS, key=len, reverse=True):
        text = text.replace(_normalize(term), " ")
    tokens = _tokens(text)
    if not tokens:
        return text
    return "|".join(sorted(tokens)[:10])


def _polarity(candidate: DecisionCandidate, combined: str) -> str:
    if candidate.decision_type == "scope_change":
        return "scope_change"
    if candidate.decision_type == "rejection" or _contains_any(combined, REJECTION_MARKERS):
        return "negative"
    return "positive"


def _tokens(value: object) -> set[str]:
    text = _normalize(value)
    return set(re.findall(r"[a-z0-9][a-z0-9_+\-.]{1,}", text))


def _overlap(a: object, b: object) -> float:
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _similarity(a: object, b: object) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _contains_any(text: object, terms: tuple[str, ...]) -> bool:
    lowered = _normalize(text)
    compact = lowered.replace(" ", "")
    return any(_normalize(term) in lowered or _normalize(term).replace(" ", "") in compact for term in terms)


def _is_generic_scope_only(text: object) -> bool:
    normalized = _normalize(text).strip("。.!！?？")
    compact = normalized.replace(" ", "")
    return compact in {term.replace(" ", "") for term in GENERIC_SCOPE_ONLY_MARKERS}


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _normalize(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


__all__ = [
    "RankedDecisionCandidate",
    "rank_and_deduplicate_decisions",
]
