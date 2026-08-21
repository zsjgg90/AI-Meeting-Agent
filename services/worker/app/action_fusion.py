from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.meeting_analysis_postprocessor import normalize_text, similarity
from app.meeting_analysis_schema import MeetingActionItem, MeetingAnalysisSchema


ACTION_TERMS = (
    "补充",
    "提交",
    "完成",
    "更新",
    "同步",
    "跟进",
    "确认",
    "整理",
    "提供",
    "评估",
    "修复",
    "调整",
    "输出",
    "推进",
    "准备",
    "落地",
    "处理",
    "验证",
    "回归",
    "排查",
    "review",
    "submit",
    "update",
    "follow",
    "fix",
)

WEAK_COMMITMENT_TASKS = {
    "我会处理",
    "我来处理",
    "我会跟进",
    "我来跟进",
    "我会看",
    "我来看",
    "我回去看看",
    "后续跟进",
    "继续跟进",
}

MIN_KEYWORD_OVERLAP = 0.6
MIN_TASK_SIMILARITY = 0.86
MIN_SOURCE_OVERLAP = 0.75
MIN_CANDIDATE_SCORE = 0.55

ACTION_FAMILIES: dict[str, tuple[str, ...]] = {
    "progress": ("推进", "跟进", "落地", "闭环", "协调", "follow"),
    "verify": ("验证", "回归", "测试", "稳定性验证", "确认结果", "review"),
    "fix": ("修复", "排查", "处理", "解决", "fix"),
    "sync": ("同步", "对齐", "通知", "更新", "update"),
    "deliver": ("提交", "提供", "输出", "补充", "整理", "准备", "submit"),
    "confirm": ("确认", "明确"),
}

FAMILY_COMPATIBLE_FOR_SAME_OBJECT = {
    frozenset({"progress", "verify"}),
    frozenset({"deliver", "other"}),
}

DISCUSSION_TERMS = (
    "建议",
    "可以考虑",
    "可能",
    "先讨论",
    "再讨论",
    "看是否",
    "要不要",
    "有没有必要",
)

RECAP_TERMS = (
    "最后",
    "结论",
    "行动项",
    "任务",
    "分工",
    "总结",
    "过一下",
    "明确一下",
)

TASK_OBJECT_STOP_TERMS = {
    "推进",
    "跟进",
    "落地",
    "闭环",
    "协调",
    "验证",
    "回归",
    "测试",
    "稳定性",
    "确认",
    "结果",
    "修复",
    "排查",
    "处理",
    "解决",
    "同步",
    "对齐",
    "通知",
    "更新",
    "提交",
    "提供",
    "输出",
    "补充",
    "整理",
    "调整",
    "准备",
    "完成",
    "问题",
    "任务",
}


@dataclass(frozen=True)
class _ScoredAction:
    action: MeetingActionItem
    score: float
    object_key: str
    family: str
    index: int
    source_type: str = "semantic"
    candidate_id: str = ""
    duplicate_group: str = ""
    suppression_reason: str | None = None


def _text(value: object) -> str:
    return str(value or "").strip()


def _tokens(value: object) -> set[str]:
    text = _text(value).lower()
    tokens = set(re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_+\-.]{1,}", text))
    for block in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(block) <= 4:
            tokens.add(block)
        for index in range(len(block) - 1):
            tokens.add(block[index : index + 2])
    return {token for token in tokens if token}


def _overlap(a: object, b: object) -> float:
    left = _tokens(a)
    right = _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _source_overlap(a: object, b: object) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    return _overlap(a, b)


def _contains_any(text: object, terms: Iterable[str]) -> bool:
    lowered = _text(text).lower()
    return any(term.lower() in lowered for term in terms)


def _has_action_term(item: MeetingActionItem) -> bool:
    combined = f"{item.task}{item.source_text}".lower()
    return any(term in combined for term in ACTION_TERMS)


