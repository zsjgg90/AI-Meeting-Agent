from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

from app.meeting_analysis_schema import (
    KeyConclusion,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAnalysisSchema,
    RiskAndFocus,
    UnresolvedIssue,
)


DIMENSION_FIELDS = [
    "meeting_agenda",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
]


def normalize_text(text: object) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = re.sub(r"\d+(\.\d+)?\s*-\s*\d+(\.\d+)?", "", value)
    value = re.sub(r"\s+", "", value)
    return value.lower()


def similarity(a: object, b: object) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def source_is_continuous(source_text: object, transcript: str) -> bool:
    source = str(source_text or "")
    if not source or "..." in source or "……" in source or "鈥︹€?" in source:
        return False
    return normalize_text(source) in normalize_text(transcript)


def transcript_position(text: object, transcript: str) -> int:
    needle = normalize_text(text)
    haystack = normalize_text(transcript)
    if not needle:
        return 10**12
    pos = haystack.find(needle)
    if pos >= 0:
        return pos
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", str(text or ""))
    for token in tokens:
        pos = haystack.find(normalize_text(token))
        if pos >= 0:
            return pos
    return 10**12


def claim_text(field: str, item: object) -> str:
    if field == "meeting_agenda" and isinstance(item, MeetingAgendaItem):
        return item.item
    if field == "key_conclusions" and isinstance(item, KeyConclusion):
        return item.conclusion
    if field == "action_items" and isinstance(item, MeetingActionItem):
        return item.task
    if field == "unresolved_issues" and isinstance(item, UnresolvedIssue):
        return item.issue
    if field == "risks_and_focus" and isinstance(item, RiskAndFocus):
        return item.risk
    return ""


def audit_summary(audit: list[dict[str, Any]]) -> dict[str, Any]:
    by_action = {"keep": 0, "remove": 0, "modify": 0}
    by_field: dict[str, dict[str, int]] = {}
    for event in audit:
        action = str(event.get("action") or "")
        field = str(event.get("field") or "")
        if action in by_action:
            by_action[action] += 1
        field_counts = by_field.setdefault(field, {"keep": 0, "remove": 0, "modify": 0})
        if action in field_counts:
            field_counts[action] += 1
    return {
        "event_count": len(audit),
        "keep_count": by_action["keep"],
        "remove_count": by_action["remove"],
        "modify_count": by_action["modify"],
        "by_field": by_field,
    }


