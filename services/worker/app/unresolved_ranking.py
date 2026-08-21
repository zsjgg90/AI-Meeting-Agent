from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.unresolved_candidate_recall import UnresolvedCandidate


MIN_UNRESOLVED_SCORE = 0.45
MIN_OBJECT_OVERLAP = 0.66
MIN_OBJECT_SIMILARITY = 0.86

UNRESOLVED_MARKERS = (
    "还没确认",
    "还没有确认",
    "未确认",
    "未确定",
    "没确定",
    "没有解决",
    "没解决",
    "仍然存在",
    "还没定位",
    "还没有定位",
    "原因未知",
    "还没百分百确定",
    "还没通",
    "闭环还是跑不了",
)
EXTERNAL_DEPENDENCY_MARKERS = (
    "第三方",
    "外部",
    "sdk",
    "文档有差异",
    "等待",
    "依赖",
)
STATE_BLOCKED_MARKERS = (
    "阻塞",
    "不回",
    "跑不了",
    "不通过",
    "未解决",
    "没解决",
    "没通",
)
ACTION_MARKERS = (
    "修复",
    "回归",
    "输出",
    "提交",
    "完成",
    "更新",
    "同步",
    "跟进",
    "处理",
    "验证",
    "测试",
    "补充",
    "整理",
    "推进",
)
ACTION_OWNER_MARKERS = (
    "后端",
    "前端",
    "测试",
    "产品",
    "研发",
    "设计",
    "运营",
    "算法",
    "客户端",
    "服务端",
    "qa",
    "ai",
)
ACTION_DEADLINE_MARKERS = (
    "今天",
    "明天",
    "上午",
    "下午",
    "今晚",
    "本周",
    "这周",
    "下周",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
    "之前",
    "月底",
)
RISK_MARKERS = (
    "风险",
    "可能延期",
    "可能影响",
    "可能导致",
    "压缩测试",
    "会压缩",
    "如果",
)
MEETING_QUESTION_MARKERS = (
    "还有遗漏吗",
    "还有问题吗",
    "还有补充吗",
    "还有意见吗",
    "大家有没有问题",
)
PROPOSAL_MARKERS = (
    "建议",
    "可以考虑",
    "要不",
    "是否",
    "要不要",
    "能不能",
    "能否",
)
WEAK_CONTEXT_PREFIXES = (
    "对",
    "嗯",
    "好",
    "可以",
    "行",
)
OBJECT_STOP_TERMS = (
    *UNRESOLVED_MARKERS,
    *EXTERNAL_DEPENDENCY_MARKERS,
    *STATE_BLOCKED_MARKERS,
    "现在",
    "目前",
    "原因",
    "问题",
    "这个",
    "那个",
    "一次",
    "一直",
)


@dataclass(frozen=True)
class RankedUnresolvedCandidate:
    candidate: UnresolvedCandidate
    score: float
    marker_score: float
    dependency_score: float
    evidence_score: float
    state_score: float
    issue_object: str
    source_index: int = 0
    merged_source_texts: tuple[str, ...] = ()
    merged_source_event_ids: tuple[str, ...] = ()
    merged_recall_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = self.candidate.to_dict()
        payload.update(
            {
                "score": self.score,
                "marker_score": self.marker_score,
                "dependency_score": self.dependency_score,
                "evidence_score": self.evidence_score,
                "state_score": self.state_score,
                "issue_object": self.issue_object,
                "merged_source_texts": list(self.merged_source_texts),
                "merged_source_event_ids": list(self.merged_source_event_ids),
                "merged_recall_reasons": list(self.merged_recall_reasons),
            }
        )
        return payload