def _is_weak_commitment(item: MeetingActionItem) -> bool:
    task_norm = normalize_text(item.task)
    if task_norm in {normalize_text(task) for task in WEAK_COMMITMENT_TASKS}:
        return True

    first_person_prefix = task_norm.startswith(("我会", "我来", "我负责", "我这边"))
    if first_person_prefix and len(task_norm) <= 6:
        return True

    return False


def _has_discussion_expression(item: MeetingActionItem) -> bool:
    combined = f"{item.task}{item.source_text}"
    return _contains_any(combined, DISCUSSION_TERMS)


def _has_recap_source(item: MeetingActionItem) -> bool:
    return _contains_any(item.source_text, RECAP_TERMS)


def _action_family(item: MeetingActionItem) -> str:
    combined = f"{item.task}{item.source_text}".lower()
    for family, terms in ACTION_FAMILIES.items():
        if any(term.lower() in combined for term in terms):
            return family
    return "other"


def _task_object_key(item: MeetingActionItem) -> str:
    text = normalize_text(item.task)
    for terms in ACTION_FAMILIES.values():
        for term in terms:
            text = text.replace(normalize_text(term), "")
    for term in TASK_OBJECT_STOP_TERMS:
        text = text.replace(normalize_text(term), "")
    tokens = _tokens(text)
    if not tokens:
        return text
    object_tokens = sorted(
        token
        for token in tokens
        if normalize_text(token) not in {normalize_text(term) for term in TASK_OBJECT_STOP_TERMS}
    )
    return "|".join(object_tokens[:6])


def _has_distinct_owner_or_deadline(left: MeetingActionItem, right: MeetingActionItem) -> bool:
    left_owner = normalize_text(left.owner_name or "")
    right_owner = normalize_text(right.owner_name or "")
    if left_owner and right_owner and left_owner != right_owner:
        return True

    left_deadline = normalize_text(left.deadline or "")
    right_deadline = normalize_text(right.deadline or "")
    if left_deadline and right_deadline and left_deadline != right_deadline:
        return True

    return False


def _family_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    return frozenset({left, right}) in FAMILY_COMPATIBLE_FOR_SAME_OBJECT


def _candidate_score(item: MeetingActionItem) -> float:
    score = 0.0
    combined = f"{item.task}{item.source_text}"

    if _contains_any(item.task, ACTION_TERMS):
        score += 0.30
    elif _contains_any(combined, ACTION_TERMS):
        score += 0.22

    if item.source_text:
        if similarity(item.task, item.source_text) >= 0.5 or _overlap(item.task, item.source_text) >= 0.45:
            score += 0.20
        else:
            score += 0.10

    if item.owner_name:
        score += 0.18
    if item.deadline:
        score += 0.12
    if _has_recap_source(item):
        score += 0.12

    score += 0.08 * max(0.0, min(1.0, item.confidence))

    if _is_weak_commitment(item):
        score -= 0.45
    if _has_discussion_expression(item):
        score -= 0.20

    return score


def _candidate_to_action(item: MeetingActionItem | dict[str, Any]) -> MeetingActionItem | None:
    if isinstance(item, MeetingActionItem):
        action = item.model_copy(deep=True)
    elif isinstance(item, dict):
        task = _text(item.get("task") or item.get("item"))
        if not task:
            return None
        priority = _text(item.get("priority") or "medium")
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        status = _text(item.get("status") or "open")
        if status not in {"open", "in_progress", "done"}:
            status = "open"
        action = MeetingActionItem(
            owner_name=_text(item.get("owner_name") or item.get("owner")) or None,
            task=task,
            deadline=_text(item.get("deadline") or item.get("due_date")) or None,
            priority=priority,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            source_text=_text(item.get("source_text") or item.get("source") or task),
            source_segment_id=_text(item.get("source_segment_id")) or None,
            confidence=float(item.get("confidence") or 0.7),
        )
    else:
        return None

    if not _has_action_term(action):
        return None
    if _is_weak_commitment(action):
        return None
    return action


