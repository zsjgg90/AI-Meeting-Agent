from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_TRACE_EVENTS_FILE = "03_semantic_events_validated.json"
_MIN_CONFIDENCE = 0.7
_OPEN_ISSUE_INTENT = "open_issue"
_REJECTED_INTENTS = {"task_assignment", "commitment", "requirement", "risk_warning", "proposal", "decision", "rejection"}

_UNRESOLVED_MARKERS = (
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
    "等待第三方",
    "依赖外部",
    "还没百分百确定",
    "还没通",
    "闭环还是跑不了",
    "第三方",
    "sdk",
    "文档有差异",
)
_MEETING_CONTROL_MARKERS = (
    "还有遗漏吗",
    "还有问题吗",
    "还有补充吗",
    "还有意见吗",
    "大家有没有问题",
)
_ACTION_MARKERS = (
    "修复",
    "回归",
    "输出",
    "提交",
    "完成",
    "更新",
    "同步",
    "跟进",
    "排查",
    "处理",
    "验证",
    "测试",
    "对接",
    "补充",
    "整理",
    "推进",
)
_ACTION_OWNER_MARKERS = (
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
_ACTION_DEADLINE_MARKERS = (
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
_RISK_MARKERS = (
    "风险",
    "可能延期",
    "可能影响",
    "可能导致",
    "压缩测试",
    "会压缩",
    "如果",
)
_PROPOSAL_MARKERS = (
    "建议",
    "可以考虑",
    "要不",
    "是否",
    "要不要",
    "能不能",
    "能否",
)
_RESOLVED_MARKERS = (
    "已解决",
    "已经解决",
    "解决了",
    "已确认",
    "已经确认",
    "确定了",
    "定了",
    "可以了",
    "没有问题",
    "无问题",
    "闭环完成",
)


@dataclass(frozen=True)
class UnresolvedCandidate:
    issue: str
    source_text: str
    source_segment_id: str | None = None
    source_event_ids: tuple[str, ...] = ()
    topic_id: str | None = None
    confidence: float = 0.0
    recall_reason: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue": self.issue,
            "source_text": self.source_text,
            "source_segment_id": self.source_segment_id,
            "source_event_ids": list(self.source_event_ids),
            "topic_id": self.topic_id,
            "confidence": self.confidence,
            "recall_reason": list(self.recall_reason),
        }


def extract_unresolved_candidates_from_trace(trace_dir: str | Path) -> list[UnresolvedCandidate]:
    trace_path = Path(trace_dir)
    payload = _read_json(trace_path / _TRACE_EVENTS_FILE)
    if not payload:
        return []
    return extract_unresolved_candidates_from_event_trace(payload)


def extract_unresolved_candidates_from_event_trace(payload: dict[str, Any]) -> list[UnresolvedCandidate]:
    candidates = [_candidate_from_trace_item(item) for item in _payload_items(payload)]
    return _dedupe_candidates([candidate for candidate in candidates if candidate is not None])


def _candidate_from_trace_item(item: dict[str, Any]) -> UnresolvedCandidate | None:
    event = item.get("event") if isinstance(item.get("event"), dict) else item
    if not isinstance(event, dict):
        return None

    intent = _field("primary_intent", item, event).lower()
    source_text = _field("source_text", item, event)
    normalized_text = _field("normalized_text", event, item)
    text = normalized_text or source_text
    if not text:
        return None

    lower_text = _normalize(text)
    confidence = _confidence(item, event)
    if confidence < _MIN_CONFIDENCE:
        return None

    if _is_rejected_surface(intent, lower_text):
        return None

    marker_reason = _marker_reason(lower_text)
    if intent == _OPEN_ISSUE_INTENT:
        reason = ("open_issue_intent", *marker_reason)
    elif marker_reason:
        reason = marker_reason
    else:
        return None

    event_id = _field("event_id", item, event)
    return UnresolvedCandidate(
        issue=text,
        source_text=source_text or text,
        source_segment_id=_field("segment_id", item, event) or None,
        source_event_ids=(event_id,) if event_id else (),
        topic_id=_field("topic_id", item, event) or None,
        confidence=confidence,
        recall_reason=reason,
    )


def _is_rejected_surface(intent: str, lower_text: str) -> bool:
    if intent in _REJECTED_INTENTS:
        return True
    if _has_marker(lower_text, _MEETING_CONTROL_MARKERS):
        return True
    if _has_marker(lower_text, _RESOLVED_MARKERS):
        return True
    if _is_action_like(lower_text):
        return True
    if _is_risk_like(lower_text):
        return True
    if _is_proposal_like(lower_text):
        return True
    return False


def _marker_reason(lower_text: str) -> tuple[str, ...]:
    matched = [marker for marker in _UNRESOLVED_MARKERS if _has_marker(lower_text, (marker,))]
    if matched:
        return ("unresolved_marker",)
    return ()


def _is_action_like(lower_text: str) -> bool:
    has_owner = _has_marker(lower_text, _ACTION_OWNER_MARKERS)
    has_deadline = _has_marker(lower_text, _ACTION_DEADLINE_MARKERS)
    has_action = _has_marker(lower_text, _ACTION_MARKERS)
    return has_owner and has_deadline and has_action


def _is_risk_like(lower_text: str) -> bool:
    if _has_marker(lower_text, ("签名验证不通过", "原因未知", "还没确认", "还没百分百确定", "第三方", "sdk")):
        return False
    return _has_marker(lower_text, _RISK_MARKERS)


def _is_proposal_like(lower_text: str) -> bool:
    if "为什么" in lower_text and _has_marker(lower_text, ("失败", "不通过", "原因")):
        return False
    return _has_marker(lower_text, _PROPOSAL_MARKERS)


def _dedupe_candidates(candidates: list[UnresolvedCandidate]) -> list[UnresolvedCandidate]:
    selected: dict[str, UnresolvedCandidate] = {}
    for candidate in candidates:
        key = candidate.source_segment_id or _normalize(candidate.source_text)
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
    "UnresolvedCandidate",
    "extract_unresolved_candidates_from_event_trace",
    "extract_unresolved_candidates_from_trace",
]
