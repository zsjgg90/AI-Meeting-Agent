from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_TRACE_EVENTS_FILE = "03_semantic_events_validated.json"
_MIN_CONFIDENCE = 0.7
_DECISION_INTENT = "decision"
_REJECTION_INTENT = "rejection"
_CONFIRMED_STATUSES = {"confirmed", "completed"}
_REJECTION_STATUSES = {"confirmed", "completed", "rejected"}
_ACTION_INTENTS = {"task_assignment", "commitment", "requirement"}
_RISK_INTENTS = {"risk_warning"}
_REJECTED_DIRECT_INTENTS = {"proposal", "question"}

_DECISION_MARKERS = (
    "decided",
    "decision",
    "approved",
    "confirmed",
    "agreed",
    "finalize",
    "locked",
    "go with",
    "will use",
    "确定",
    "确认",
    "决定",
    "原则",
)
_REJECTION_MARKERS = (
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
_SCOPE_MARKERS = (
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
_PROPOSAL_MARKERS = (
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
_QUESTION_MARKERS = (
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
_ACTION_MARKERS = (
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
_RISK_MARKERS = (
    "risk",
    "if ",
    "may ",
    "might ",
    "could impact",
)
_POLICY_CONSTRAINT_MARKERS = (
    "低置信度不能强制绑定",
    "不能强制绑定真人名字",
    "不能强制绑定",
    "不得强绑",
)
_MEETING_CONTROL_MARKERS = (
    "先说功能问题",
    "ui后面统一看",
    "ui 后面统一看",
    "先别争这个",
)
_TECHNICAL_ACTION_MARKERS = (
    "取消旧请求",
    "request id",
    "debounce",
)
_GENERIC_SCOPE_ONLY_MARKERS = (
    "以后放v2.6",
    "以后放 v2.6",
)
_CONFIRMATION_ONLY_MARKERS = (
    "确认",
    "对",
    "好",
    "可以",
    "行",
    "嗯",
)
_FUTURE_DECISION_MARKERS = (
    "再决定",
    "到时候决定",
    "看情况决定",
)


@dataclass(frozen=True)
class DecisionCandidate:
    conclusion: str
    source_text: str
    source_segment_id: str | None = None
    source_event_ids: tuple[str, ...] = ()
    topic_id: str | None = None
    decision_type: str = "confirmed"
    confidence: float = 0.0
    recall_reason: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion": self.conclusion,
            "source_text": self.source_text,
            "source_segment_id": self.source_segment_id,
            "source_event_ids": list(self.source_event_ids),
            "topic_id": self.topic_id,
            "decision_type": self.decision_type,
            "confidence": self.confidence,
            "recall_reason": list(self.recall_reason),
        }


def extract_decision_candidates_from_trace(trace_dir: str | Path) -> list[DecisionCandidate]:
    trace_path = Path(trace_dir)
    payload = _read_json(trace_path / _TRACE_EVENTS_FILE)
    if not payload:
        return []
    return extract_decision_candidates_from_event_trace(payload)


def extract_decision_candidates_from_event_trace(payload: dict[str, Any]) -> list[DecisionCandidate]:
    candidates: list[DecisionCandidate] = []
    items = _payload_items(payload)
    for index, item in enumerate(items):
        previous_item = items[index - 1] if index > 0 else None
        next_item = items[index + 1] if index + 1 < len(items) else None
        candidate = _candidate_from_trace_item(item, previous_item, next_item)
        if candidate is not None:
            candidates.append(candidate)
    return _dedupe_candidates(candidates)


def _candidate_from_trace_item(
    item: dict[str, Any],
    previous_item: dict[str, Any] | None = None,
    next_item: dict[str, Any] | None = None,
) -> DecisionCandidate | None:
    event = item.get("event") if isinstance(item.get("event"), dict) else item
    if not isinstance(event, dict):
        return None

    intent = _field("primary_intent", item, event).lower()
    status = _status(item, event)
    source_text = _field("source_text", item, event)
    normalized_text = _field("normalized_text", event, item)
    text = normalized_text or source_text
    if not text:
        return None

    lower_text = _normalize(text)
    confidence = _confidence(item, event)
    if confidence < _MIN_CONFIDENCE:
        return None
    if _is_rejected_surface(intent, status, lower_text):
        return None

    previous_text = _item_text(previous_item)
    next_text = _item_text(next_item)
    decision_type, reason = _decision_type(intent, status, lower_text, previous_text, next_text)
    if decision_type is None:
        return None

    event_id = _field("event_id", item, event)
    conclusion = _defer_decision_conclusion(text) or text
    candidate_source_text = _defer_decision_source_text(text) or source_text or text
    return DecisionCandidate(
        conclusion=conclusion,
        source_text=candidate_source_text,
        source_segment_id=_field("segment_id", item, event) or None,
        source_event_ids=(event_id,) if event_id else (),
        topic_id=_field("topic_id", item, event) or None,
        decision_type=decision_type,
        confidence=confidence,
        recall_reason=reason,
    )


def _decision_type(
    intent: str,
    status: str,
    lower_text: str,
    previous_text: str = "",
    next_text: str = "",
) -> tuple[str | None, tuple[str, ...]]:
    strong_signal = _has_strong_decision_signal(lower_text)
    context_reason = ("neighbor_confirmation",) if _has_neighbor_confirmation(previous_text, next_text) else ()

    if _has_marker(lower_text, _SCOPE_MARKERS):
        return "scope_change", ("scope_marker", *context_reason)

    if _has_marker(lower_text, _POLICY_CONSTRAINT_MARKERS):
        return "confirmed", ("policy_constraint_marker", *context_reason)

    if _has_marker(lower_text, _REJECTION_MARKERS):
        return "rejection", ("rejection_marker", *context_reason)

    if intent == _DECISION_INTENT and status in _CONFIRMED_STATUSES:
        if not strong_signal:
            return None, ()
        return "confirmed", ("confirmed_decision_intent", *context_reason)

    if intent == _REJECTION_INTENT and status in _REJECTION_STATUSES:
        if not strong_signal:
            return None, ()
        return "rejection", ("rejection_intent", *context_reason)

    if status not in _REJECTION_STATUSES:
        return None, ()
    if _has_marker(lower_text, _DECISION_MARKERS) and _has_marker(lower_text, _SCOPE_MARKERS):
        return "scope_change", ("decision_marker", "scope_marker", *context_reason)
    return None, ()


def _is_rejected_surface(intent: str, status: str, lower_text: str) -> bool:
    if intent in _REJECTED_DIRECT_INTENTS:
        return True
    if intent in _ACTION_INTENTS:
        return True
    if _has_marker(lower_text, _MEETING_CONTROL_MARKERS):
        return True
    if _has_marker(lower_text, _TECHNICAL_ACTION_MARKERS):
        return True
    if _is_generic_scope_only(lower_text):
        return True
    if _has_marker(lower_text, _QUESTION_MARKERS):
        return True
    has_strong_signal = _has_strong_decision_signal(lower_text)
    if intent in _RISK_INTENTS and not has_strong_signal:
        return True
    if _has_marker(lower_text, _PROPOSAL_MARKERS) and not has_strong_signal:
        return True
    if _has_marker(lower_text, _ACTION_MARKERS) and not has_strong_signal:
        return True
    if _has_marker(lower_text, _FUTURE_DECISION_MARKERS) and not has_strong_signal:
        return True
    if _looks_like_risk_condition(lower_text) and not has_strong_signal:
        return True
    return False


def _looks_like_risk_condition(lower_text: str) -> bool:
    return _has_marker(lower_text, _RISK_MARKERS) and not _has_marker(
        lower_text,
        _DECISION_MARKERS + _REJECTION_MARKERS + _SCOPE_MARKERS + _POLICY_CONSTRAINT_MARKERS,
    )


def _has_strong_decision_signal(lower_text: str) -> bool:
    return _has_marker(
        lower_text,
        _SCOPE_MARKERS + _REJECTION_MARKERS + _POLICY_CONSTRAINT_MARKERS + _DECISION_MARKERS,
    )


def _defer_decision_conclusion(text: str) -> str | None:
    normalized = _normalize(text)
    if "标题" in normalized and ("先放" in normalized or "暂缓" in normalized):
        return "标题优化先放一下"
    if "性能优化" in normalized and (
        "先不要急" in normalized or "等版本稳定" in normalized or "以后再看" in normalized
    ):
        return "性能优化等版本稳定以后再看"
    return None


def _defer_decision_source_text(text: str) -> str | None:
    clauses = [clause.strip() for clause in re.split(r"[。.!！?？]\s*", str(text or "")) if clause.strip()]
    normalized = _normalize(text)
    if "标题" in normalized and ("先放" in normalized or "暂缓" in normalized):
        return next((clause for clause in clauses if "标题" in clause and ("先放" in clause or "暂缓" in clause)), None)
    if "性能优化" in normalized and (
        "先不要急" in normalized or "等版本稳定" in normalized or "以后再看" in normalized
    ):
        selected = [
            clause
            for clause in clauses
            if "性能优化" in clause or "版本稳定" in clause or "以后再看" in clause
        ]
        return "。 ".join(selected) if selected else None
    return None


def _has_neighbor_confirmation(previous_text: str, next_text: str) -> bool:
    return _is_confirmation_only(previous_text) or _is_confirmation_only(next_text)


def _is_confirmation_only(text: str) -> bool:
    normalized = _normalize(text).strip("。.!！?？")
    compact = normalized.replace(" ", "")
    return compact in _CONFIRMATION_ONLY_MARKERS


def _is_generic_scope_only(lower_text: str) -> bool:
    normalized = lower_text.strip("。.!！?？")
    compact = normalized.replace(" ", "")
    return compact in {marker.replace(" ", "") for marker in _GENERIC_SCOPE_ONLY_MARKERS}


def _dedupe_candidates(candidates: list[DecisionCandidate]) -> list[DecisionCandidate]:
    selected: dict[tuple[str, str], DecisionCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.source_segment_id or _normalize(candidate.source_text),
            _normalize(candidate.conclusion),
        )
        existing = selected.get(key)
        if existing is None or candidate.confidence > existing.confidence:
            selected[key] = candidate
    return list(selected.values())


def _payload_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _field(name: str, *sources: dict[str, Any]) -> str:
    for source in sources:
        value = source.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _item_text(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    event = item.get("event") if isinstance(item.get("event"), dict) else item
    return _normalize(_field("normalized_text", event, item) or _field("source_text", item, event))


def _status(item: dict[str, Any], event: dict[str, Any]) -> str:
    attributes = event.get("attributes")
    if isinstance(attributes, dict):
        value = attributes.get("status")
        if value is not None:
            return str(value).strip().lower()
    return _field("status", item, event).lower()


def _confidence(item: dict[str, Any], event: dict[str, Any]) -> float:
    for source in (event, item):
        confidence = source.get("confidence")
        if isinstance(confidence, dict):
            value = confidence.get("overall")
        else:
            value = confidence
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _has_marker(lower_text: str, markers: tuple[str, ...]) -> bool:
    compact_text = lower_text.replace(" ", "")
    return any(_normalize(marker) in lower_text or _normalize(marker).replace(" ", "") in compact_text for marker in markers)


__all__ = [
    "DecisionCandidate",
    "extract_decision_candidates_from_event_trace",
    "extract_decision_candidates_from_trace",
]