def _is_duplicate(
    candidate: MeetingActionItem,
    existing_items: Iterable[MeetingActionItem],
    *,
    preserve_distinct_metadata: bool = True,
) -> bool:
    candidate_task = normalize_text(candidate.task)
    for existing in existing_items:
        if preserve_distinct_metadata and _has_distinct_owner_or_deadline(candidate, existing):
            continue
        if candidate_task and candidate_task == normalize_text(existing.task):
            return True
        if similarity(candidate.task, existing.task) >= MIN_TASK_SIMILARITY:
            return True
        if _overlap(candidate.task, existing.task) >= MIN_KEYWORD_OVERLAP:
            return True
        if _source_overlap(candidate.source_text, existing.source_text) >= MIN_SOURCE_OVERLAP:
            return True
    return False


def _same_task_cluster(left: _ScoredAction, right: _ScoredAction) -> bool:
    if _has_distinct_owner_or_deadline(left.action, right.action):
        return False
    if normalize_text(left.action.task) == normalize_text(right.action.task):
        return True
    if similarity(left.action.task, right.action.task) >= MIN_TASK_SIMILARITY:
        return True
    if _source_overlap(left.action.source_text, right.action.source_text) >= MIN_SOURCE_OVERLAP:
        return True
    if left.object_key and left.object_key == right.object_key and _family_compatible(left.family, right.family):
        return True
    return False


def _same_duplicate_group(left: _ScoredAction, right: _ScoredAction) -> bool:
    if left.source_type == right.source_type:
        return _same_task_cluster(left, right)
    if normalize_text(left.action.task) == normalize_text(right.action.task):
        return True
    if similarity(left.action.task, right.action.task) >= MIN_TASK_SIMILARITY:
        return True
    if _overlap(left.action.task, right.action.task) >= MIN_KEYWORD_OVERLAP:
        return True
    if _source_overlap(left.action.source_text, right.action.source_text) >= MIN_SOURCE_OVERLAP:
        return True
    if left.object_key and left.object_key == right.object_key:
        return True
    return False


def _evidence_quality(item: MeetingActionItem) -> float:
    score = 0.0
    if item.source_text:
        score += 0.25
        if similarity(item.task, item.source_text) >= 0.5 or _overlap(item.task, item.source_text) >= 0.45:
            score += 0.25
        else:
            score += 0.10
    if item.source_segment_id:
        score += 0.12
    if item.owner_name:
        score += 0.10
    if item.deadline:
        score += 0.10
    if len(normalize_text(item.task)) >= 10:
        score += 0.08
    return score


def _legacy_priority_score(item: MeetingActionItem) -> float:
    return {"high": 0.3, "medium": 0.2, "low": 0.1}.get(item.priority, 0.0)


def _survivor_key(item: _ScoredAction) -> tuple[float, float, float, float, int]:
    semantic_confidence = item.action.confidence if item.source_type == "semantic" else 0.0
    legacy_priority = _legacy_priority_score(item.action) if item.source_type == "legacy" else 0.0
    return (
        _evidence_quality(item.action),
        semantic_confidence,
        legacy_priority,
        item.score,
        -item.index,
    )


def _audit_event(item: _ScoredAction, final_survivor: bool) -> dict[str, Any]:
    return {
        "candidate_id": item.candidate_id,
        "source_type": item.source_type,
        "duplicate_group": item.duplicate_group,
        "task": item.action.task,
        "suppression_reason": item.suppression_reason,
        "final_survivor": final_survivor,
    }


def mark_action_fusion_final_survivors(audit: list[dict[str, Any]], final_actions: Iterable[MeetingActionItem | dict[str, Any]]) -> None:
    final_tasks = [
        normalize_text(item.task if isinstance(item, MeetingActionItem) else item.get("task"))
        for item in final_actions
    ]
    for event in audit:
        task = normalize_text(event.get("task"))
        event["final_survivor"] = bool(task and task in final_tasks)