def rank_and_deduplicate_unresolved(
    candidates: Iterable[UnresolvedCandidate],
) -> list[RankedUnresolvedCandidate]:
    clusters: list[list[RankedUnresolvedCandidate]] = []
    for index, candidate in enumerate(candidates):
        scored = _score_candidate(candidate, index)
        if scored is None or scored.score < MIN_UNRESOLVED_SCORE:
            continue

        cluster_index = next(
            (
                existing_index
                for existing_index, cluster in enumerate(clusters)
                if any(_same_issue_object(scored, existing) for existing in cluster)
            ),
            None,
        )
        if cluster_index is None:
            clusters.append([scored])
        else:
            clusters[cluster_index].append(scored)

    merged = [_merge_cluster(cluster) for cluster in clusters]
    merged.sort(key=lambda item: (-item.score, item.source_index))
    return merged


def _score_candidate(candidate: UnresolvedCandidate, source_index: int) -> RankedUnresolvedCandidate | None:
    combined = f"{candidate.issue} {candidate.source_text}"
    if _is_rejected_surface(combined):
        return None

    marker_score = _marker_score(combined, candidate)
    dependency_score = _dependency_score(combined)
    evidence_score = _evidence_score(candidate)
    state_score = _state_score(combined)
    score = round(
        marker_score * 0.34
        + dependency_score * 0.22
        + evidence_score * 0.24
        + state_score * 0.20,
        4,
    )

    return RankedUnresolvedCandidate(
        candidate=candidate,
        score=score,
        marker_score=marker_score,
        dependency_score=dependency_score,
        evidence_score=evidence_score,
        state_score=state_score,
        issue_object=_issue_object(candidate),
        source_index=source_index,
        merged_source_texts=(candidate.source_text,) if candidate.source_text else (),
        merged_source_event_ids=candidate.source_event_ids,
        merged_recall_reasons=candidate.recall_reason,
    )


def _is_rejected_surface(text: object) -> bool:
    normalized = _normalize(text)
    if _contains_any(normalized, MEETING_QUESTION_MARKERS):
        return True
    if _is_action_like(normalized):
        return True
    if _is_risk_like(normalized):
        return True
    if _is_proposal_like(normalized):
        return True
    if _is_weak_context_fragment(normalized):
        return True
    return False


def _marker_score(text: object, candidate: UnresolvedCandidate) -> float:
    score = 0.0
    if _contains_any(text, UNRESOLVED_MARKERS):
        score += 0.65
    if "open_issue_intent" in candidate.recall_reason:
        score += 0.20
    if "unresolved_marker" in candidate.recall_reason:
        score += 0.15
    return _bounded_score(score)


def _dependency_score(text: object) -> float:
    score = 0.0
    if _contains_any(text, EXTERNAL_DEPENDENCY_MARKERS):
        score += 0.75
    if _contains_any(text, ("第三方 sdk", "第三方sdk", "外部依赖", "等待第三方")):
        score += 0.25
    if _contains_any(text, ("支付", "签名验证", "回调", "闭环")):
        score += 0.55
    return _bounded_score(score)


def _evidence_score(candidate: UnresolvedCandidate) -> float:
    score = 0.0
    if candidate.source_text:
        score += 0.35
    if candidate.source_event_ids:
        score += 0.25
    if candidate.source_segment_id:
        score += 0.20
    if candidate.topic_id:
        score += 0.05
    score += 0.15 * _bounded_confidence(candidate.confidence)
    return _bounded_score(score)


def _state_score(text: object) -> float:
    score = 0.0
    if _contains_any(text, STATE_BLOCKED_MARKERS):
        score += 0.70
    if _contains_any(text, ("原因", "闭环", "验证不通过")):
        score += 0.20
    if "?" in str(text) or "？" in str(text):
        score += 0.10
    return _bounded_score(score)


