from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.semantic_event_schema import SemanticEvent


# ---------------------------------------------------------------------------
# 意图信号配置
# ---------------------------------------------------------------------------

PROPOSAL_PATTERNS = [
    "建议",
    "可以考虑",
    "是否可以",
    "是不是可以",
    "要不要",
    "我觉得",
    "最好",
    "不如",
    "可以先",
    "建议先",
]

CONFIRMATION_PATTERNS = [
    "同意",
    "确认",
    "决定",
    "采纳",
    "就这么定",
    "按此执行",
    "正式采用",
    "统一按照",
    "最终决定",
    "敲定",
    "确定方案",
    "确认采用",
    "决定执行",
    "达成一致",
]

NON_FINAL_DECISION_PATTERNS = [
    "再确定",
    "后续确定",
    "继续评估",
    "暂未确定",
    "暂不确认",
    "暂不决定",
    "初步怀疑",
    "还没有最终确认",
    "不能直接确认",
    "待进一步评估",
]

REJECTION_PATTERNS = [
    "否决",
    "驳回",
    "砍掉",
    "取消",
    "停止",
    "不做",
    "不上",
    "不再推进",
    "暂不执行",
    "暂缓",
    "移到下期",
    "延后至下期",
]

# 这些表达本身通常已经具有“已形成否决动作”的含义。
# 但如果同时存在“建议”等提议信号，仍然应判为 proposal。
CONFIRMED_REJECTION_PATTERNS = [
    "决定不做",
    "确定不做",
    "本期不做",
    "本期不上",
    "正式取消",
    "确认取消",
    "停止推进",
    "不再推进",
    "砍掉",
    "否决",
    "驳回",
]

COMMITMENT_PATTERNS = [
    "我会",
    "我负责",
    "我来负责",
    "我来跟进",
    "我来处理",
    "我今天",
    "我明天",
    "我后续",
    "我会后",
    "我这边会",
    "由我",
]

ASSIGNMENT_PATTERNS = [
    "由测试负责",
    "由前端负责",
    "由后端负责",
    "由产品负责",
    "由运营负责",
    "由设计负责",
    "由项目负责人负责",
    "交给",
    "安排给",
    "负责完成",
    "负责跟进",
    "负责处理",
    "需要完成",
    "需要补充",
    "需要更新",
    "需要提交",
    "需要同步",
    "需要排查",
    "需要验证",
    "需要评估",
    "需要跟进",
    "后续安排",
    "下一步完成",
    "需在",
]

REQUIREMENT_PATTERNS = [
    "需要",
    "必须",
    "应当",
    "要求",
    "务必",
    "需在",
    "禁止",
    "不得",
    "严格执行",
]

STRONG_AGENDA_SIGNALS = [
    "会议议题",
    "会议流程",
    "会议目标",
    "今天主要讨论",
    "今天重点讨论",
    "今天主要确认",
    "本次主要讨论",
    "本次重点讨论",
    "本次重点确认",
    "本次会议核心",
    "本次会议主要",
    "会议控制在",
    "核心目标是",
    "主要分为",
]

PURE_FLOW_EXACT_TEXTS = {
    "好",
    "好的",
    "可以",
    "没问题",
    "没有问题",
    "无问题",
    "无异议",
    "大家好",
    "各位好",
    "各位大家好",
    "会议结束",
    "本次会议结束",
    "今天的会议结束",
    "收到",
    "明白",
}

PURE_FLOW_PATTERNS = [
    re.compile(r"^大家还有(其他)?问题吗[？?。]?$"),
    re.compile(r"^大家有没有(其他)?问题[？?。]?$"),
    re.compile(r"^有没有(其他)?问题[？?。]?$"),
    re.compile(r"^是否有异议[？?。]?$"),
    re.compile(r"^有没有异议[？?。]?$"),
    re.compile(r"^还有人补充吗[？?。]?$"),
    re.compile(r"^还有没有补充[？?。]?$"),
    re.compile(r"^我补充一下[。.!！]?$"),
    re.compile(r"^我来说一下[。.!！]?$"),
    re.compile(r"^我简单说一下[。.!！]?$"),
]

