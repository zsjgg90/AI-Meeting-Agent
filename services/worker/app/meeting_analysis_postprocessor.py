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
    summary_context_terms = (
        "最后把结论过一下",
        "结论过一下",
        "最后结论",
        "总结一下",
    )
    ordinal_conclusion_terms = (
        "第一",
        "第二",
        "第三",
        "第四",
        "第五",
        "第六",
        "第七",
        "第八",
    )
    confirmation_terms = (
        "确认",
        "对",
        "可以",
        "同意",
        "没问题",
    )
    negative_decision_terms = (
        "不增加",
        "不做",
        "不上",
        "不纳入",
        "不支持",
        "暂不上",
        "不考虑",
        "不能",
        "取消",
        "延期",
    )
    scope_version_terms = (
        "范围",
        "需求",
        "能力",
        "版本",
        "本版",
        "这版",
        "当前版本",
        "本版本",
        "下个版本",
        "下版本",
        "下期",
    )
    defer_decision_terms = (
        "先放",
        "先放一下",
        "暂缓",
        "先不要急",
        "等版本稳定",
        "版本稳定以后再看",
        "以后再看",
        "先作为优化项",
        "不要影响版本",
    )
    defer_decision_object_terms = (
        "标题",
        "优化",
        "性能",
        "版本",
        "六维输出",
    )
    priority_decision_terms = (
        "最高优先级",
        "优先级最高",
        "优先解决",
        "最高优先级任务",
    )
    priority_decision_object_terms = (
        "AI分析",
        "稳定性",
    )
    scope_version_positive_patterns = (
        r"v\s*\d+(?:\.\d+)*.*(?:范围冻结|冻结范围|原则上冻结范围)",
        r"(?:范围冻结|冻结范围|原则上冻结范围).*v\s*\d+(?:\.\d+)*",
        r"新需求都?放(?:到)?v\s*\d+(?:\.\d+)*",
        r"(?:这版|本版|本版本|当前版本)不上(?:实际)?能力",
        r"(?:这版|本版|本版本|当前版本)不(?:做|新增|增加|纳入)",
        r"不进入(?:当前版本|本版本|这版|本版|v\s*\d+(?:\.\d+)*)",
        r"不纳入(?:当前版本|本版本|这版|本版|v\s*\d+(?:\.\d+)*)",
        r"延后到(?:下个版本|下版本|下期|v\s*\d+(?:\.\d+)*)",
        r"放(?:到)?(?:下个版本|下版本|下期|v\s*\d+(?:\.\d+)*)",
    )
    unconfirmed_decision_blockers = (
        "如果",
        "可能",
        "要不要",
        "后续再确认",
        "再确认",
        "还没决定",
        "没决定",
        "暂时还没决定",
        "尚未决定",
        "来不及",
    )
    action_like_conclusion_patterns = (
        r"(?:必须|需要).{0,8}(?:修|修复|验证|测试|回归|检查)",
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
    meeting_control_question_terms = (
        "还有遗漏吗",
        "还有问题吗",
        "还有补充吗",
        "还有意见吗",
        "大家有没有问题",
    )
    issue_close_terms = (
        "已确认",
        "确定",
        "定了",
        "就行",
        "可以",
        "不用",
        "不需要",
        "按这个",
        "统一",
        "解决了",
    )
    explicit_action_terms = (
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
    explicit_action_owner_terms = (
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
    explicit_action_deadline_terms = (
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
            has_context_decision = self._has_confirmed_conclusion_context(item.source_text, transcript)
            has_negative_decision = any(term in item.source_text for term in self.negative_decision_terms)
            has_scope_version_decision = self._has_confirmed_scope_version_decision(item.conclusion, item.source_text)
            has_defer_decision = self._has_confirmed_defer_decision(item.conclusion, item.source_text)
            has_priority_decision = self._has_confirmed_priority_decision(item.conclusion, item.source_text)
            if (
                self._has_unconfirmed_decision_blocker(combined)
                or self._is_action_like_conclusion(combined)
            ) and not (has_defer_decision or has_priority_decision):
                self._audit("key_conclusions", "remove", "not_confirmed_decision", item.model_dump())
                continue
            if self._claim_has_unsupported_numeric_detail(item.conclusion, item.source_text):
                self._audit("key_conclusions", "remove", "not_confirmed_decision", item.model_dump())
                continue
            if (
                not has_decision
                and not (has_negative_decision and has_context_decision)
                and not has_scope_version_decision
                and not has_defer_decision
                and not has_priority_decision
            ) or (
                has_proposal
                and not has_strong_decision
                and not has_context_decision
                and not has_scope_version_decision
                and not has_defer_decision
                and not has_priority_decision
            ):
                self._audit("key_conclusions", "remove", "not_confirmed_decision", item.model_dump())
                continue
            if any(similarity(item.conclusion, existing.conclusion) >= 0.86 for existing in kept):
                self._audit("key_conclusions", "remove", "duplicate_conclusion", item.model_dump())
                continue
            kept.append(item)
            self._keep("key_conclusions", item)
        return sorted(kept, key=lambda item: transcript_position(item.source_text, transcript))

    def _has_confirmed_conclusion_context(self, source_text: str, transcript: str) -> bool:
        lines = [line for line in transcript.splitlines() if line.strip()]
        source_norm = normalize_text(source_text)
        if not source_norm:
            return False

        source_start = None
        source_end = None
        for start in range(len(lines)):
            combined = ""
            for end in range(start, min(start + 3, len(lines))):
                combined = f"{combined}{lines[end]}"
                combined_norm = normalize_text(combined)
                if source_norm in combined_norm or combined_norm in source_norm:
                    source_start = start
                    source_end = end
                    break
            if source_start is not None:
                break
        if source_start is None or source_end is None:
            return False

        context_start = max(0, source_start - 3)
        context_end = min(len(lines), source_end + 3)
        before_and_source = "".join(lines[context_start : source_end + 1])
        near_after = "".join(lines[source_end + 1 : context_end])
        near_context = "".join(lines[context_start:context_end])
        in_summary_context = any(term in before_and_source for term in self.summary_context_terms)
        has_ordinal = any(term in lines[source_start] for term in self.ordinal_conclusion_terms)
        has_confirmation = any(term in near_after for term in self.confirmation_terms)
        has_strong_context = any(term in near_context for term in self.strong_decision_terms)
        return (in_summary_context and has_confirmation) or (has_ordinal and (has_confirmation or has_strong_context))

    def _has_confirmed_scope_version_decision(self, conclusion: str, source_text: str) -> bool:
        text = normalize_text(f"{conclusion}{source_text}")
        if (
            not text
            or self._has_unconfirmed_decision_blocker(text)
            or self._is_action_like_conclusion(text)
            or any(normalize_text(term) in text for term in self.proposal_terms)
        ):
            return False
        has_scope_or_version = any(normalize_text(term) in text for term in self.scope_version_terms)
        if not has_scope_or_version and not re.search(r"v\s*\d+(?:\.\d+)*", text, flags=re.IGNORECASE):
            return False
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in self.scope_version_positive_patterns)

    def _has_confirmed_defer_decision(self, conclusion: str, source_text: str) -> bool:
        text = normalize_text(f"{conclusion}{source_text}")
        if not text:
            return False
        has_defer_marker = any(normalize_text(term) in text for term in self.defer_decision_terms)
        has_defer_object = any(normalize_text(term) in text for term in self.defer_decision_object_terms)
        if not has_defer_marker or not has_defer_object:
            return False
        if any(normalize_text(term) in text for term in ("建议", "是否", "能不能", "要不要")):
            return False
        return True

    def _has_confirmed_priority_decision(self, conclusion: str, source_text: str) -> bool:
        text = normalize_text(f"{conclusion}{source_text}")
        if not text:
            return False
        has_priority_marker = any(normalize_text(term) in text for term in self.priority_decision_terms)
        has_priority_object = any(normalize_text(term) in text for term in self.priority_decision_object_terms)
        if not has_priority_marker or not has_priority_object:
            return False
        if any(normalize_text(term) in text for term in ("建议", "是否", "能不能", "要不要")):
            return False
        return True

    def _has_unconfirmed_decision_blocker(self, text: str) -> bool:
        if "?" in text or "？" in text:
            return True
        normalized = normalize_text(text)
        return any(normalize_text(term) in normalized for term in self.unconfirmed_decision_blockers)

    def _is_action_like_conclusion(self, text: str) -> bool:
        normalized = normalize_text(text)
        return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in self.action_like_conclusion_patterns)

    def _claim_has_unsupported_numeric_detail(self, conclusion: str, source_text: str) -> bool:
        conclusion_numbers = set(re.findall(r"\d+(?:[:：]\d+)?", conclusion))
        if not conclusion_numbers:
            return False
        source_norm = normalize_text(source_text)
        return any(normalize_text(number) not in source_norm for number in conclusion_numbers)

    def _is_recording_test_arrangement(self, text: object) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        has_arrangement = "安排" in normalized
        has_recording = "录音" in normalized
        has_test = "测试" in normalized or "压测" in normalized
        if not (has_arrangement and has_recording and has_test):
            return False
        blockers = ("建议", "是否", "能不能", "要不要", "已经", "基本完成", "现在")
        return not any(normalize_text(term) in normalized for term in blockers)

    def _has_supported_action_verb(self, item: MeetingActionItem) -> bool:
        combined = f"{item.task}{item.source_text}".lower()
        return any(term in combined for term in self.action_terms) or self._is_recording_test_arrangement(combined)

    def _find_recording_test_arrangement_source(self, item: MeetingActionItem, transcript: str) -> str | None:
        if not self._is_recording_test_arrangement(f"{item.task}{item.source_text}"):
            return None
        for line in transcript.splitlines():
            if self._is_recording_test_arrangement(line):
                return line.strip()
        return None

    def _process_actions(self, items: list[MeetingActionItem], transcript: str) -> list[MeetingActionItem]:
        kept: list[MeetingActionItem] = []
        for item in items:
            if not source_is_continuous(item.source_text, transcript):
                replacement_source = self._find_recording_test_arrangement_source(item, transcript)
                if not replacement_source:
                    self._audit("action_items", "remove", "invalid_or_ellipsized_source_text", item.model_dump())
                    continue
                before = item.model_dump()
                item.source_text = replacement_source
                self._audit("action_items", "modify", "recording_test_source_repaired_from_transcript", before, item.model_dump())
            if not self._has_supported_action_verb(item):
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
            if self._is_meeting_control_question(combined):
                self._audit("unresolved_issues", "remove", "meeting_control_question", item.model_dump())
                continue
            if self._is_action_like_issue(combined):
                self._audit("unresolved_issues", "remove", "action_like_issue", item.model_dump())
                continue
            if self._issue_resolved_by_nearby_followup(item.source_text, transcript):
                self._audit("unresolved_issues", "remove", "resolved_by_followup", item.model_dump())
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

    def _is_meeting_control_question(self, text: str) -> bool:
        normalized = normalize_text(text)
        return any(normalize_text(term) in normalized for term in self.meeting_control_question_terms)

    def _is_action_like_issue(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        has_owner = any(normalize_text(term) in normalized for term in self.explicit_action_owner_terms)
        has_deadline = any(normalize_text(term) in normalized for term in self.explicit_action_deadline_terms)
        has_action = any(normalize_text(term) in normalized for term in self.explicit_action_terms)
        return has_owner and has_deadline and has_action

    def _issue_resolved_by_nearby_followup(self, source_text: str, transcript: str) -> bool:
        lines = [line for line in transcript.splitlines() if line.strip()]
        source_start, source_end = self._find_source_line_window(source_text, lines)
        if source_start is None or source_end is None:
            return False

        context_start = max(0, source_start - 2)
        context_end = min(len(lines), source_end + 4)
        source_norm = normalize_text("".join(lines[source_start : source_end + 1]))

        for index in range(context_start, context_end):
            if source_start <= index <= source_end:
                continue
            line_norm = normalize_text(lines[index])
            if not line_norm or line_norm in source_norm or source_norm in line_norm:
                continue
            if any(normalize_text(term) in line_norm for term in self.issue_close_terms):
                return True
        return False

    def _find_source_line_window(self, source_text: str, lines: list[str]) -> tuple[int | None, int | None]:
        source_norm = normalize_text(source_text)
        if not source_norm:
            return None, None

        for start in range(len(lines)):
            combined = ""
            for end in range(start, min(start + 3, len(lines))):
                combined = f"{combined}{lines[end]}"
                combined_norm = normalize_text(combined)
                if source_norm in combined_norm or combined_norm in source_norm:
                    return start, end
        return None, None

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