def _rank_and_deduplicate_candidates(
    semantic_candidates: Iterable[MeetingActionItem | dict[str, Any]],
    legacy_items: Iterable[MeetingActionItem],
    audit: list[dict[str, Any]] | None = None,
) -> list[MeetingActionItem]:
    selected: list[_ScoredAction] = []
    for index, raw_candidate in enumerate(semantic_candidates):
        candidate = _candidate_to_action(raw_candidate)
        if candidate is None:
            continue
        score = _candidate_score(candidate)
        if score < MIN_CANDIDATE_SCORE:
            continue

        scored = _ScoredAction(
            action=candidate,
            score=score,
            object_key=_task_object_key(candidate),
            family=_action_family(candidate),
            index=index,
            source_type="semantic",
            candidate_id=f"semantic:{index}",
        )
        duplicate_index = next(
            (existing_index for existing_index, existing in enumerate(selected) if _same_task_cluster(scored, existing)),
            None,
        )
        if duplicate_index is None:
            selected.append(scored)
            continue

        existing = selected[duplicate_index]
        if (scored.score, -scored.index) > (existing.score, -existing.index):
            selected[duplicate_index] = scored

    grouped: list[list[_ScoredAction]] = []
    for index, legacy in enumerate(legacy_items):
        scored = _ScoredAction(
            action=legacy.model_copy(deep=True),
            score=_candidate_score(legacy),
            object_key=_task_object_key(legacy),
            family=_action_family(legacy),
            index=index,
            source_type="legacy",
            candidate_id=f"legacy:{index}",
        )
        duplicate_index = next(
            (group_index for group_index, group in enumerate(grouped) if any(_same_duplicate_group(scored, existing) for existing in group)),
            None,
        )
        if duplicate_index is None:
            grouped.append([scored])
        else:
            grouped[duplicate_index].append(scored)

    for scored in sorted(selected, key=lambda item: (-item.score, item.index)):
        duplicate_index = next(
            (group_index for group_index, group in enumerate(grouped) if any(_same_duplicate_group(scored, existing) for existing in group)),
            None,
        )
        if duplicate_index is None:
            grouped.append([scored])
        else:
            grouped[duplicate_index].append(scored)

    ordered: list[_ScoredAction] = []
    for group_index, group in enumerate(grouped, start=1):
        duplicate_group = f"action-group-{group_index}"
        ranked_group = sorted(group, key=_survivor_key, reverse=True)
        for member_index, item in enumerate(ranked_group):
            reason = None if member_index == 0 else "duplicate_group_non_survivor"
            item = _ScoredAction(
                action=item.action,
                score=item.score,
                object_key=item.object_key,
                family=item.family,
                index=item.index,
                source_type=item.source_type,
                candidate_id=item.candidate_id,
                duplicate_group=duplicate_group,
                suppression_reason=reason,
            )
            ordered.append(item)
            if audit is not None:
                audit.append(_audit_event(item, final_survivor=member_index == 0))

    ordered.sort(
        key=lambda item: (
            item.duplicate_group,
            -_survivor_key(item)[0],
            -_survivor_key(item)[1],
            -_survivor_key(item)[2],
            -item.score,
            item.index,
        )
    )
    return [item.action for item in ordered]


def fuse_action_items(
    analysis: MeetingAnalysisSchema,
    semantic_candidates: Iterable[MeetingActionItem | dict[str, Any]] | None,
    audit: list[dict[str, Any]] | None = None,
) -> MeetingAnalysisSchema:
    result = analysis.model_copy(deep=True)
    if not semantic_candidates:
        if audit is not None:
            for index, item in enumerate(result.action_items):
                audit.append(
                    {
                        "candidate_id": f"legacy:{index}",
                        "source_type": "legacy",
                        "duplicate_group": f"action-group-{index + 1}",
                        "task": item.task,
                        "suppression_reason": None,
                        "final_survivor": True,
                    }
                )
        return result

    result.action_items = _rank_and_deduplicate_candidates(semantic_candidates, result.action_items, audit)
    return result


__all__ = ["fuse_action_items", "mark_action_fusion_final_survivors"]