QUESTION_PATTERN = re.compile(
    r"(吗|么|呢|是否|是不是|有没有|能否|可否|为什么|怎么|何时|什么时候|谁负责)[？?]?"
)

OPEN_ISSUE_PATTERN = re.compile(
    r"(尚未|还没|没有明确|未明确|待确认|等待确认|仍需确认|"
    r"暂未确定|尚未确认|没有最终决定|不能确认|"
    r"暂时无法|无法现场|规则缺失|方案缺失|尚不清楚|"
    r"未解决|仍未解决|存在问题|缺少|遗漏|不确定)"
)

RISK_PATTERN = re.compile(
    r"(风险|隐患|可能导致|可能影响|受到影响|会导致|容易导致|"
    r"一旦.+?(会|可能)|如果.+?(会|可能|导致|影响)|"
    r"否则|资损|数据丢失|返工|延期|故障|投诉|失败|"
    r"不稳定|超时|失败|异常)"
)

TIME_PATTERN = re.compile(
    r"("
    r"今天|今日|明天|明日|后天|今晚|上午|下午|晚上|"
    r"本周|下周|这周|本月|下月|月底|月末|年内|"
    r"周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{1,2}\s*[月/-]\s*\d{1,2}\s*日?|"
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"\d+\s*(分钟|小时|天|日|周|个月|月)|"
    r"之前|以前|以内|之内|截止|截至|前完成|前提交"
    r")"
)

ASSIGNMENT_PATTERN = re.compile(
    r"("
    r"由.{1,15}?(负责|完成|跟进|处理|提交|更新|补充|启动)|"
    r".{1,12}?(需要|需在|必须在|应当在).{0,30}?"
    r"(完成|补充|更新|提交|处理|跟进|启动|编写|修复|确认|同步|排查|验证|评估|安排)|"
    r"(后续安排|下一步完成).{0,30}?|"
    r".{1,12}?(负责|承担).{0,30}?"
    r"(完成|补充|更新|提交|处理|跟进|启动|编写|修复|确认|同步|排查|验证|评估|安排)"
    r")"
)

BUSINESS_SIGNAL_PATTERN = re.compile(
    r"(需求|方案|接口|功能|开发|测试|上线|排期|风险|问题|"
    r"任务|负责人|截止|完成|更新|补充|确认|数据|文档|"
    r"设计|运营|产品|前端|后端|项目|客户|订单|退款|"
    r"会员|结算|系统|报告|用例|修复|灰度)"
)


# ---------------------------------------------------------------------------
# Validator 输出摘要
# ---------------------------------------------------------------------------

@dataclass
class ValidationSummary:
    changed: bool = False
    rules: list[str] = field(default_factory=list)

    def add(self, rule_name: str) -> None:
        self.changed = True
        self.rules.append(rule_name)

    def to_dict(self) -> dict[str, object]:
        return {
            "changed": self.changed,
            "rules": list(self.rules),
        }


# ---------------------------------------------------------------------------
# 基础工具函数
# ---------------------------------------------------------------------------

def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _has_non_final_decision_signal(text: str) -> bool:
    return _contains_any(text, NON_FINAL_DECISION_PATTERNS)


def _has_action_requirement_signal(text: str) -> bool:
    return bool(ASSIGNMENT_PATTERN.search(text))


def _normalize_flow_text(text: str) -> str:
    return text.strip().rstrip("。！？!?；;，,")


def is_pure_flow_utterance(text: str) -> bool:
    normalized = _normalize_flow_text(text)

    if normalized in PURE_FLOW_EXACT_TEXTS:
        return True

    return any(pattern.fullmatch(text.strip()) for pattern in PURE_FLOW_PATTERNS)


def _has_business_signal(text: str) -> bool:
    return bool(BUSINESS_SIGNAL_PATTERN.search(text))