class MeetingAnalysisPostProcessor:
    """
    Deterministic boundary pass after schema normalization.

    This pass may only filter, deduplicate, sort, clear fields, and enforce
    dimension boundaries. It never creates new meeting facts or rewrites item
    text.
    """

    decision_terms = (
        "确认",
        "决定",
        "同意",
        "最终",
        "锁定",
        "禁止",
        "必须",
        "敲定",
        "达成",
        "纭",
        "鍐冲畾",
        "鍚屾剰",
        "鏈€缁",
        "閿佸畾",
        "绂佹",
        "蹇呴』",
        "鏁插畾",
        "杈炬垚",
    )
    strong_decision_terms = (
        "确认",
        "决定",
        "同意",
        "最终",
        "锁定",
        "敲定",
        "达成",
        "纭",
        "鍐冲畾",
        "鍚屾剰",
        "鏈€缁",
        "閿佸畾",
        "鏁插畾",
        "杈炬垚",
    )
    proposal_terms = (
        "建议",
        "考虑",
        "倾向",
        "可以尝试",
        "希望",
        "是否",
        "能不能",
        "疑问",
        "寤鸿",
        "鎴戝缓璁",
        "鍙互鑰冭檻",
        "鏄惁",
        "鐤戦棶",
        "鑳戒笉鑳",
        "甯屾湜",
    )
    action_terms = (
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
        "review",
        "submit",
        "update",
        "follow",
    )
    flow_terms = ("大家好", "下午好", "会议控制", "会议开始", "会议结束", "首先请", "开场", "流程")
    resolved_terms = ("已解决", "已经解决", "已明确", "没有问题", "无问题", "可以落地", "确认可以")
    risk_terms = ("风险", "可能", "影响", "延期", "阻塞", "异常", "故障", "超时", "返工", "压力")
    priority_terms = ("高优先级", "中优先级", "低优先级", "优先处理", "优先跟进", "紧急", "high", "medium", "low")

    def __init__(self) -> None:
        self.last_audit: list[dict[str, Any]] = []

    def process(self, analysis: MeetingAnalysisSchema, transcript: str) -> MeetingAnalysisSchema:
        self.last_audit = []
        result = analysis.model_copy(deep=True)

        result.meeting_agenda = self._process_agenda(result.meeting_agenda, transcript)
        result.key_conclusions = self._process_conclusions(result.key_conclusions, transcript)
        result.action_items = self._process_actions(result.action_items, transcript)
        result.unresolved_issues = self._process_issues(result.unresolved_issues, transcript)
        result.risks_and_focus = self._process_risks(result.risks_and_focus, transcript)
        self._remove_cross_dimension_duplicates(result)

        for order, item in enumerate(result.meeting_agenda, start=1):
            if item.order != order:
                before = item.model_dump()
                item.order = order
                self._audit("meeting_agenda", "modify", "renumber_after_filter_sort", before, item.model_dump())

        return result

    def audit_summary(self) -> dict[str, Any]:
        return audit_summary(self.last_audit)

    def _audit(
        self,
        field: str,
        action: str,
        reason: str,
        before: object = None,
        after: object = None,
    ) -> None:
        event: dict[str, Any] = {"field": field, "action": action, "reason": reason}
        if before is not None:
            event["before"] = deepcopy(before)
        if after is not None:
            event["after"] = deepcopy(after)
        self.last_audit.append(event)

    def _keep(self, field: str, item: object, reason: str = "kept") -> None:
        dump = item.model_dump() if hasattr(item, "model_dump") else item
        self._audit(field, "keep", reason, dump)

    def _process_agenda(self, items: list[MeetingAgendaItem], transcript: str) -> list[MeetingAgendaItem]:
        kept: list[MeetingAgendaItem] = []
        for item in sorted(items, key=lambda entry: (transcript_position(entry.item, transcript), entry.order)):
            text = item.item
            if any(term in text for term in self.flow_terms):
                self._audit("meeting_agenda", "remove", "flow_talk_or_greeting", item.model_dump())
                continue
            if any(similarity(text, existing.item) >= 0.82 for existing in kept):
                self._audit("meeting_agenda", "remove", "duplicate_topic", item.model_dump())
                continue
            kept.append(item)
            self._keep("meeting_agenda", item)

        if len(kept) > 6:
            for item in kept[6:]:
                self._audit("meeting_agenda", "remove", "agenda_limit_6", item.model_dump())
            kept = kept[:6]
        return kept

    def _process_conclusions(self, items: list[KeyConclusion], transcript: str) -> list[KeyConclusion]:
        kept: list[KeyConclusion] = []
        for item in items:
            combined = f"{item.conclusion}{item.source_text}"
            has_decision = any(term in combined for term in self.decision_terms)
            has_proposal = any(term in combined for term in self.proposal_terms)
            has_strong_decision = any(term in item.source_text for term in self.strong_decision_terms)
            if not source_is_continuous(item.source_text, transcript):
                self._audit("key_conclusions", "remove", "invalid_or_ellipsized_source_text", item.model_dump())
                continue
            if not has_decision or (has_proposal and not has_strong_decision):
                self._audit("key_conclusions", "remove", "not_confirmed_decision", item.model_dump())
                continue
            if any(similarity(item.conclusion, existing.conclusion) >= 0.86 for existing in kept):
                self._audit("key_conclusions", "remove", "duplicate_conclusion", item.model_dump())
                continue
            kept.append(item)
            self._keep("key_conclusions", item)
        return sorted(kept, key=lambda item: transcript_position(item.source_text, transcript))

    def _process_actions(self, items: list[MeetingActionItem], transcript: str) -> list[MeetingActionItem]:
        kept: list[MeetingActionItem] = []
        for item in items:
            if not source_is_continuous(item.source_text, transcript):
                self._audit("action_items", "remove", "invalid_or_ellipsized_source_text", item.model_dump())
                continue
            if not any(term in f"{item.task}{item.source_text}".lower() for term in self.action_terms):
                self._audit("action_items", "remove", "no_explicit_action_verb", item.model_dump())
                continue
            before = item.model_dump()
            changed = False
            source_norm = normalize_text(item.source_text)
            if item.owner_name and normalize_text(item.owner_name) not in source_norm:
                item.owner_name = None
                changed = True
            if item.deadline and normalize_text(item.deadline) not in source_norm:
                item.deadline = None
                changed = True
            if (
                item.priority
                and item.priority != "medium"
                and not any(normalize_text(term) in source_norm for term in self.priority_terms)
            ):
                item.priority = "medium"
                changed = True
            if changed:
                self._audit("action_items", "modify", "unsupported_action_metadata_cleared", before, item.model_dump())
            if any(similarity(item.task, existing.task) >= 0.86 for existing in kept):
                self._audit("action_items", "remove", "duplicate_action", item.model_dump())
                continue
            kept.append(item)
            self._keep("action_items", item)
        return sorted(
            kept,
            key=lambda item: (
                item.deadline is None,
                normalize_text(item.deadline or ""),
                transcript_position(item.source_text, transcript),
            ),
        )

    def _process_issues(self, items: list[UnresolvedIssue], transcript: str) -> list[UnresolvedIssue]:
        kept: list[UnresolvedIssue] = []
        for item in items:
            combined = f"{item.issue}{item.reason}{item.blocker}{item.source_text}"
            if not source_is_continuous(item.source_text, transcript):
                self._audit("unresolved_issues", "remove", "invalid_or_ellipsized_source_text", item.model_dump())
                continue
            if any(term in combined for term in self.resolved_terms):
                self._audit("unresolved_issues", "remove", "resolved_issue", item.model_dump())
                continue
            if any(similarity(item.issue, existing.issue) >= 0.86 for existing in kept):
                self._audit("unresolved_issues", "remove", "duplicate_issue", item.model_dump())
                continue
            kept.append(item)
            self._keep("unresolved_issues", item)
        return sorted(kept, key=lambda item: transcript_position(item.source_text, transcript))

    def _process_risks(self, items: list[RiskAndFocus], transcript: str) -> list[RiskAndFocus]:
        kept: list[RiskAndFocus] = []
        for item in items:
            combined = f"{item.risk}{item.impact}{item.focus_area}{item.mitigation}{item.source_text}"
            if not source_is_continuous(item.source_text, transcript):
                self._audit("risks_and_focus", "remove", "invalid_or_ellipsized_source_text", item.model_dump())
                continue
            if not any(term in combined for term in self.risk_terms):
                self._audit("risks_and_focus", "remove", "no_risk_evidence", item.model_dump())
                continue
            if any(similarity(item.risk, existing.risk) >= 0.86 for existing in kept):
                self._audit("risks_and_focus", "remove", "duplicate_risk", item.model_dump())
                continue
            kept.append(item)
            self._keep("risks_and_focus", item)
        return sorted(kept, key=lambda item: transcript_position(item.source_text, transcript))

    def _remove_cross_dimension_duplicates(self, result: MeetingAnalysisSchema) -> None:
        accepted: list[tuple[str, object, str]] = []
        priority_order = [
            ("action_items", result.action_items),
            ("key_conclusions", result.key_conclusions),
            ("unresolved_issues", result.unresolved_issues),
            ("risks_and_focus", result.risks_and_focus),
        ]

        for field, items in priority_order:
            filtered = []
            for item in items:
                text = claim_text(field, item)
                duplicate_of = next(
                    (
                        accepted_field
                        for accepted_field, _accepted_item, accepted_text in accepted
                        if normalize_text(text) == normalize_text(accepted_text)
                    ),
                    None,
                )
                if duplicate_of:
                    self._audit(field, "remove", f"cross_dimension_exact_duplicate_of_{duplicate_of}", item.model_dump())
                    continue
                accepted.append((field, item, text))
                filtered.append(item)
            setattr(result, field, filtered)
