from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.observability import log_event, safe_error
from app.semantic_event_extractor import SemanticEventExtractor
from app.semantic_event_schema import SemanticEvent, UtteranceInput
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


SEMANTIC_PIPELINE_MODEL_NAME = "semantic-events+rules"
SEMANTIC_PIPELINE_PROMPT_VERSION = "semantic-event-pipeline-v1"
SEMANTIC_LLM_MAX_UTTERANCES = 8
PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


def _rule_intent(text: str, index: int) -> str:
    if _contains_any(text, {"无问题", "无疑问", "没有其他问题"}):
        return "non_event"
    if index == 0 or _contains_any(text, {"议程", "目标", "今天我们", "首先", "本次会议"}):
        return "agenda_statement"
    if _contains_any(text, {"疑问", "没有明确", "未明确", "需要补充", "缺失", "遗漏", "有没有"}):
        return "open_issue"
    if _contains_any(text, {"决定", "确认", "同意", "明确", "采纳", "锁定", "禁止", "不再", "必须", "砍掉", "统一"}):
        return "decision"
    if _contains_any(text, {"风险", "隐患", "压力", "超时", "回滚", "故障", "高风险", "压缩", "偏紧"}):
        return "risk_warning"
    if _contains_any(text, {"我会", "负责", "启动", "更新", "补充", "同步", "推进", "落地", "编写"}):
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


def _extract_rule_based_events(utterances: list[UtteranceInput]) -> list[SemanticEvent]:
    return [_rule_event(utterance, index=index) for index, utterance in enumerate(utterances)]


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
    action_items = [
        {
            "task": item.content,
            "owner_name": item.owner,
            "deadline": item.deadline,
            "priority": _priority(item.priority),
            "status": _status_for_action(item.status),
            "source_text": _source_text(item),
            "source_segment_id": _first_segment_id(item),
            "confidence": item.confidence,
        }
        for item in result.action_items
    ]
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
            "- `01_utterances.json`",
            "- `02_semantic_events_raw.json`",
            "- `03_semantic_events_validated.json`",
            "- `04_topic_groups.json`",
            "- `05_six_dimension_mapped.json`",
            "- `06_six_dimension_validated.json`",
            "- `07_final_meeting_analysis.json`",
        ]
    )
    return "\n".join(lines)


def run_semantic_shadow_trace(
    meeting_id: str,
    transcript: list[Any],
    *,
    trace_root: Path | None = None,
    use_llm_extractor: bool = False,
    extractor: SemanticEventExtractor | None = None,
    aggregator: TopicEventAggregator | None = None,
    mapper: SixDimensionMapper | None = None,
    validator: SixDimensionValidator | None = None,
) -> Path:
    trace_dir = (trace_root or SEMANTIC_TRACE_ROOT) / meeting_id
    try:
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

        final_payload = _ensure_meeting_summary_text(
            _add_topics_to_analysis_dict(six_dimension_result_to_analysis_dict(validated), topics)
        )
        _write_trace_json(
            trace_dir,
            "07_final_meeting_analysis.json",
            {
                "meeting_id": meeting_id,
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
    **trace_kwargs: Any,
) -> dict[str, Any]:
    formal_result = legacy_analyzer()
    metadata = formal_result.get("_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        formal_result["_metadata"] = metadata

    try:
        trace_dir = run_semantic_shadow_trace(
            meeting_id,
            transcript,
            trace_root=trace_root,
            **trace_kwargs,
        )
        metadata["semantic_shadow_mode"] = True
        metadata["semantic_shadow_trace_dir"] = str(trace_dir)
    except Exception as exc:
        metadata["semantic_shadow_mode"] = True
        metadata["semantic_shadow_error"] = safe_error(exc)

    return formal_result
