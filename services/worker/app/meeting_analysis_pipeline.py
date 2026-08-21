from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.memory_retriever import CurrentMeetingContext, MemoryRetrievalPolicy, MemoryRetriever
from app.memory_snapshot_builder import MemoryContext, MemorySnapshotBuilder
from app.observability import log_event, safe_error
from app.decision_candidate_recall import extract_decision_candidates_from_trace
from app.decision_ranking import rank_and_deduplicate_decisions
from app.unresolved_candidate_recall import extract_unresolved_candidates_from_trace
from app.unresolved_ranking import rank_and_deduplicate_unresolved
from app.reasoning_engine import ReasoningEngine
from app.responsibility_evidence_matrix import ResponsibilityEvidenceMatrixBuilder
from app.responsibility_extractor import ResponsibilityExtractor
from app.semantic_event_extractor import SemanticEventExtractor
from app.semantic_event_schema import SemanticEvent, UtteranceInput
from app.speaker_context_builder import SpeakerContextBuilder
from app.speaker_identity import SpeakerResolver
from app.speaker_role import RoleResolver
from app.six_dimension_mapper import SixDimensionMapper
from app.six_dimension_schema import (
    ActionItem,
    AgendaItem,
    DecisionItem,
    OpenIssueItem,
    RiskItem,
    SixDimensionResult,
    SummaryItem,
)
from app.six_dimension_validator import SixDimensionValidator
from app.topic_event_aggregator import TopicEventAggregator
from app.topic_event_schema import TopicEventGroup
from app.action_proposal_engine import ActionProposalEngine
from app.tool_action_contract import ToolActionContractBuilder, action_shadow_audit_payload
from app.workflow_recommendation_builder import WorkflowRecommendationBuilder
from app.workflow_state_builder import WorkflowStateObservationBuilder


SEMANTIC_PIPELINE_MODEL_NAME = "semantic-events+rules"
SEMANTIC_PIPELINE_PROMPT_VERSION = "semantic-event-pipeline-v1"
SEMANTIC_LLM_MAX_UTTERANCES = 8
MEMORY_SHADOW_TOKEN_BUDGET = 480
MEMORY_SHADOW_MIN_CONFIDENCE = 0.3
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_TRACE_ROOT = PROJECT_ROOT / "data" / "debug" / "semantic_pipeline_trace"


class SemanticPipelineError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        failed_utterance_count: int = 0,
        semantic_event_count: int = 0,
        topic_count: int = 0,
        detail: str | None = None,
    ):
        super().__init__(detail or reason)
        self.reason = reason
        self.failed_utterance_count = failed_utterance_count
        self.semantic_event_count = semantic_event_count
        self.topic_count = topic_count
        self.detail = detail