def _combined_text(event: SemanticEvent, context: list[str]) -> str:
    parts = [event.source_text or ""]

    speaker = getattr(event, "speaker", None)
    if speaker:
        parts.append(str(speaker))

    parts.extend(item for item in context if item)

    return "\n".join(parts)


def _append_secondary_intent(event: SemanticEvent, intent: str) -> bool:
    if intent == event.primary_intent:
        return False

    if intent in event.secondary_intents:
        return False

    event.secondary_intents.append(intent)
    return True


def _set_event_type(event: SemanticEvent, event_type: str) -> None:
    """
    统一设置 event_type。

    当前代码仅使用第一阶段 Schema 中常见的合法值：
    action / state / question / decision / risk / information。

    如果你项目 Schema 的枚举有所不同，只需要调整这里。
    """
    event.event_type = event_type  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 分规则校验
# ---------------------------------------------------------------------------

def _validate_non_event(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    if event.primary_intent != "non_event":
        return

    if is_pure_flow_utterance(source_text):
        event.secondary_intents = []
        event.subject = None
        event.action = None
        event.object = None
        event.attributes.owner = None
        event.attributes.deadline = None
        event.attributes.status = "unknown"
        _set_event_type(event, "information")
        return

    # non_event 不允许吞掉带业务内容的句子。
    if OPEN_ISSUE_PATTERN.search(source_text):
        event.primary_intent = "open_issue"
        event.attributes.status = "blocked"
        _set_event_type(event, "state")

    elif RISK_PATTERN.search(source_text):
        event.primary_intent = "risk_warning"
        _set_event_type(event, "risk")

    elif _contains_any(source_text, COMMITMENT_PATTERNS):
        event.primary_intent = "commitment"
        _set_event_type(event, "action")

    elif bool(ASSIGNMENT_PATTERN.search(source_text)):
        event.primary_intent = "task_assignment"
        _set_event_type(event, "action")

    else:
        event.primary_intent = "information"
        _set_event_type(event, "information")

    event.needs_review = True
    summary.add("non_event_with_business_content_reclassified")


def _validate_agenda(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    if event.primary_intent != "agenda_statement":
        return

    if _contains_any(source_text, STRONG_AGENDA_SIGNALS):
        return

    event.primary_intent = "information"
    _set_event_type(event, "information")
    event.needs_review = True
    summary.add("weak_agenda_reclassified_to_information")


def _validate_proposal_and_decision(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    has_proposal = _contains_any(source_text, PROPOSAL_PATTERNS)
    has_confirmation = _contains_any(source_text, CONFIRMATION_PATTERNS)
    has_rejection = _contains_any(source_text, REJECTION_PATTERNS)
    has_confirmed_rejection = _contains_any(
        source_text,
        CONFIRMED_REJECTION_PATTERNS,
    )

    if event.primary_intent == "decision" and _has_non_final_decision_signal(source_text):
        if _has_action_requirement_signal(source_text):
            event.primary_intent = "task_assignment"
            _set_event_type(event, "action")
            event.attributes.status = "pending"
            _append_secondary_intent(event, "requirement")
            summary.add("non_final_decision_reclassified_to_task_assignment")
        else:
            event.primary_intent = "open_issue"
            _set_event_type(event, "state")
            event.attributes.status = "blocked"
            summary.add("non_final_decision_reclassified_to_open_issue")
        event.needs_review = True
        return

    # 有建议语气、没有确认语气，不允许成为正式决策。
    if (
        event.primary_intent == "decision"
        and has_proposal
        and not has_confirmation
    ):
        event.primary_intent = "proposal"
        _set_event_type(event, "action")
        event.attributes.status = "proposed"
        event.needs_review = True
        summary.add("proposal_text_downgraded_from_decision")

    # 正式确认的否决统一表示为：
    # primary=decision, secondary=rejection。
    #
    # “建议否决……”仍然是 proposal，因此必须排除 has_proposal。
    if (
        has_rejection
        and (has_confirmation or has_confirmed_rejection)
        and not has_proposal
    ):
        was_rejection = event.primary_intent == "rejection"

        event.primary_intent = "decision"
        _set_event_type(event, "decision")
        event.attributes.status = "confirmed"

        secondary_added = _append_secondary_intent(event, "rejection")

        if was_rejection:
            summary.add("confirmed_rejection_promoted_to_decision")
        elif secondary_added:
            summary.add("confirmed_rejection_secondary_intent_added")

    # 纯拒绝态度，没有正式确认/拍板信号时，保留 rejection。
    elif (
        event.primary_intent == "decision"
        and has_rejection
        and not has_confirmation
        and not has_confirmed_rejection
    ):
        event.primary_intent = "rejection"
        _set_event_type(event, "action")
        event.attributes.status = "rejected"
        event.needs_review = True
        summary.add("unconfirmed_rejection_demoted_from_decision")


def _validate_risk(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    if event.primary_intent != "risk_warning":
        return

    if RISK_PATTERN.search(source_text):
        _set_event_type(event, "risk")
        return

    if OPEN_ISSUE_PATTERN.search(source_text):
        event.primary_intent = "open_issue"
        _set_event_type(event, "state")
        event.attributes.status = "blocked"
        event.needs_review = True
        summary.add("risk_without_future_signal_reclassified_to_open_issue")
        return

    event.needs_review = True
    summary.add("risk_warning_without_risk_signal")


def _validate_open_issue(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    if event.primary_intent != "open_issue":
        return

    # 流程提问不应该进入遗留问题。
    if is_pure_flow_utterance(source_text):
        event.primary_intent = "non_event"
        _set_event_type(event, "information")
        event.attributes.status = "unknown"
        event.needs_review = False
        summary.add("flow_question_reclassified_to_non_event")
        return

    # 普通问句，没有任何“尚未解决”信号，应归为 question。
    if (
        QUESTION_PATTERN.search(source_text)
        and not OPEN_ISSUE_PATTERN.search(source_text)
    ):
        event.primary_intent = "question"
        _set_event_type(event, "question")
        event.attributes.status = "discussing"
        event.needs_review = True
        summary.add("plain_question_reclassified_from_open_issue")


def _validate_commitment(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    if event.primary_intent != "commitment":
        return

    has_commitment_signal = _contains_any(
        source_text,
        COMMITMENT_PATTERNS,
    )
    has_assignment_signal = bool(ASSIGNMENT_PATTERN.search(source_text))

    if has_commitment_signal:
        _set_event_type(event, "action")

        # 第一人称承诺的 owner 可以是当前 speaker。
        if not event.attributes.owner and event.speaker:
            event.attributes.owner = event.speaker
            summary.add("commitment_owner_filled_from_speaker")

        return

    if has_assignment_signal:
        event.primary_intent = "task_assignment"
        _set_event_type(event, "action")
        summary.add("assignment_text_reclassified_from_commitment")
        return

    event.needs_review = True
    summary.add("commitment_without_first_person_signal")


def _validate_assignment_and_requirement(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    has_assignment = bool(ASSIGNMENT_PATTERN.search(source_text))
    has_requirement = _contains_any(source_text, REQUIREMENT_PATTERNS)

    # 同一主体、动作、对象下，不重复生成 requirement 事件。
    # 使用 task_assignment 作为主意图，requirement 作为辅助意图。
    if event.primary_intent == "requirement" and has_assignment:
        event.primary_intent = "task_assignment"
        _set_event_type(event, "action")

        _append_secondary_intent(event, "requirement")

        if event.attributes.status == "unknown":
            event.attributes.status = "confirmed"

        summary.add("assigned_requirement_promoted_to_task_assignment")
        return

    if event.primary_intent == "task_assignment":
        _set_event_type(event, "action")

        if has_requirement:
            if _append_secondary_intent(event, "requirement"):
                summary.add("requirement_added_as_secondary_intent")


def _validate_owner(
    event: SemanticEvent,
    combined_text: str,
    summary: ValidationSummary,
) -> None:
    owner = event.attributes.owner

    if not owner:
        return

    owner_text = str(owner).strip()
    speaker_text = str(event.speaker).strip() if event.speaker else ""

    if owner_text in combined_text:
        return

    # 第一人称承诺时，模型可能输出 speaker 名称；
    # 允许 owner 与当前 speaker 相同。
    if speaker_text and owner_text == speaker_text:
        return

    event.attributes.owner = None
    event.needs_review = True
    summary.add("owner_not_supported_by_source")


def _validate_deadline(
    event: SemanticEvent,
    combined_text: str,
    summary: ValidationSummary,
) -> None:
    deadline = event.attributes.deadline

    if not deadline:
        return

    if TIME_PATTERN.search(combined_text):
        return

    event.attributes.deadline = None
    event.needs_review = True
    summary.add("deadline_not_supported_by_source")


def _validate_evidence(
    event: SemanticEvent,
    source_text: str,
    summary: ValidationSummary,
) -> None:
    evidence_source = event.evidence.source_text or ""

    # source_text 应与当前输入发言一致。
    # 不允许证据文本来自模型自行补全。
    if evidence_source != source_text:
        event.evidence.source_text = source_text
        event.needs_review = True
        summary.add("evidence_source_text_replaced")

    quote = event.evidence.quote

    if quote and quote not in source_text:
        event.evidence.quote = None
        event.needs_review = True
        summary.add("evidence_quote_removed")


def _validate_confidence(
    event: SemanticEvent,
    summary: ValidationSummary,
) -> None:
    if event.confidence.overall >= 0.7:
        return

    if event.needs_review:
        return

    event.needs_review = True
    summary.add("low_confidence_marked_for_review")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def validate_semantic_event(
    event: SemanticEvent,
    context: list[str] | None = None,
) -> tuple[SemanticEvent, ValidationSummary]:
    """
    对模型输出的单个 SemanticEvent 执行规则校验。

    参数：
        event:
            已经通过基础 JSON / Pydantic 解析的语义事件。

        context:
            当前发言之前允许用于证据校验的上下文原文列表。
            建议最多传前 2～3 条 utterance，避免 owner 或 deadline
            被过长上下文错误支持。

    返回：
        tuple[SemanticEvent, ValidationSummary]

        - 修正后的 SemanticEvent
        - Validator 命中的规则摘要
    """
    context = context or []
    summary = ValidationSummary()

    source_text = event.source_text or ""
    combined_text = _combined_text(event, context)

    _validate_non_event(event, source_text, summary)
    _validate_agenda(event, source_text, summary)
    _validate_proposal_and_decision(event, source_text, summary)
    _validate_risk(event, source_text, summary)
    _validate_open_issue(event, source_text, summary)
    _validate_commitment(event, source_text, summary)
    _validate_assignment_and_requirement(event, source_text, summary)

    _validate_owner(event, combined_text, summary)
    _validate_deadline(event, combined_text, summary)
    _validate_evidence(event, source_text, summary)
    _validate_confidence(event, summary)

    return event, summary
def validate_semantic_events(
    events: list[SemanticEvent],
    context: list[str] | None = None,
) -> tuple[list[SemanticEvent], list[ValidationSummary]]:
    """
    批量校验 SemanticEvent。

    参数：
        events:
            待校验的语义事件列表。

        context:
            当前 utterance 前允许使用的上下文文本。
            同一批事件共享该上下文。

    返回：
        tuple[
            list[SemanticEvent],
            list[ValidationSummary],
        ]

        第一个元素是校验后的事件列表；
        第二个元素是每个事件对应的校验摘要。
    """
    validated_events: list[SemanticEvent] = []
    validation_summaries: list[ValidationSummary] = []

    for event in events:
        validated_event, summary = validate_semantic_event(
            event=event,
            context=context,
        )
        validated_events.append(validated_event)
        validation_summaries.append(summary)

    return validated_events, validation_summaries