def _same_issue_object(left: RankedUnresolvedCandidate, right: RankedUnresolvedCandidate) -> bool:
    if left.issue_object and left.issue_object == right.issue_object:
        return True
    if _payment_dependency_object(left.issue_object) and _payment_dependency_object(right.issue_object):
        return True
    if _state_only_object(left.issue_object) and _payment_dependency_object(right.issue_object):
        return True
    if _payment_dependency_object(left.issue_object) and _state_only_object(right.issue_object):
        return True
    if _similarity(left.issue_object, right.issue_object) >= MIN_OBJECT_SIMILARITY:
        return True
    return _overlap(left.issue_object, right.issue_object) >= MIN_OBJECT_OVERLAP


def _merge_cluster(cluster: list[RankedUnresolvedCandidate]) -> RankedUnresolvedCandidate:
    ordered = sorted(cluster, key=lambda item: (-item.score, item.source_index))
    best = ordered[0]
    source_texts = _unique(text for item in ordered for text in item.merged_source_texts)
    event_ids = _unique(event_id for item in ordered for event_id in item.merged_source_event_ids)
    reasons = _unique(reason for item in ordered for reason in item.merged_recall_reasons)
    max_score = max(item.score for item in ordered)
    cluster_bonus = min(0.12, 0.03 * (len(ordered) - 1))
    return RankedUnresolvedCandidate(
        candidate=best.candidate,
        score=_bounded_score(max_score + cluster_bonus),
        marker_score=best.marker_score,
        dependency_score=best.dependency_score,
        evidence_score=best.evidence_score,
        state_score=best.state_score,
        issue_object=best.issue_object,
        source_index=min(item.source_index for item in ordered),
        merged_source_texts=tuple(source_texts),
        merged_source_event_ids=tuple(event_ids),
        merged_recall_reasons=tuple(reasons),
    )


def _issue_object(candidate: UnresolvedCandidate) -> str:
    text = _normalize(f"{candidate.issue} {candidate.source_text}")
    compact = text.replace(" ", "")
    if any(term in compact for term in ("支付", "签名验证", "第三方sdk", "第三方", "闭环")):
        return "payment_external_dependency"
    if any(term in compact for term in ("没解决", "未解决", "跑不了", "没通")):
        return "unresolved_state_only"
    if "小屏" in compact or "设备适配" in compact:
        return "device_adaptation"
    for term in sorted(OBJECT_STOP_TERMS, key=len, reverse=True):
        text = text.replace(_normalize(term), " ")
    tokens = _tokens(text)
    if not tokens:
        return text
    return "|".join(sorted(tokens)[:10])


def _payment_dependency_object(value: str) -> bool:
    return value == "payment_external_dependency"


def _state_only_object(value: str) -> bool:
    return value == "unresolved_state_only"


def _is_action_like(text: str) -> bool:
    return _contains_any(text, ACTION_OWNER_MARKERS) and _contains_any(text, ACTION_DEADLINE_MARKERS) and _contains_any(text, ACTION_MARKERS)


def _is_risk_like(text: str) -> bool:
    if _contains_any(text, ("签名验证不通过", "原因未知", "还没确认", "还没百分百确定", "第三方", "sdk", "没解决")):
        return False
    return _contains_any(text, RISK_MARKERS)


def _is_proposal_like(text: str) -> bool:
    if "为什么" in text and _contains_any(text, ("失败", "不通过", "原因")):
        return False
    return _contains_any(text, PROPOSAL_MARKERS)


def _is_weak_context_fragment(text: str) -> bool:
    compact = text.replace(" ", "").strip("。.!！?？")
    if not any(compact.startswith(prefix) for prefix in WEAK_CONTEXT_PREFIXES):
        return False
    return not _contains_any(compact, ("支付", "签名", "第三方", "sdk", "闭环", "声纹", "设备", "接口", "原因"))


def _tokens(value: object) -> set[str]:
    text = _normalize(value)
    tokens = set(re.findall(r"[a-z0-9][a-z0-9_+\-.]{1,}", text))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


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


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _normalize(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


__all__ = [
    "RankedUnresolvedCandidate",
    "rank_and_deduplicate_unresolved",
]