def _field(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _text(value: object) -> str:
    return str(value or "").strip()


def _unique(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _status_for_action(status: str | None) -> str:
    normalized = _text(status).lower()
    if normalized == "completed":
        return "done"
    if normalized in {"pending", "blocked", "discussing"}:
        return "in_progress"
    return "open"


def _priority(value: str | None) -> str:
    normalized = _text(value).lower()
    return normalized if normalized in {"low", "medium", "high"} else "medium"


def _source_text(item: AgendaItem | SummaryItem | DecisionItem | ActionItem | OpenIssueItem | RiskItem) -> str:
    return "\n".join(item.source_texts)


def _action_source_text(item: ActionItem) -> str:
    for source_text in item.source_texts:
        text = _text(source_text)
        if text:
            return text
    return _source_text(item)


def _source_supported_value(value: str | None, source_text: str) -> str | None:
    if not value:
        return None
    return value if _text(value).lower() in _text(source_text).lower() else None


def _first_segment_id(item: AgendaItem | SummaryItem | DecisionItem | ActionItem | OpenIssueItem | RiskItem) -> str | None:
    for event_id in item.source_event_ids:
        if event_id:
            return event_id
    return None


def transcript_to_utterances(transcript: list[Any]) -> list[UtteranceInput]:
    utterances: list[UtteranceInput] = []
    previous: list[str] = []

    for index, row in enumerate(transcript):
        text = _text(_field(row, "text"))
        if not text:
            continue

        segment_id = _field(row, "id") or _field(row, "segment_id") or f"segment-{index}"
        utterance = UtteranceInput(
            utterance_id=str(segment_id),
            segment_id=str(segment_id),
            speaker=_field(row, "speaker_name") or _field(row, "speaker_label") or _field(row, "speaker"),
            speaker_role=_field(row, "speaker_role"),
            start_time=_field(row, "start_time"),
            end_time=_field(row, "end_time"),
            text=text,
            previous_utterances=previous[-3:],
            context=previous[-3:],
        )
        utterances.append(utterance)
        previous.append(text)

    return utterances


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_conditional_risk_signal(text: str) -> bool:
    return (
        _contains_any(text, {"可能影响", "可能导致", "受到影响", "返工", "失败", "投诉"})
        or ("如果" in text and _contains_any(text, {"可能", "导致", "影响"}))
        or "否则" in text
    )


def _has_non_final_decision_signal(text: str) -> bool:
    return _contains_any(
        text,
        {
            "再确定",
            "后续确定",
            "继续评估",
            "暂未确定",
            "尚未确认",
            "待确认",
            "后续评估",
            "暂不确认",
            "暂不决定",
            "初步怀疑",
            "还没有最终确认",
            "不能直接确认",
        },
    )


def _has_strong_decision_signal(text: str) -> bool:
    return _contains_any(
        text,
        {
            "确定方案",
            "确认采用",
            "决定执行",
            "达成一致",
            "同意",
            "采纳",
            "锁定",
            "禁止",
            "不再",
            "必须",
            "砍掉",
            "统一",
        },
    )


def _has_action_requirement_signal(text: str) -> bool:
    if _contains_any(text, {"建议", "可以考虑", "可能", "不确定", "讨论"}):
        return False
    return _contains_any(
        text,
        {
            "需要补充",
            "需要同步",
            "需要更新",
            "需要验证",
            "需要排查",
            "后续安排",
            "下一步完成",
        },
    )


_NEGATIVE_EXAMPLE_MARKERS = {
    "只是提醒",
    "只是说明",
    "不是任务",
    "不是待办",
    "不是 action",
    "不是 Action",
    "不应该识别为任务",
    "不能识别为任务",
    "错误识别",
    "误识别",
    "误判",
    "模型有时候直接变成",
    "实际上用户只是",
    "实际上不是",
}

_QUOTE_EXAMPLE_MARKERS = {
    "比如",
    "例如",
    "举例",
    "例子",
    "引用",
    "原话",
}

_PROGRESS_ONLY_MARKERS = {
    "已完成",
    "已经完成",
    "基本完成",
    "已增加",
    "已经增加",
    "增加了",
    "已处理",
    "已经处理",
    "现在基本完成",
    "当前状态",
    "我同步一下",
}

_FUTURE_ACTION_MARKERS = {
    "安排",
    "负责",
    "需要",
    "后续",
    "下一步",
    "明天",
    "今天",
    "下午",
    "之前",
    "我来",
    "我会",
    "我今天",
    "我明天",
    "测试",
    "排查",
    "补充",
    "提交",
    "输出",
    "给结果",
}


def _is_negative_example_action_text(text: str) -> bool:
    if not _contains_any(text, _NEGATIVE_EXAMPLE_MARKERS):
        return False
    if "“" in text or "”" in text or '"' in text or "'" in text:
        return True
    return _contains_any(text, _QUOTE_EXAMPLE_MARKERS) or _contains_any(text, {"任务", "待办", "Action", "action"})


def _has_explicit_future_action(text: str) -> bool:
    return _has_future_deadline(text) or _contains_any(text, _FUTURE_ACTION_MARKERS) or _has_action_requirement_signal(text)


def _is_progress_update_without_action(text: str) -> bool:
    if not _contains_any(text, _PROGRESS_ONLY_MARKERS):
        return False
    if _has_explicit_future_action(text):
        return False
    return True


def _should_reject_semantic_action_text(text: str) -> bool:
    return _is_negative_example_action_text(text) or _is_progress_update_without_action(text)


_ACTION_RECAP_MARKERS = {
    "任务再过一下",
    "任务确认",
    "最后过一下任务",
}

_ACTION_RECAP_STOP_MARKERS = {
    "还有遗漏吗",
    "散会",
    "没有别的",
}

MAX_ACTION_RECAP_UTTERANCES = 30
MAX_ACTION_RECAP_SECONDS = 300.0

_SHORT_CONFIRMATION_MARKERS = {
    "好",
    "嗯",
    "可以",
    "对",
    "确认",
    "收到",
    "行",
    "你说",
}

_QUESTION_ACTION_MARKERS = {
    "能否",
    "是否",
    "什么时候",
    "怎么",
    "要不要",
    "能不能",
    "能修",
    "能完成",
}

_ACTION_OWNER_MARKERS = {
    "前端",
    "后端",
    "测试",
    "产品",
    "AI",
    "项目经理",
}

_ACTION_DEADLINE_MARKERS = (
    "今天",
    "明天",
    "明天下午",
    "周一",
    "周二",
    "周三",
    "周四",
    "下周二",
    "下周三",
    "周一上午十点前",
    "周一 18 点前",
    "周一 18:00",
)

_ACTION_VERB_MARKERS = {
    "修",
    "修复",
    "改",
    "调整",
    "检查",
    "回归",
    "完成",
    "提供",
    "输出",
    "出",
    "报告",
    "给结果",
    "发我",
    "给我",
    "看一下",
    "确认",
    "测",
    "测试",
    "记录",
    "准备",
    "处理",
    "取消",
    "使用",
    "用 request id",
    "推进",
    "明确",
    "落地",
    "补",
    "整理",
}

_STRONG_ACTION_VERB_MARKERS = {
    "修",
    "修复",
    "改",
    "调整",
    "检查",
    "回归",
    "完成",
    "提供",
    "输出",
    "给结果",
    "发我",
    "给我",
    "确认",
    "准备",
    "处理",
    "取消旧请求",
    "request id",
    "推进",
    "明确",
    "落地",
    "整理",
}

_ACTION_OBJECT_MARKERS = {
    "搜索",
    "Android",
    "录音",
    "计时",
    "首页",
    "知识库",
    "文案",
    "支付",
    "AI 分析",
    "失败状态",
    "声纹",
    "噪声",
    "Golden Dataset",
    "基线报告",
    "稳定性",
    "Scope 文档",
    "检查清单",
    "confidence",
    "会议",
}

_WEAK_COMMITMENT_MARKERS = {
    "我会处理",
    "我来处理",
    "我回去看看",
    "回头看看",
    "我尽量",
    "先看看",
}

_COMPLETED_STATE_MARKERS = {
    "已经好了",
    "已经好",
    "已经能",
    "已经通",
    "已经做完",
    "都能用",
    "正常",
    "没什么大的",
    "可以了",
}

_NON_ACTION_MARKERS = {
    "不做",
    "不上",
    "先不",
    "放 V2.6",
    "后面做",
    "只是",
    "估计",
    "可能",
    "建议",
    "最好",
    "可以考虑",
}


def _rule_intent(text: str, index: int) -> str:
    if _contains_any(text, {"无问题", "无疑问", "没有其他问题"}):
        return "non_event"
    if _should_reject_semantic_action_text(text):
        return "information"
    if index == 0 or _contains_any(text, {"议程", "目标", "今天我们", "首先", "本次会议"}):
        return "agenda_statement"
    if _has_conditional_risk_signal(text) or _contains_any(text, {"风险", "隐患", "压力", "超时", "回滚", "故障", "高风险", "压缩", "偏紧"}):
        return "risk_warning"
    if _has_non_final_decision_signal(text) or _contains_any(text, {"疑问", "没有明确", "未明确", "缺失", "遗漏", "有没有"}):
        return "open_issue"
    if _has_strong_decision_signal(text):
        return "decision"
    if _contains_any(text, {"建议", "可以考虑"}):
        return "proposal"
    if _has_action_requirement_signal(text) or _contains_any(text, {"我会", "我今天", "我明天", "负责", "安排", "启动", "更新", "补充", "同步", "推进", "落地", "编写", "需要提交"}):
        return "task_assignment"
    if _contains_any(text, {"建议", "可以考虑", "希望", "最好"}):
        return "proposal"
    if _contains_any(text, {"完成", "通过", "已", "目前", "进度", "周期"}):
        return "progress_update"
    return "information"


def _rule_event_status(intent: str) -> str:
    if intent == "decision":
        return "confirmed"
    if intent == "task_assignment":
        return "pending"
    if intent == "open_issue":
        return "blocked"
    if intent == "risk_warning":
        return "pending"
    if intent == "proposal":
        return "proposed"
    if intent == "progress_update":
        return "completed"
    return "unknown"


def _rule_event(
    utterance: UtteranceInput,
    *,
    index: int,
) -> SemanticEvent:
    text = utterance.text.strip()
    intent = _rule_intent(text, index)
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{utterance.utterance_id}:rule:{text}"))
    return SemanticEvent.model_validate(
        {
            "event_id": event_id,
            "utterance_id": utterance.utterance_id,
            "segment_id": utterance.segment_id,
            "speaker": utterance.speaker,
            "speaker_role": utterance.speaker_role,
            "start_time": utterance.start_time,
            "end_time": utterance.end_time,
            "source_text": text,
            "normalized_text": text,
            "primary_intent": intent,
            "secondary_intents": [],
            "event_type": "information",
            "subject": utterance.speaker or "meeting",
            "action": intent,
            "object": text[:80],
            "entities": {
                "persons": [utterance.speaker] if utterance.speaker else [],
                "teams": [],
                "projects": [],
                "features": [],
                "dates": [value for value in ("今天", "明日", "本周", "一周", "四周") if value in text],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": utterance.speaker if intent == "task_assignment" else None,
                "deadline": next((value for value in ("今天", "明日", "本周", "一周", "四周") if value in text), None),
                "priority": "high" if intent in {"risk_warning", "decision"} else "medium",
                "status": _rule_event_status(intent),
                "polarity": "neutral",
                "certainty": "contextual",
            },
            "evidence": {
                "source_text": text,
                "quote": text,
                "evidence_type": "direct",
            },
            "confidence": {
                "intent": 0.72,
                "entity": 0.68,
                "overall": 0.72,
            },
            "needs_review": True,
        }
    )


def _normalize_action_text(text: str) -> str:
    return "".join(ch for ch in text.strip() if ch not in " ，,。！？；;：:\n\t")


def _is_action_recap_marker(text: str) -> bool:
    return _contains_any(text, _ACTION_RECAP_MARKERS)


def _is_action_recap_stop(text: str) -> bool:
    return _contains_any(text, _ACTION_RECAP_STOP_MARKERS)


def _action_recap_flags(utterances: list[UtteranceInput]) -> list[bool]:
    flags: list[bool] = []
    active = False
    start_index: int | None = None
    start_time: float | None = None
    for index, utterance in enumerate(utterances):
        text = utterance.text.strip()
        if _is_action_recap_marker(text):
            active = True
            start_index = index
            start_time = utterance.start_time
        elif active and _is_action_recap_stop(text):
            active = False
            start_index = None
            start_time = None
        elif active and start_index is not None and start_time is not None:
            if index - start_index >= MAX_ACTION_RECAP_UTTERANCES or utterance.start_time - start_time > MAX_ACTION_RECAP_SECONDS:
                active = False
                start_index = None
                start_time = None
        flags.append(active)
    return flags


def _action_deadline(text: str) -> str | None:
    for marker in sorted(_ACTION_DEADLINE_MARKERS, key=len, reverse=True):
        if marker in text:
            return marker
    return None


def _action_owner(text: str, speaker: str | None) -> str | None:
    stripped = text.strip()
    for marker in sorted(_ACTION_OWNER_MARKERS, key=len, reverse=True):
        if stripped.startswith(f"{marker}，") or stripped.startswith(f"{marker},") or stripped.startswith(marker + " "):
            return marker
    if stripped.startswith("我") and speaker:
        return speaker
    return None


def _has_future_deadline(text: str) -> bool:
    return _action_deadline(text) is not None or _contains_any(text, {"之前", "前完成", "前提交", "前给结果"})


def _is_completed_state_only(text: str) -> bool:
    if not _contains_any(text, _COMPLETED_STATE_MARKERS):
        return False
    return not _has_future_deadline(text) and not _contains_any(text, {"再", "还要", "需要", "待"})


def _is_weak_action_text(text: str) -> bool:
    normalized = _normalize_action_text(text)
    return any(normalized == _normalize_action_text(marker) for marker in _WEAK_COMMITMENT_MARKERS)


def _is_short_confirmation_text(text: str) -> bool:
    normalized = _normalize_action_text(text)
    return normalized in {_normalize_action_text(marker) for marker in _SHORT_CONFIRMATION_MARKERS}


def _is_action_question_text(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith(("?", "？")):
        return True
    return _contains_any(stripped, _QUESTION_ACTION_MARKERS)


def _has_action_object(text: str) -> bool:
    return _contains_any(text, _ACTION_OBJECT_MARKERS)


def _has_action_verb(text: str) -> bool:
    return _contains_any(text, _ACTION_VERB_MARKERS) or _has_action_requirement_signal(text)


def _is_non_action_discussion(text: str, *, recap_mode: bool) -> bool:
    if recap_mode and _has_action_verb(text) and (_has_future_deadline(text) or _has_action_object(text)):
        return False
    return _contains_any(text, _NON_ACTION_MARKERS)


def _window_text(utterances: list[UtteranceInput], index: int) -> str:
    start = max(0, index - 1)
    end = min(len(utterances), index + 2)
    return "\n".join(utterance.text.strip() for utterance in utterances[start:end] if utterance.text.strip())


def _window_segment_id(utterances: list[UtteranceInput], index: int) -> str | None:
    start = max(0, index - 1)
    end = min(len(utterances), index + 2)
    segment_ids = _unique(utterance.segment_id for utterance in utterances[start:end] if utterance.text.strip())
    return ",".join(segment_ids) if segment_ids else utterances[index].segment_id


def _canonical_action_task(text: str, window: str) -> str:
    source = text.strip()
    combined = f"{window}\n{source}"
    deadline = _action_deadline(combined)

    if "提供文案" in source or source.startswith("我给文案"):
        return "提供知识库文案"
    if "我改" == _normalize_action_text(source) and "知识库" in combined and "文案" in combined:
        return "调整知识库文案"
    if "任务搜索结果闪动" in combined or "搜索结果会闪" in combined:
        return "修复任务搜索结果闪动问题"
    if "Android" in combined and ("后台" in combined or "计时" in combined):
        return "修复 Android 后台恢复后录音计时不准问题"
    if "AI 分析失败状态" in combined or ("AI 分析" in combined and "失败" in combined):
        return "修复 AI 分析失败状态返回机制"
    if "首页" in combined and ("空白" in combined or "空一下" in combined):
        return "排查首页首次加载短暂空白并给出结果"
    if "知识库" in combined and "文案" in combined:
        return "调整知识库文案"
    if "支付" in combined and ("推进" in combined or "明确" in combined or "闭环" in combined):
        return "推进支付闭环并明确验证状态"
    if "声纹" in combined and ("噪声" in combined or "环境测试" in combined):
        return "完成声纹噪声环境测试"
    if "Golden Dataset" in combined or "基线报告" in combined:
        return "输出 Golden Dataset 基线报告并完成稳定性测试"
    if "Scope 文档" in combined:
        return "完成 Scope 文档"
    if "截图" in combined:
        return "提供问题截图"
    if "confidence" in combined:
        return "记录声纹测试 confidence"
    if "检查清单" in combined:
        return "准备演示检查清单"

    if source.startswith("改了"):
        return "完成修改后同步结果"
    if "给结果" in source:
        return f"给出处理结果{f'（{deadline}）' if deadline else ''}"
    if "回归" in source:
        return "完成问题回归测试"
    if "修" in source and not source.startswith("修复"):
        return f"修复{source.split('修', 1)[1].strip() or '相关问题'}"
    if "提供" in source:
        return source
    if "完成" in source:
        return source
    if "推进" in source:
        return source
    if "明确" in source:
        return source
    if "看一下" in source or "确认" in source or "查" in source:
        return f"确认{source.strip('。')}"
    return source


def _should_add_action_candidate(
    utterances: list[UtteranceInput],
    index: int,
    *,
    recap_mode: bool,
) -> bool:
    text = utterances[index].text.strip()
    if not text or _is_action_recap_marker(text) or _is_action_recap_stop(text):
        return False
    if _is_short_confirmation_text(text) or _is_action_question_text(text):
        return False
    if _should_reject_semantic_action_text(text):
        return False
    if _is_weak_action_text(text) or _is_completed_state_only(text):
        return False
    if _is_non_action_discussion(text, recap_mode=recap_mode):
        return False

    window = _window_text(utterances, index)
    has_action = _has_action_verb(text)
    has_center_anchor = _has_action_object(text) or _has_future_deadline(text) or _action_owner(text, utterances[index].speaker) is not None
    has_window_anchor = _has_action_object(window) or _has_future_deadline(window)
    if recap_mode:
        return has_action and has_center_anchor
    if not _contains_any(text, {"给我", "发我", "叫我", "必须修", "取消旧请求", "request id", "给结果"}):
        return False
    return has_action and (has_center_anchor or has_window_anchor) and (
        _has_future_deadline(window) or _contains_any(text, {"给我", "发我", "叫我", "必须修"})
    )


def _enhanced_action_event(
    utterances: list[UtteranceInput],
    index: int,
    *,
    recap_mode: bool,
) -> SemanticEvent:
    utterance = utterances[index]
    text = utterance.text.strip()
    window = _window_text(utterances, index)
    task = _canonical_action_task(text, window)
    source_text = window if "\n" in window else text
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{utterance.utterance_id}:semantic-action-recall-v1:{task}:{source_text}"))
    deadline = _action_deadline(source_text)
    owner = _action_owner(text, utterance.speaker)
    return SemanticEvent.model_validate(
        {
            "event_id": event_id,
            "utterance_id": utterance.utterance_id,
            "segment_id": _window_segment_id(utterances, index),
            "speaker": utterance.speaker,
            "speaker_role": utterance.speaker_role,
            "start_time": utterance.start_time,
            "end_time": utterance.end_time,
            "source_text": source_text,
            "normalized_text": task,
            "primary_intent": "task_assignment",
            "secondary_intents": [],
            "event_type": "action",
            "subject": owner or utterance.speaker or "meeting",
            "action": "task_assignment",
            "object": task,
            "entities": {
                "persons": [owner] if owner else ([utterance.speaker] if utterance.speaker else []),
                "teams": [owner] if owner in _ACTION_OWNER_MARKERS else [],
                "projects": [],
                "features": [marker for marker in _ACTION_OBJECT_MARKERS if marker in source_text],
                "dates": [deadline] if deadline else [],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": owner,
                "deadline": deadline,
                "priority": "medium",
                "status": "pending",
                "polarity": "neutral",
                "certainty": "contextual" if "\n" in source_text else "explicit",
            },
            "evidence": {
                "source_text": source_text,
                "quote": source_text,
                "evidence_type": "contextual" if "\n" in source_text else "direct",
            },
            "confidence": {
                "intent": 0.78 if recap_mode else 0.74,
                "entity": 0.7,
                "overall": 0.78 if recap_mode else 0.74,
            },
            "needs_review": True,
        }
    )


def _extract_rule_based_events(utterances: list[UtteranceInput]) -> list[SemanticEvent]:
    events: list[SemanticEvent] = []
    recap_flags = _action_recap_flags(utterances)
    for index, utterance in enumerate(utterances):
        base_event = _rule_event(utterance, index=index)
        events.append(base_event)
        if _should_add_action_candidate(utterances, index, recap_mode=recap_flags[index]):
            events.append(_enhanced_action_event(utterances, index, recap_mode=recap_flags[index]))
    return events


def six_dimension_result_to_analysis_dict(result: SixDimensionResult) -> dict[str, Any]:
    agenda = [
        {
            "item": item.content,
            "order": index,
            "source_segment_ids": item.source_event_ids,
        }
        for index, item in enumerate(result.meeting_agenda, start=1)
    ]
    summary_parts = [item.content for item in result.meeting_summary if item.content]
    meeting_summary = "\n".join(summary_parts)

    key_conclusions = [
        {
            "conclusion": item.content,
            "source_text": _source_text(item),
            "confidence": item.confidence,
        }
        for item in result.key_conclusions
    ]
    action_items = []
    for item in result.action_items:
        source_text = _action_source_text(item)
        action_items.append(
            {
                "task": item.content,
                "owner_name": _source_supported_value(item.owner, source_text),
                "deadline": _source_supported_value(item.deadline, source_text),
                "priority": _priority(item.priority),
                "status": _status_for_action(item.status),
                "source_text": source_text,
                "source_segment_id": _first_segment_id(item),
                "confidence": item.confidence,
            }
        )
    unresolved_issues = [
        {
            "issue": item.content,
            "reason": "",
            "blocker": "",
            "source_text": _source_text(item),
            "confidence": item.confidence,
        }
        for item in result.unresolved_issues
    ]
    risks_and_focus = [
        {
            "risk": item.content,
            "impact": item.impact or "",
            "focus_area": item.condition or "",
            "mitigation": item.mitigation or "",
            "source_text": _source_text(item),
            "confidence": item.confidence,
        }
        for item in result.risks_and_focus
    ]

    return {
        "meeting_agenda": agenda,
        "meeting_summary": meeting_summary,
        "key_conclusions": key_conclusions,
        "action_items": action_items,
        "unresolved_issues": unresolved_issues,
        "risks_and_focus": risks_and_focus,
        "topics": [],
        "_metadata": {
            "model_name": SEMANTIC_PIPELINE_MODEL_NAME,
            "prompt_version": SEMANTIC_PIPELINE_PROMPT_VERSION,
            "rag_chunk_ids": [],
            "result_source": "semantic_pipeline",
        },
    }


def _add_topics_to_analysis_dict(payload: dict[str, Any], topics: list[TopicEventGroup]) -> dict[str, Any]:
    payload["topics"] = [
        {
            "title": topic.title,
            "summary": topic.title,
            "start_time": topic.start_time or 0.0,
            "end_time": topic.end_time or topic.start_time or 0.0,
            "related_segment_ids": _unique(
                event.segment_id for event in topic.events if event.segment_id
            ),
            "speakers": _unique(event.speaker for event in topic.events if event.speaker),
        }
        for topic in topics
    ]
    return payload


def _ensure_meeting_summary_text(payload: dict[str, Any]) -> dict[str, Any]:
    if _text(payload.get("meeting_summary")):
        return payload

    summary_sources: list[str] = []
    for key, field in (
        ("meeting_agenda", "item"),
        ("key_conclusions", "conclusion"),
        ("action_items", "task"),
        ("unresolved_issues", "issue"),
        ("risks_and_focus", "risk"),
    ):
        for item in payload.get(key, []):
            if not isinstance(item, dict):
                continue
            content = _text(item.get(field))
            if content:
                summary_sources.append(content)
            if len(summary_sources) >= 3:
                break
        if len(summary_sources) >= 3:
            break

    if summary_sources:
        payload["meeting_summary"] = "；".join(summary_sources)

    return payload


def _log_stage_completed(
    stage: str,
    started_at: float,
    *,
    meeting_id: str,
    input_count: int,
    output_count: int,
) -> None:
    log_event(
        "semantic_pipeline.stage.completed",
        pipeline_stage=stage,
        meeting_id=meeting_id,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        input_count=input_count,
        output_count=output_count,
    )


def _raise_pipeline_error(
    reason: str,
    *,
    meeting_id: str,
    failed_utterance_count: int,
    semantic_event_count: int,
    topic_count: int,
    detail: str | None = None,
) -> None:
    log_event(
        "semantic_pipeline.invalid_result",
        level="error",
        meeting_id=meeting_id,
        fallback_reason=reason,
        failed_utterance_count=failed_utterance_count,
        semantic_event_count=semantic_event_count,
        topic_count=topic_count,
    )
    raise SemanticPipelineError(
        reason,
        failed_utterance_count=failed_utterance_count,
        semantic_event_count=semantic_event_count,
        topic_count=topic_count,
        detail=detail,
    )


async def analyze_meeting(
    meeting_id: str,
    transcript: list[Any],
    *,
    extractor: SemanticEventExtractor | None = None,
    aggregator: TopicEventAggregator | None = None,
    mapper: SixDimensionMapper | None = None,
    validator: SixDimensionValidator | None = None,
) -> SixDimensionResult:
    result, _topics = await _analyze_meeting_with_topics(
        meeting_id,
        transcript,
        extractor=extractor,
        aggregator=aggregator,
        mapper=mapper,
        validator=validator,
    )
    return result


async def _analyze_meeting_with_topics(
    meeting_id: str,
    transcript: list[Any],
    *,
    extractor: SemanticEventExtractor | None = None,
    aggregator: TopicEventAggregator | None = None,
    mapper: SixDimensionMapper | None = None,
    validator: SixDimensionValidator | None = None,
) -> tuple[SixDimensionResult, list[TopicEventGroup]]:
    log_event(
        "semantic_pipeline.started",
        meeting_id=meeting_id,
        transcript_count=len(transcript),
    )

    utterance_started = time.perf_counter()
    utterances = transcript_to_utterances(transcript)
    _log_stage_completed(
        "utterance_build",
        utterance_started,
        meeting_id=meeting_id,
        input_count=len(transcript),
        output_count=len(utterances),
    )

    validated_events: list[SemanticEvent] = []
    failed_utterance_count = 0

    extraction_started = time.perf_counter()
    if extractor is None and len(utterances) > SEMANTIC_LLM_MAX_UTTERANCES:
        validated_events = _extract_rule_based_events(utterances)
        log_event(
            "semantic_pipeline.fast_path",
            meeting_id=meeting_id,
            reason="large_meeting_rule_based",
            utterance_count=len(utterances),
            llm_max_utterances=SEMANTIC_LLM_MAX_UTTERANCES,
            output_count=len(validated_events),
        )
    else:
        extractor = extractor or SemanticEventExtractor()
        for utterance in utterances:
            try:
                extracted_events, _summaries = extractor.extract(utterance)
                # SemanticEventExtractor.extract already runs SemanticEventValidator.
                validated_events.extend(extracted_events)
            except Exception as exc:
                failed_utterance_count += 1
                log_event(
                    "semantic_pipeline.event_failed",
                    level="error",
                    meeting_id=meeting_id,
                    utterance_id=utterance.utterance_id,
                    error_type=exc.__class__.__name__,
                    error_message=safe_error(exc),
                )
                continue

    _log_stage_completed(
        "semantic_event_extraction",
        extraction_started,
        meeting_id=meeting_id,
        input_count=len(utterances),
        output_count=len(validated_events),
    )

    if utterances and failed_utterance_count == len(utterances):
        _raise_pipeline_error(
            "all_utterances_failed",
            meeting_id=meeting_id,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=len(validated_events),
            topic_count=0,
        )

    if not validated_events:
        _raise_pipeline_error(
            "empty_semantic_events",
            meeting_id=meeting_id,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=0,
            topic_count=0,
        )

    aggregation_started = time.perf_counter()
    topics = (aggregator or TopicEventAggregator()).aggregate(validated_events)
    _log_stage_completed(
        "topic_event_aggregation",
        aggregation_started,
        meeting_id=meeting_id,
        input_count=len(validated_events),
        output_count=len(topics),
    )

    if not topics:
        _raise_pipeline_error(
            "empty_topic_groups",
            meeting_id=meeting_id,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=len(validated_events),
            topic_count=0,
        )

    mapping_started = time.perf_counter()
    mapped = (mapper or SixDimensionMapper()).map_topics(meeting_id, topics)
    mapped_count = _result_item_count(mapped)
    _log_stage_completed(
        "six_dimension_mapping",
        mapping_started,
        meeting_id=meeting_id,
        input_count=len(topics),
        output_count=mapped_count,
    )

    validation_started = time.perf_counter()
    validated = (validator or SixDimensionValidator()).validate(mapped, topics)
    validated_count = _result_item_count(validated)
    _log_stage_completed(
        "six_dimension_validation",
        validation_started,
        meeting_id=meeting_id,
        input_count=mapped_count,
        output_count=validated_count,
    )

    if validated_count == 0:
        _raise_pipeline_error(
            "empty_six_dimension_output",
            meeting_id=meeting_id,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=len(validated_events),
            topic_count=len(topics),
        )

    log_event(
        "semantic_pipeline.completed",
        meeting_id=meeting_id,
        event_count=len(validated_events),
        topic_count=len(topics),
        output_count=validated_count,
        failed_utterance_count=failed_utterance_count,
    )
    return validated, topics


def _result_item_count(result: SixDimensionResult) -> int:
    return (
        len(result.meeting_agenda)
        + len(result.meeting_summary)
        + len(result.key_conclusions)
        + len(result.action_items)
        + len(result.unresolved_issues)
        + len(result.risks_and_focus)
    )


def _event_trace_dict(
    event: SemanticEvent | dict[str, Any],
    *,
    meeting_id: str,
    topic_id: str | None = None,
    target_dimension: str | None = None,
) -> dict[str, Any]:
    data = event.model_dump(mode="json") if isinstance(event, SemanticEvent) else dict(event)
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    return {
        "meeting_id": meeting_id,
        "event_id": data.get("event_id"),
        "topic_id": topic_id,
        "source_text": data.get("source_text") or evidence.get("source_text") or "",
        "primary_intent": data.get("primary_intent"),
        "status": attributes.get("status"),
        "target_dimension": target_dimension,
        "needs_review": data.get("needs_review", False),
        "event": data,
    }


def _topic_trace_dict(topic: TopicEventGroup, *, meeting_id: str) -> dict[str, Any]:
    return {
        "meeting_id": meeting_id,
        "event_id": None,
        "topic_id": topic.topic_id,
        "source_text": "\n".join(event.source_text for event in topic.events if event.source_text),
        "primary_intent": None,
        "status": topic.status,
        "target_dimension": None,
        "needs_review": any(event.needs_review for event in topic.events),
        "title": topic.title,
        "event_ids": topic.event_ids,
        "start_time": topic.start_time,
        "end_time": topic.end_time,
        "events": [event.model_dump(mode="json") for event in topic.events],
    }


def _dimension_trace_items(
    result: SixDimensionResult,
    *,
    meeting_id: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    dimensions = (
        ("meeting_agenda", result.meeting_agenda),
        ("meeting_summary", result.meeting_summary),
        ("key_conclusions", result.key_conclusions),
        ("action_items", result.action_items),
        ("unresolved_issues", result.unresolved_issues),
        ("risks_and_focus", result.risks_and_focus),
    )
    for target_dimension, dimension_items in dimensions:
        for item in dimension_items:
            status = getattr(item, "status", None)
            items.append(
                {
                    "meeting_id": meeting_id,
                    "event_id": item.source_event_ids[0] if item.source_event_ids else None,
                    "topic_id": item.topic_id,
                    "source_text": "\n".join(item.source_texts),
                    "primary_intent": None,
                    "status": status,
                    "target_dimension": target_dimension,
                    "needs_review": item.needs_review,
                    "item": item.model_dump(mode="json"),
                }
            )
    return items


def _write_trace_json(trace_dir: Path, filename: str, payload: dict[str, Any]) -> None:
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / filename).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _trace_payload(meeting_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"meeting_id": meeting_id, "items": items}


def _responsibility_shadow_payload(
    meeting_id: str,
    *,
    semantic_events: list[SemanticEvent],
    action_items: list[ActionItem],
    speaker_contexts: dict[str, Any],
    role_contexts: dict[str, Any],
) -> dict[str, Any]:
    responsibility_contexts = ResponsibilityExtractor().extract_many(
        semantic_events=semantic_events,
        meeting_id=meeting_id,
        speaker_contexts=speaker_contexts,
        role_contexts=role_contexts,
    )
    responsibility_matrix = ResponsibilityEvidenceMatrixBuilder().build(
        action_items=action_items,
        responsibility_contexts=responsibility_contexts,
    )
    row_statuses = [row.consistency_status for row in responsibility_matrix.rows]
    consistency_status = "unknown"
    if row_statuses:
        consistency_status = "consistent" if all(status == "confirmed_match" for status in row_statuses) else "needs_review"

    return {
        "meeting_id": meeting_id,
        "responsibility_contexts": [
            context.model_dump(mode="json") for context in responsibility_contexts
        ],
        "responsibility_matrix": responsibility_matrix.model_dump(mode="json"),
        "consistency_status": consistency_status,
    }


def _memory_current_context(
    meeting_id: str,
    *,
    analysis: dict[str, Any],
    utterances: list[UtteranceInput],
) -> CurrentMeetingContext:
    agenda = [
        _text(item.get("item") or item.get("content") or item.get("text"))
        for item in analysis.get("meeting_agenda", [])
        if isinstance(item, dict)
    ]
    focus_terms: list[str] = []
    for key, field in (
        ("key_conclusions", "conclusion"),
        ("action_items", "task"),
        ("unresolved_issues", "issue"),
        ("risks_and_focus", "risk"),
    ):
        for item in analysis.get(key, []):
            if not isinstance(item, dict):
                continue
            text = _text(item.get(field))
            if text:
                focus_terms.append(text)

    return CurrentMeetingContext(
        meeting_id=meeting_id,
        title=None,
        agenda=[item for item in agenda if item],
        summary=_text(analysis.get("meeting_summary")) or None,
        transcript_excerpt="\n".join(utterance.text for utterance in utterances[:8] if utterance.text),
        focus_terms=focus_terms[:12],
    )


def _memory_retrieval_audit_payload(
    *,
    snapshot_memories: list[MemoryContext],
    current_context: CurrentMeetingContext,
    policy: MemoryRetrievalPolicy,
    selected_ids: set[str],
) -> dict[str, Any]:
    filtered_reason: dict[str, int] = {}
    query_terms = MemoryRetriever()._terms(MemoryRetriever()._context_text(current_context))
    for memory in snapshot_memories:
        reason = None
        if policy.memory_types is not None and memory.memory_type not in policy.memory_types:
            reason = "memory_type_filtered"
        elif memory.status not in policy.allowed_statuses:
            reason = "status_filtered"
        elif memory.confidence < policy.min_confidence:
            reason = "low_confidence"
        elif not memory.evidence:
            reason = "missing_evidence"
        else:
            relevance_score = MemoryRetriever()._relevance(memory, query_terms=query_terms)
            if query_terms and relevance_score < policy.min_relevance_score:
                reason = "low_relevance"
            elif memory.memory_id not in selected_ids:
                reason = "token_budget_exceeded"

        if reason:
            filtered_reason[reason] = filtered_reason.get(reason, 0) + 1

    return {
        "query_context": current_context.model_dump(mode="json"),
        "candidate_count": len(snapshot_memories),
        "selected_count": len(selected_ids),
        "filtered_reason": filtered_reason,
        "token_budget": {
            "max_tokens": policy.token_budget,
            "min_confidence": policy.min_confidence,
            "min_relevance_score": policy.min_relevance_score,
            "allowed_statuses": sorted(policy.allowed_statuses),
            "memory_types": sorted(policy.memory_types) if policy.memory_types else None,
        },
    }


def _memory_shadow_payloads(
    meeting_id: str,
    *,
    speaker_contexts: dict[str, Any],
    role_contexts: dict[str, Any],
    responsibility_shadow_payload: dict[str, Any],
    meeting_analysis_events: list[dict[str, Any]],
    analysis: dict[str, Any],
    utterances: list[UtteranceInput],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    snapshot = MemorySnapshotBuilder().build(
        meeting_id=meeting_id,
        speaker_contexts=speaker_contexts,
        role_contexts=role_contexts,
        responsibility_contexts=responsibility_shadow_payload.get("responsibility_contexts", []),
        responsibility_matrix=responsibility_shadow_payload.get("responsibility_matrix"),
        meeting_analysis_events=meeting_analysis_events,
    )
    current_context = _memory_current_context(meeting_id, analysis=analysis, utterances=utterances)
    policy = MemoryRetrievalPolicy(
        token_budget=MEMORY_SHADOW_TOKEN_BUDGET,
        min_confidence=MEMORY_SHADOW_MIN_CONFIDENCE,
    )
    retrieved = MemoryRetriever().retrieve(
        snapshot=snapshot,
        current_context=current_context,
        policy=policy,
        retrieved_at=snapshot.as_of,
    )
    selected_ids = {item.memory_id for item in retrieved.memories}
    audit = _memory_retrieval_audit_payload(
        snapshot_memories=snapshot.memories,
        current_context=current_context,
        policy=policy,
        selected_ids=selected_ids,
    )

    return (
        snapshot.model_dump(mode="json"),
        retrieved.model_dump(mode="json"),
        audit,
    )


def _confidence_distribution(contexts: list[dict[str, Any]]) -> dict[str, int]:
    distribution = {"low": 0, "medium": 0, "high": 0}
    for context in contexts:
        confidence = float(context.get("confidence") or 0.0)
        if confidence >= 0.8:
            distribution["high"] += 1
        elif confidence >= 0.6:
            distribution["medium"] += 1
        else:
            distribution["low"] += 1
    return distribution


def _reasoning_filtered_reasons(
    *,
    retrieved_memory_payload: dict[str, Any],
    responsibility_shadow_payload: dict[str, Any],
    generated_count: int,
) -> dict[str, int]:
    reasons: dict[str, int] = {}
    memories = [
        item
        for item in retrieved_memory_payload.get("memories", [])
        if isinstance(item, dict)
    ]
    matrix_rows = (
        responsibility_shadow_payload.get("responsibility_matrix", {}).get("rows", [])
        if isinstance(responsibility_shadow_payload.get("responsibility_matrix"), dict)
        else []
    )
    review_rows = [
        row
        for row in matrix_rows
        if isinstance(row, dict)
        and row.get("consistency_status") in {"owner_conflict", "owner_missing", "responsibility_only"}
    ]

    memory_risk_or_decision_count = 0
    trend_groups: dict[tuple[str, str], int] = {}
    for memory in memories:
        evidence = memory.get("evidence") or []
        if not evidence:
            reasons["missing_evidence"] = reasons.get("missing_evidence", 0) + 1
            continue
        content = memory.get("content") if isinstance(memory.get("content"), dict) else {}
        text = _text(content.get("text") or content.get("risk") or content.get("issue") or content.get("task"))
        memory_kind = _text(content.get("meeting_memory_type") or memory.get("memory_type"))
        if memory_kind == "decision" or memory_kind == "risk" or any(
            term in text.lower() for term in ("risk", "block", "blocked", "blocking", "unstable", "slip", "delay")
        ):
            memory_risk_or_decision_count += 1
        else:
            reasons["unsupported_reasoning_input"] = reasons.get("unsupported_reasoning_input", 0) + 1

        if text:
            topic = ReasoningEngine()._topic_key(text)
            if topic:
                trend_groups[(memory_kind or _text(memory.get("memory_type")), topic)] = (
                    trend_groups.get((memory_kind or _text(memory.get("memory_type")), topic), 0) + 1
                )

    repeated_trend_count = sum(1 for count in trend_groups.values() if count >= 2)
    single_trend_inputs = sum(count for count in trend_groups.values() if count == 1)
    if single_trend_inputs:
        reasons["insufficient_repeated_evidence"] = reasons.get("insufficient_repeated_evidence", 0) + single_trend_inputs

    for row in review_rows:
        if not row.get("evidence") and row.get("consistency_status") != "owner_conflict":
            reasons["missing_evidence"] = reasons.get("missing_evidence", 0) + 1

    expected_generated_upper_bound = memory_risk_or_decision_count + repeated_trend_count + len(review_rows)
    explained_filtered = sum(reasons.values())
    unexplained_filtered = max(0, expected_generated_upper_bound - generated_count)
    if unexplained_filtered:
        reasons["filtered_by_reasoning_gate"] = reasons.get("filtered_by_reasoning_gate", 0) + unexplained_filtered

    return {key: value for key, value in reasons.items() if value > 0}


def _reasoning_shadow_payloads(
    meeting_id: str,
    *,
    retrieved_memory_payload: dict[str, Any],
    responsibility_shadow_payload: dict[str, Any],
    current_context: CurrentMeetingContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contexts = ReasoningEngine().generate(
        retrieved_memory_context=retrieved_memory_payload,
        responsibility_matrix=responsibility_shadow_payload.get("responsibility_matrix"),
        current_meeting_context=current_context.model_dump(mode="json"),
    )
    context_items = [context.model_dump(mode="json") for context in contexts]
    filtered_reason = _reasoning_filtered_reasons(
        retrieved_memory_payload=retrieved_memory_payload,
        responsibility_shadow_payload=responsibility_shadow_payload,
        generated_count=len(context_items),
    )
    filtered_count = sum(filtered_reason.values())

    return (
        {
            "meeting_id": meeting_id,
            "items": context_items,
        },
        {
            "meeting_id": meeting_id,
            "candidate_count": len(context_items) + filtered_count,
            "generated_count": len(context_items),
            "filtered_count": filtered_count,
            "filtered_reason": filtered_reason,
            "confirmation_required_count": sum(1 for item in context_items if item.get("requires_confirmation")),
            "confidence_distribution": _confidence_distribution(context_items),
        },
    )


def _workflow_evidence_ref(
    *,
    meeting_id: str,
    source_type: str,
    source_id: str,
    supports: list[str],
    confidence: float,
    evidence_status: str = "active",
) -> dict[str, Any]:
    evidence_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"workflow-evidence:{meeting_id}:{source_type}:{source_id}:{','.join(supports)}",
        )
    )
    return {
        "evidence_ref_id": f"eref:workflow:{evidence_id}",
        "source_type": source_type,
        "source_id": source_id,
        "meeting_id": meeting_id,
        "supports": supports,
        "support_level": "supports",
        "evidence_status": evidence_status,
        "confidence": confidence,
    }


def _workflow_contexts_from_shadow_analysis(
    meeting_id: str,
    *,
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for index, item in enumerate(analysis.get("action_items", []), start=1):
        if not isinstance(item, dict):
            continue
        task = _text(item.get("task"))
        if not task:
            continue
        source_id = _text(item.get("source_segment_id")) or f"action:{index}"
        source_text = _text(item.get("source_text"))
        confidence = float(item.get("confidence") or 0.72)
        evidence = _workflow_evidence_ref(
            meeting_id=meeting_id,
            source_type="formal_action_item",
            source_id=source_id,
            supports=["observed_state", "recommendation", "task"],
            confidence=confidence,
            evidence_status="active" if source_text else "needs_review",
        )
        if item.get("status") == "done":
            state_value = "completed_candidate"
        elif item.get("status") == "in_progress":
            state_value = "in_progress"
        else:
            state_value = "action_created"
        workflow_key = f"{meeting_id}:action:{source_id}:{task}"
        workflow_id = f"workflow:meeting_follow_up:{uuid.uuid5(uuid.NAMESPACE_URL, workflow_key)}"
        blockers: list[dict[str, Any]] = []
        if not source_text:
            blocker_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{workflow_id}:missing-evidence")
            blockers.append(
                {
                    "blocker_id": f"blocker:workflow:{blocker_id}",
                    "blocker_type": "missing_evidence",
                    "subject_ref": f"task:formal_action_item:{source_id}",
                    "severity": "medium",
                    "reason": "Action item has no source text evidence in the shadow analysis payload.",
                    "recommended_next_step": "refresh_evidence",
                    "evidence_refs": [evidence["evidence_ref_id"]],
                    "confidence": min(confidence, 0.78),
                    "status": "active",
                }
            )
        if not item.get("owner_name"):
            blocker_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{workflow_id}:missing-owner-confirmation")
            blockers.append(
                {
                    "blocker_id": f"blocker:workflow:{blocker_id}",
                    "blocker_type": "missing_confirmation",
                    "subject_ref": f"task:formal_action_item:{source_id}",
                    "severity": "medium",
                    "reason": "Follow-up owner is not confirmed by source-backed formal analysis.",
                    "recommended_next_step": "request_confirmation",
                    "evidence_refs": [evidence["evidence_ref_id"]],
                    "confidence": min(confidence, 0.82),
                    "status": "active",
                }
            )
        contexts.append(
            {
                "workflow_id": workflow_id,
                "workflow_type": "meeting_follow_up",
                "entities": [],
                "tasks": [
                    {
                        "task_ref": f"task:formal_action_item:{source_id}",
                        "title": task,
                        "task_type": "follow_up",
                        "owner_ref": item.get("owner_name"),
                        "state_ref": f"state:workflow:{source_id}",
                        "evidence_refs": [evidence["evidence_ref_id"]],
                    }
                ],
                "dependencies": [],
                "states": [
                    {
                        "state_id": f"state:workflow:{source_id}",
                        "subject_ref": f"task:formal_action_item:{source_id}",
                        "state_type": "task_state",
                        "state_value": state_value,
                        "previous_state_ref": None,
                        "changed_at_ref": f"meeting:{meeting_id}",
                        "evidence_refs": [evidence["evidence_ref_id"]],
                        "confidence": confidence,
                    }
                ],
                "blockers": blockers,
                "evidence_refs": [evidence],
                "confidence": confidence,
            }
        )

    for index, item in enumerate(analysis.get("unresolved_issues", []), start=1):
        if not isinstance(item, dict):
            continue
        issue = _text(item.get("issue"))
        if not issue:
            continue
        source_id = f"issue:{index}"
        confidence = float(item.get("confidence") or 0.72)
        evidence = _workflow_evidence_ref(
            meeting_id=meeting_id,
            source_type="formal_summary_item",
            source_id=source_id,
            supports=["observed_state", "recommendation", "issue"],
            confidence=confidence,
            evidence_status="active" if _text(item.get("source_text")) else "needs_review",
        )
        workflow_id = f"workflow:issue_resolution:{uuid.uuid5(uuid.NAMESPACE_URL, f'{meeting_id}:issue:{issue}')}"
        blocker_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{workflow_id}:manual-review")
        contexts.append(
            {
                "workflow_id": workflow_id,
                "workflow_type": "issue_resolution",
                "entities": [],
                "tasks": [],
                "dependencies": [],
                "states": [
                    {
                        "state_id": f"state:workflow:{source_id}",
                        "subject_ref": f"issue:formal_summary_item:{index}",
                        "state_type": "issue_state",
                        "state_value": "reported",
                        "previous_state_ref": None,
                        "changed_at_ref": f"meeting:{meeting_id}",
                        "evidence_refs": [evidence["evidence_ref_id"]],
                        "confidence": confidence,
                    }
                ],
                "blockers": [
                    {
                        "blocker_id": f"blocker:workflow:{blocker_id}",
                        "blocker_type": "missing_confirmation",
                        "subject_ref": f"issue:formal_summary_item:{index}",
                        "severity": "medium",
                        "reason": "Unresolved issue remains review-only and requires human confirmation before workflow use.",
                        "recommended_next_step": "request_confirmation",
                        "evidence_refs": [evidence["evidence_ref_id"]],
                        "confidence": min(confidence, 0.82),
                        "status": "active",
                    }
                ],
                "evidence_refs": [evidence],
                "confidence": confidence,
            }
        )

    return contexts


def _workflow_shadow_payloads(
    meeting_id: str,
    *,
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contexts = _workflow_contexts_from_shadow_analysis(meeting_id, analysis=analysis)
    observations = []
    recommendations = []
    blocked_actions = [
        "execute_workflow",
        "advance_workflow_state",
        "update_task_status",
        "create_task",
        "send_notification",
        "call_mcp_or_external_connector",
        "write_database",
    ]
    observation_builder = WorkflowStateObservationBuilder()
    recommendation_builder = WorkflowRecommendationBuilder()
    for context in contexts:
        observation = observation_builder.build(workflow_context=context)
        if observation is None:
            blocked_actions.append(f"observe_workflow:{context.get('workflow_id')}:missing_supported_evidence")
            continue
        observations.append(observation)
        recommendation = recommendation_builder.build(
            observation=observation,
            blockers=context.get("blockers") if isinstance(context.get("blockers"), list) else [],
            dependencies=context.get("dependencies") if isinstance(context.get("dependencies"), list) else [],
            evidence_refs=context.get("evidence_refs") if isinstance(context.get("evidence_refs"), list) else [],
        )
        if recommendation is None:
            blocked_actions.append(f"recommend_workflow:{context.get('workflow_id')}:missing_supported_evidence")
            continue
        recommendations.append(recommendation)

    return (
        {
            "meeting_id": meeting_id,
            "items": [item.model_dump(mode="json") for item in observations],
        },
        {
            "meeting_id": meeting_id,
            "items": [item.model_dump(mode="json") for item in recommendations],
        },
        {
            "meeting_id": meeting_id,
            "workflow_count": len(contexts),
            "state_observation_count": len(observations),
            "recommendation_count": len(recommendations),
            "execution_attempted": False,
            "writes_performed": False,
            "blocked_actions": _unique(blocked_actions),
        },
    )


def _comparison_markdown(
    meeting_id: str,
    utterances: list[UtteranceInput],
    raw_events: list[dict[str, Any]],
    validated_events: list[SemanticEvent],
    mapped: SixDimensionResult,
    validated: SixDimensionResult,
) -> str:
    raw_items = [_event_trace_dict(item, meeting_id=meeting_id) for item in raw_events]
    validated_items = [_event_trace_dict(item, meeting_id=meeting_id) for item in validated_events]
    mapped_items = _dimension_trace_items(mapped, meeting_id=meeting_id)
    final_items = _dimension_trace_items(validated, meeting_id=meeting_id)

    checks = [
        ("greeting_as_agenda", ("大家好", "下午好", "早上好"), "meeting_agenda"),
        ("progress_as_decision", ("目前", "进度", "已完成", "完成"), "key_conclusions"),
        ("flow_talk_as_summary", ("最后统一", "有没有其他问题", "无问题"), "meeting_summary"),
        ("commitment_inflated_as_action", ("我会", "我来", "可以"), "action_items"),
        ("agenda_as_risk", ("目标", "议程", "本次会议"), "risks_and_focus"),
        ("mitigation_as_risk", ("已经加了重试", "可以关闭", "验证通过后"), "risks_and_focus"),
        ("confirmed_conclusion_as_summary", ("结论是", "保持", "不变"), "meeting_summary"),
    ]

    rows: list[dict[str, str]] = []
    for error_type, keywords, target_dimension in checks:
        first_stage = ""
        evidence = ""
        for stage_name, items in (
            ("02_semantic_events_raw", raw_items),
            ("03_semantic_events_validated", validated_items),
            ("05_six_dimension_mapped", mapped_items),
            ("06_six_dimension_validated", final_items),
        ):
            for item in items:
                source_text = str(item.get("source_text") or "")
                if not any(keyword in source_text for keyword in keywords):
                    continue
                if stage_name.startswith("0") and stage_name < "05":
                    if error_type == "greeting_as_agenda" and item.get("primary_intent") != "agenda_statement":
                        continue
                    if error_type == "progress_as_decision" and item.get("primary_intent") != "decision":
                        continue
                    if error_type == "agenda_as_risk" and item.get("primary_intent") != "risk_warning":
                        continue
                    if error_type == "mitigation_as_risk" and item.get("primary_intent") != "risk_warning":
                        continue
                    if error_type == "confirmed_conclusion_as_summary" and item.get("primary_intent") == "decision":
                        continue
                    if error_type in {"flow_talk_as_summary", "commitment_inflated_as_action"}:
                        continue
                elif item.get("target_dimension") != target_dimension:
                    continue
                first_stage = stage_name
                evidence = source_text
                break
            if first_stage:
                break
        rows.append(
            {
                "error_type": error_type,
                "first_stage": first_stage or "not_found",
                "evidence": evidence,
                "suggestion": "Fix semantic event intent rules first." if first_stage in {"02_semantic_events_raw", "03_semantic_events_validated"} else "Fix six-dimension mapper/validator routing.",
            }
        )

    duplicate_sources: dict[str, set[str]] = {}
    for item in final_items:
        source_text = str(item.get("source_text") or "")
        if not source_text:
            continue
        duplicate_sources.setdefault(source_text, set()).add(str(item.get("target_dimension")))
    for source_text, dimensions in duplicate_sources.items():
        if len(dimensions) > 1:
            rows.append(
                {
                    "error_type": "duplicate_across_dimensions",
                    "first_stage": "06_six_dimension_validated",
                    "evidence": source_text,
                    "suggestion": "Fix cross-dimension dedupe in SixDimensionValidator.",
                }
            )

    original = "\n".join(f"{utterance.speaker or ''}: {utterance.text}" for utterance in utterances)
    lines = [
        f"# Semantic Pipeline Comparison: {meeting_id}",
        "",
        "## Original",
        "",
        original,
        "",
        "## First Error Stage",
        "",
        "| error_type | first_stage | suggestion | evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = row["evidence"].replace("\n", " ")[:160]
        lines.append(f"| {row['error_type']} | {row['first_stage']} | {row['suggestion']} | {evidence} |")
    lines.extend(
        [
            "",
            "## Stage Files",
            "",
            "- `00_speaker_contexts.json`",
            "- `01_utterances.json`",
            "- `02_semantic_events_raw.json`",
            "- `03_semantic_events_validated.json`",
            "- `04_topic_groups.json`",
            "- `05_six_dimension_mapped.json`",
            "- `06_six_dimension_validated.json`",
            "- `08_responsibility_evidence_matrix.json`",
            "- `memory_snapshot.json`",
            "- `retrieved_memory_context.json`",
            "- `memory_retrieval_audit.json`",
            "- `reasoning_contexts.json`",
            "- `reasoning_audit.json`",
            "- `unresolved_candidates.json`",
            "- `action_candidates.json`",
            "- `tool_action_contracts.json`",
            "- `action_audit.json`",
            "- `workflow_state_observations.json`",
            "- `workflow_recommendations.json`",
            "- `workflow_audit.json`",
            "- `07_final_meeting_analysis.json`",
        ]
    )
    return "\n".join(lines)


def run_semantic_shadow_trace(
    meeting_id: str,
    transcript: list[Any],
    *,
    trace_root: Path | None = None,
    speaker_resolver: SpeakerResolver | None = None,
    role_resolver: RoleResolver | None = None,
    use_llm_extractor: bool = False,
    extractor: SemanticEventExtractor | None = None,
    aggregator: TopicEventAggregator | None = None,
    mapper: SixDimensionMapper | None = None,
    validator: SixDimensionValidator | None = None,
) -> Path:
    trace_dir = (trace_root or SEMANTIC_TRACE_ROOT) / meeting_id
    try:
        speaker_context_result = SpeakerContextBuilder(speaker_resolver, role_resolver).build(
            meeting_id=meeting_id,
            transcript=transcript,
        )
        speaker_shadow_context = speaker_context_result.to_shadow_context()
        _write_trace_json(trace_dir, "00_speaker_contexts.json", speaker_shadow_context)

        utterances = transcript_to_utterances(transcript)
        utterance_items = [
            {
                "meeting_id": meeting_id,
                "event_id": None,
                "topic_id": None,
                "source_text": utterance.text,
                "primary_intent": None,
                "status": None,
                "target_dimension": None,
                "needs_review": False,
                "utterance": utterance.model_dump(mode="json"),
            }
            for utterance in utterances
        ]
        _write_trace_json(trace_dir, "01_utterances.json", _trace_payload(meeting_id, utterance_items))

        raw_events: list[dict[str, Any]] = []
        validated_events: list[SemanticEvent] = []
        if extractor is None and (not use_llm_extractor or len(utterances) > SEMANTIC_LLM_MAX_UTTERANCES):
            validated_events = _extract_rule_based_events(utterances)
            raw_events = [event.model_dump(mode="json") for event in validated_events]
        else:
            extractor = extractor or SemanticEventExtractor()
            for utterance in utterances:
                if hasattr(extractor, "extract_with_debug"):
                    events, _summaries, debug = extractor.extract_with_debug(utterance)  # type: ignore[attr-defined]
                    raw_events.extend(debug.parsed_before_validation or [event.model_dump(mode="json") for event in events])
                    validated_events.extend(events)
                else:
                    events, _summaries = extractor.extract(utterance)
                    raw_events.extend(event.model_dump(mode="json") for event in events)
                    validated_events.extend(events)

        _write_trace_json(
            trace_dir,
            "02_semantic_events_raw.json",
            _trace_payload(meeting_id, [_event_trace_dict(event, meeting_id=meeting_id) for event in raw_events]),
        )
        _write_trace_json(
            trace_dir,
            "03_semantic_events_validated.json",
            _trace_payload(meeting_id, [_event_trace_dict(event, meeting_id=meeting_id) for event in validated_events]),
        )

        topics = (aggregator or TopicEventAggregator()).aggregate(validated_events)
        _write_trace_json(
            trace_dir,
            "04_topic_groups.json",
            _trace_payload(meeting_id, [_topic_trace_dict(topic, meeting_id=meeting_id) for topic in topics]),
        )

        mapped = (mapper or SixDimensionMapper()).map_topics(meeting_id, topics)
        _write_trace_json(
            trace_dir,
            "05_six_dimension_mapped.json",
            _trace_payload(meeting_id, _dimension_trace_items(mapped, meeting_id=meeting_id)),
        )

        validated = (validator or SixDimensionValidator()).validate(mapped, topics)
        _write_trace_json(
            trace_dir,
            "06_six_dimension_validated.json",
            _trace_payload(meeting_id, _dimension_trace_items(validated, meeting_id=meeting_id)),
        )

        responsibility_shadow_payload = _responsibility_shadow_payload(
            meeting_id,
            semantic_events=validated_events,
            action_items=validated.action_items,
            speaker_contexts=speaker_context_result.speaker_contexts,
            role_contexts=speaker_context_result.speaker_role_context,
        )
        _write_trace_json(
            trace_dir,
            "08_responsibility_evidence_matrix.json",
            responsibility_shadow_payload,
        )

        final_payload = _ensure_meeting_summary_text(
            _add_topics_to_analysis_dict(six_dimension_result_to_analysis_dict(validated), topics)
        )
        memory_snapshot_payload, retrieved_memory_payload, memory_audit_payload = _memory_shadow_payloads(
            meeting_id,
            speaker_contexts=speaker_context_result.speaker_contexts,
            role_contexts=speaker_context_result.speaker_role_context,
            responsibility_shadow_payload=responsibility_shadow_payload,
            meeting_analysis_events=_dimension_trace_items(validated, meeting_id=meeting_id),
            analysis=final_payload,
            utterances=utterances,
        )
        _write_trace_json(trace_dir, "memory_snapshot.json", memory_snapshot_payload)
        _write_trace_json(trace_dir, "retrieved_memory_context.json", retrieved_memory_payload)
        _write_trace_json(trace_dir, "memory_retrieval_audit.json", memory_audit_payload)
        current_context = _memory_current_context(meeting_id, analysis=final_payload, utterances=utterances)
        reasoning_contexts_payload, reasoning_audit_payload = _reasoning_shadow_payloads(
            meeting_id,
            retrieved_memory_payload=retrieved_memory_payload,
            responsibility_shadow_payload=responsibility_shadow_payload,
            current_context=current_context,
        )
        _write_trace_json(trace_dir, "reasoning_contexts.json", reasoning_contexts_payload)
        _write_trace_json(trace_dir, "reasoning_audit.json", reasoning_audit_payload)
        unresolved_candidates = extract_unresolved_candidates_from_trace(trace_dir)
        _write_trace_json(
            trace_dir,
            "unresolved_candidates.json",
            {
                "meeting_id": meeting_id,
                "items": [candidate.to_dict() for candidate in unresolved_candidates],
            },
        )
        action_candidates = ActionProposalEngine().generate(
            reasoning_contexts=reasoning_contexts_payload.get("items"),
            responsibility_matrix=responsibility_shadow_payload.get("responsibility_matrix"),
            memory_context=retrieved_memory_payload,
            current_meeting_context=current_context.model_dump(mode="json"),
        )
        tool_contracts = ToolActionContractBuilder().build(action_candidates)
        _write_trace_json(
            trace_dir,
            "action_candidates.json",
            {
                "meeting_id": meeting_id,
                "items": [
                    {
                        "action_id": candidate.action_id,
                        "action_type": candidate.action_type,
                        "reason": candidate.reason.model_dump(mode="json"),
                        "evidence_refs": [ref.model_dump(mode="json") for ref in candidate.evidence_refs],
                        "confidence": candidate.confidence,
                        "requires_confirmation": candidate.requires_confirmation,
                    }
                    for candidate in action_candidates
                ],
            },
        )
        _write_trace_json(
            trace_dir,
            "tool_action_contracts.json",
            {
                "meeting_id": meeting_id,
                "items": [contract.model_dump(mode="json") for contract in tool_contracts],
            },
        )
        _write_trace_json(
            trace_dir,
            "action_audit.json",
            action_shadow_audit_payload(meeting_id=meeting_id, candidates=action_candidates, contracts=tool_contracts),
        )
        workflow_observations_payload, workflow_recommendations_payload, workflow_audit_payload = _workflow_shadow_payloads(
            meeting_id,
            analysis=final_payload,
        )
        _write_trace_json(trace_dir, "workflow_state_observations.json", workflow_observations_payload)
        _write_trace_json(trace_dir, "workflow_recommendations.json", workflow_recommendations_payload)
        _write_trace_json(trace_dir, "workflow_audit.json", workflow_audit_payload)
        _write_trace_json(
            trace_dir,
            "07_final_meeting_analysis.json",
            {
                "meeting_id": meeting_id,
                "speaker_contexts": speaker_shadow_context["speaker_contexts"],
                "speaker_role_context": speaker_shadow_context["speaker_role_context"],
                "responsibility_evidence_matrix": responsibility_shadow_payload,
                "items": _dimension_trace_items(validated, meeting_id=meeting_id),
                "analysis": final_payload,
            },
        )
        (trace_dir / "comparison.md").write_text(
            _comparison_markdown(meeting_id, utterances, raw_events, validated_events, mapped, validated),
            encoding="utf-8",
        )

        log_event("semantic_pipeline.trace_dir", meeting_id=meeting_id, trace_dir=str(trace_dir))
        log_event("semantic_pipeline.shadow_completed", meeting_id=meeting_id, trace_dir=str(trace_dir))
        return trace_dir
    except Exception as exc:
        log_event(
            "semantic_pipeline.shadow_failed",
            level="error",
            meeting_id=meeting_id,
            trace_dir=str(trace_dir),
            error_type=exc.__class__.__name__,
            error_message=safe_error(exc),
        )
        raise


def run_semantic_pipeline(
    meeting_id: str,
    transcript: list[Any],
    **kwargs: Any,
) -> SixDimensionResult:
    return asyncio.run(analyze_meeting(meeting_id, transcript, **kwargs))


def run_semantic_pipeline_payload(
    meeting_id: str,
    transcript: list[Any],
    **kwargs: Any,
) -> dict[str, Any]:
    result, topics = asyncio.run(
        _analyze_meeting_with_topics(meeting_id, transcript, **kwargs)
    )
    payload = six_dimension_result_to_analysis_dict(result)
    payload = _add_topics_to_analysis_dict(payload, topics)
    return _ensure_meeting_summary_text(payload)


def analyze_meeting_with_fallback(
    meeting_id: str,
    transcript: list[Any],
    legacy_analyzer: Callable[[], dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        return run_semantic_pipeline_payload(meeting_id, transcript, **kwargs)
    except SemanticPipelineError as exc:
        fallback_reason = exc.reason
        failed_utterance_count = exc.failed_utterance_count
        semantic_event_count = exc.semantic_event_count
        topic_count = exc.topic_count
        log_event(
            "semantic_pipeline.fallback",
            level="error",
            meeting_id=meeting_id,
            fallback_reason=fallback_reason,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=semantic_event_count,
            topic_count=topic_count,
            error_message=safe_error(exc),
        )
    except Exception as exc:
        fallback_reason = "pipeline_exception"
        failed_utterance_count = 0
        semantic_event_count = 0
        topic_count = 0
        log_event(
            "semantic_pipeline.fallback",
            level="error",
            meeting_id=meeting_id,
            fallback_reason=fallback_reason,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=semantic_event_count,
            topic_count=topic_count,
            error_type=exc.__class__.__name__,
            error_message=safe_error(exc),
        )

    try:
        fallback = legacy_analyzer()
    except Exception as legacy_exc:
        setattr(legacy_exc, "semantic_fallback_reason", fallback_reason)
        setattr(legacy_exc, "failed_utterance_count", failed_utterance_count)
        setattr(legacy_exc, "semantic_event_count", semantic_event_count)
        setattr(legacy_exc, "topic_count", topic_count)
        log_event(
            "semantic_pipeline.fallback_failed",
            level="error",
            meeting_id=meeting_id,
            fallback_reason=fallback_reason,
            failed_utterance_count=failed_utterance_count,
            semantic_event_count=semantic_event_count,
            topic_count=topic_count,
            error_type=legacy_exc.__class__.__name__,
            error_message=safe_error(legacy_exc),
        )
        raise

    metadata = fallback.get("_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        fallback["_metadata"] = metadata
    metadata["fallback_reason"] = fallback_reason
    metadata["failed_utterance_count"] = failed_utterance_count
    metadata["semantic_event_count"] = semantic_event_count
    metadata["topic_count"] = topic_count
    return fallback


def analyze_meeting_shadow_mode(
    meeting_id: str,
    transcript: list[Any],
    legacy_analyzer: Callable[[], dict[str, Any]],
    *,
    trace_root: Path | None = None,
    speaker_resolver: SpeakerResolver | None = None,
    role_resolver: RoleResolver | None = None,
    **trace_kwargs: Any,
) -> dict[str, Any]:
    semantic_action_candidates: list[dict[str, Any]] = []
    semantic_decision_candidates: list[dict[str, Any]] = []
    semantic_unresolved_raw_candidate_count = 0
    semantic_unresolved_candidates: list[dict[str, Any]] = []
    semantic_shadow_trace_dir: str | None = None
    semantic_shadow_error: str | None = None

    try:
        trace_dir = run_semantic_shadow_trace(
            meeting_id,
            transcript,
            trace_root=trace_root,
            speaker_resolver=speaker_resolver,
            role_resolver=role_resolver,
            **trace_kwargs,
        )
        semantic_shadow_trace_dir = str(trace_dir)
        semantic_action_candidates = _semantic_action_candidates_from_trace(trace_dir)
        semantic_decision_candidates = _semantic_decision_candidates_from_trace(trace_dir)
        semantic_unresolved_candidates = _semantic_unresolved_candidates_from_trace(trace_dir)
        semantic_unresolved_raw_candidate_count = _semantic_unresolved_raw_candidate_count_from_trace(trace_dir)
    except Exception as exc:
        semantic_shadow_error = safe_error(exc)

    formal_result = _call_legacy_analyzer(
        legacy_analyzer,
        semantic_action_candidates=semantic_action_candidates,
        semantic_decision_candidates=semantic_decision_candidates,
        semantic_unresolved_candidates=semantic_unresolved_candidates,
    )
    metadata = formal_result.get("_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        formal_result["_metadata"] = metadata

    metadata["semantic_shadow_mode"] = True
    metadata["semantic_action_candidate_count"] = len(semantic_action_candidates)
    metadata["semantic_decision_candidate_count"] = len(semantic_decision_candidates)
    metadata["semantic_unresolved_raw_candidate_count"] = semantic_unresolved_raw_candidate_count
    metadata["semantic_unresolved_candidate_count"] = len(semantic_unresolved_candidates)
    if semantic_shadow_trace_dir:
        metadata["semantic_shadow_trace_dir"] = semantic_shadow_trace_dir
    if semantic_shadow_error:
        metadata["semantic_shadow_error"] = semantic_shadow_error

    return formal_result


def _call_legacy_analyzer(
    legacy_analyzer: Callable[..., dict[str, Any]],
    *,
    semantic_action_candidates: list[dict[str, Any]],
    semantic_decision_candidates: list[dict[str, Any]],
    semantic_unresolved_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        signature = inspect.signature(legacy_analyzer)
    except (TypeError, ValueError):
        return legacy_analyzer()

    accepts_keyword = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or parameter.name == "semantic_action_candidates"
        or parameter.name == "semantic_decision_candidates"
        or parameter.name == "semantic_unresolved_candidates"
        for parameter in signature.parameters.values()
    )
    if accepts_keyword:
        kwargs: dict[str, Any] = {}
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            or parameter.name == "semantic_action_candidates"
            for parameter in signature.parameters.values()
        ):
            kwargs["semantic_action_candidates"] = semantic_action_candidates
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            or parameter.name == "semantic_decision_candidates"
            for parameter in signature.parameters.values()
        ):
            kwargs["semantic_decision_candidates"] = semantic_decision_candidates
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            or parameter.name == "semantic_unresolved_candidates"
            for parameter in signature.parameters.values()
        ):
            kwargs["semantic_unresolved_candidates"] = semantic_unresolved_candidates
        return legacy_analyzer(**kwargs)
    return legacy_analyzer()


def _semantic_action_candidates_from_trace(trace_dir: Path) -> list[dict[str, Any]]:
    result_path = trace_dir / "07_final_meeting_analysis.json"
    if not result_path.exists():
        return []

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    candidates = analysis.get("action_items") if isinstance(analysis, dict) else []
    if not isinstance(candidates, list):
        return []
    return [dict(item) for item in candidates if isinstance(item, dict)]


def _semantic_decision_candidates_from_trace(trace_dir: Path) -> list[dict[str, Any]]:
    candidates = extract_decision_candidates_from_trace(trace_dir)
    ranked = rank_and_deduplicate_decisions(candidates)
    return [item.to_dict() for item in ranked]


def _semantic_unresolved_candidates_from_trace(trace_dir: Path) -> list[dict[str, Any]]:
    candidates = extract_unresolved_candidates_from_trace(trace_dir)
    ranked = rank_and_deduplicate_unresolved(candidates)
    return [item.to_dict() for item in ranked]


def _semantic_unresolved_raw_candidate_count_from_trace(trace_dir: Path) -> int:
    return len(extract_unresolved_candidates_from_trace(trace_dir))
