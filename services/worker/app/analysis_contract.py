from __future__ import annotations

from typing import Any
from uuid import UUID

from app.meeting_analysis_schema import (
    KeyConclusion,
    MeetingActionItem,
    MeetingAgendaItem,
    MeetingAnalysisMetadata,
    MeetingAnalysisSchema,
    RiskAndFocus,
    TopicChunk,
    UnresolvedIssue,
)


ANALYSIS_SCHEMA_VERSION = "meeting-analysis-v1"
DEFAULT_PROMPT_VERSION = "meeting-analyst-v1"
EMPTY_ANALYSIS_ERROR_TYPE = "empty_analysis_result"
OUTPUT_CONTRACT_ALIAS_MAP = {
    "title_candidate": "meeting_title_candidate",
    "agenda": "meeting_agenda",
    "summary": "meeting_summary",
    "risks_and_concerns": "risks_and_focus",
}
STRING_ITEM_CONTRACT_MAP = {
    "key_conclusions": "conclusion",
    "unresolved_issues": "issue",
}
CONTENT_ITEM_CONTRACT_MAP = {
    "action_items": "task",
    "risks_and_focus": "risk",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _confidence(value: object, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def persistence_source_segment_id(value: object) -> str | None:
    for part in str(value or "").split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            UUID(candidate)
        except ValueError:
            continue
        return candidate
    return None


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_items(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in _list(value) if isinstance(item, dict)]


def canonicalize_meeting_analysis_aliases(
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    canonical = dict(raw_result)
    for alias, target in OUTPUT_CONTRACT_ALIAS_MAP.items():
        if target not in canonical and alias in canonical:
            canonical[target] = canonical[alias]
        canonical.pop(alias, None)
    return canonical


def adapt_meeting_analysis_item_shapes(
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    adapted = dict(raw_result)
    for field, target_key in STRING_ITEM_CONTRACT_MAP.items():
        if field not in adapted:
            continue
        items: list[Any] = []
        for item in _list(adapted.get(field)):
            text = _text(item)
            if isinstance(item, str) and text:
                items.append({target_key: text, "source_text": text})
            elif isinstance(item, dict):
                shaped = dict(item)
                if "source_text" not in shaped and "source" not in shaped and _text(shaped.get(target_key)):
                    shaped["source_text"] = _text(shaped.get(target_key))
                items.append(shaped)
        adapted[field] = items

    for field, target_key in CONTENT_ITEM_CONTRACT_MAP.items():
        if field not in adapted:
            continue
        items = []
        for item in _list(adapted.get(field)):
            text = _text(item)
            if isinstance(item, str) and text:
                items.append({target_key: text, "source_text": text})
                continue
            if not isinstance(item, dict):
                continue
            shaped = dict(item)
            if target_key not in shaped and _text(shaped.get("content")):
                content = _text(shaped.get("content"))
                shaped[target_key] = content
                if "source_text" not in shaped:
                    shaped["source_text"] = content
            elif "source_text" not in shaped and "source" not in shaped and _text(shaped.get(target_key)):
                shaped["source_text"] = _text(shaped.get(target_key))
            items.append(shaped)
        adapted[field] = items
    return adapted


class EmptyAnalysisResultError(ValueError):
    def __init__(self, message: str = "empty_analysis_result: invalid_model_output_contract") -> None:
        super().__init__(message)
        self.error_type = EMPTY_ANALYSIS_ERROR_TYPE


def _has_text(value: object) -> bool:
    return bool(str(value or "").strip())


def is_empty_analysis_result(value: object) -> bool:
    if isinstance(value, MeetingAnalysisSchema):
        return (
            not _has_text(value.meeting_summary)
            and not value.meeting_agenda
            and not value.key_conclusions
            and not value.action_items
            and not value.unresolved_issues
            and not value.risks_and_focus
        )
    if not isinstance(value, dict):
        return True
    return (
        not _has_text(value.get("meeting_summary") or value.get("overview") or value.get("summary"))
        and not _list(value.get("meeting_agenda") or value.get("agenda"))
        and not _list(value.get("key_conclusions") or value.get("decisions"))
        and not _list(value.get("action_items"))
        and not _list(value.get("unresolved_issues") or value.get("open_questions"))
        and not _list(value.get("risks_and_focus") or value.get("risks"))
    )


def ensure_non_empty_analysis_result(value: object) -> None:
    if is_empty_analysis_result(value):
        raise EmptyAnalysisResultError()


MEETING_TYPE_VALUES = {
    "project_weekly",
    "progress_sync",
    "requirement_review",
    "solution_review",
    "project_retrospective",
    "risk_review",
    "release_review",
    "customer_communication",
    "training",
    "interview",
    "one_on_one",
    "other",
}


def _meeting_type(value: object) -> str:
    text = _text(value)
    return text if text in MEETING_TYPE_VALUES else "other"


def _text_list(value: object) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _agenda_items(value: object) -> list[MeetingAgendaItem]:
    items: list[MeetingAgendaItem] = []
    for index, item in enumerate(_list(value), start=1):
        if isinstance(item, str):
            text = _text(item)
            source_segment_ids: list[str] = []
        elif isinstance(item, dict):
            text = _text(item.get("item") or item.get("title") or item.get("summary"))
            raw_ids = item.get("source_segment_ids")
            source_segment_ids = [str(raw_id) for raw_id in raw_ids] if isinstance(raw_ids, list) else []
        else:
            continue
        if text:
            items.append(MeetingAgendaItem(item=text, order=index, source_segment_ids=source_segment_ids))
    return items


def _key_conclusions(value: object) -> list[KeyConclusion]:
    items: list[KeyConclusion] = []
    for item in _dict_items(value):
        conclusion = _text(item.get("conclusion") or item.get("decision"))
        source_text = _text(item.get("source_text") or item.get("source"))
        if conclusion:
            items.append(
                KeyConclusion(
                    conclusion=conclusion,
                    source_text=source_text,
                    confidence=_confidence(item.get("confidence")),
                )
            )
    return items


def _action_items(value: object) -> list[MeetingActionItem]:
    items: list[MeetingActionItem] = []
    for item in _dict_items(value):
        task = _text(item.get("task") or item.get("item"))
        if not task:
            continue
        priority = _text(item.get("priority") or "medium")
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        status = _text(item.get("status") or "open")
        if status not in {"open", "in_progress", "done"}:
            status = "open"
        items.append(
            MeetingActionItem(
                owner_name=_text(item.get("owner_name") or item.get("owner")) or None,
                task=task,
                deadline=_text(item.get("deadline") or item.get("due_date")) or None,
                priority=priority,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                source_text=_text(item.get("source_text") or item.get("source")),
                source_segment_id=_text(item.get("source_segment_id")) or None,
                confidence=_confidence(item.get("confidence")),
            )
        )
    return items


def _unresolved_issues(value: object) -> list[UnresolvedIssue]:
    items: list[UnresolvedIssue] = []
    for item in _dict_items(value):
        issue = _text(item.get("issue") or item.get("question"))
        if issue:
            items.append(
                UnresolvedIssue(
                    issue=issue,
                    reason=_text(item.get("reason")),
                    blocker=_text(item.get("blocker")),
                    source_text=_text(item.get("source_text") or item.get("source")),
                    confidence=_confidence(item.get("confidence")),
                )
            )
    return items


def _risks(value: object) -> list[RiskAndFocus]:
    items: list[RiskAndFocus] = []
    for item in _dict_items(value):
        risk = _text(item.get("risk"))
        if risk:
            items.append(
                RiskAndFocus(
                    risk=risk,
                    impact=_text(item.get("impact")),
                    focus_area=_text(item.get("focus_area")),
                    mitigation=_text(item.get("mitigation")),
                    source_text=_text(item.get("source_text") or item.get("source")),
                    confidence=_confidence(item.get("confidence")),
                )
            )
    return items


def _topics(value: object) -> list[TopicChunk]:
    topics: list[TopicChunk] = []
    for item in _dict_items(value):
        title = _text(item.get("title") or item.get("summary"))
        summary = _text(item.get("summary") or item.get("title"))
        if not title and not summary:
            continue
        topics.append(
            TopicChunk(
                title=title or summary[:40],
                summary=summary or title,
                start_time=float(item.get("start_time") or 0.0),
                end_time=float(item.get("end_time") or item.get("start_time") or 0.0),
                related_segment_ids=[
                    str(segment_id)
                    for segment_id in item.get("related_segment_ids", [])
                    if segment_id is not None
                ]
                if isinstance(item.get("related_segment_ids"), list)
                else [],
                speakers=[str(speaker) for speaker in item.get("speakers", []) if speaker is not None]
                if isinstance(item.get("speakers"), list)
                else [],
            )
        )
    return topics


def _confidence_score(analysis: MeetingAnalysisSchema) -> float:
    values = [
        item.confidence
        for item in [
            *analysis.key_conclusions,
            *analysis.action_items,
            *analysis.unresolved_issues,
            *analysis.risks_and_focus,
        ]
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def normalize_meeting_analysis_result(
    raw_result: dict[str, Any],
    *,
    model_name: str = "",
    prompt_version: str | None = None,
    rag_chunk_ids: list[str] | None = None,
) -> MeetingAnalysisSchema:
    """
    Authoritative boundary from model/validator dict output to trusted business schema.
    The model output must pass through this function before persistence.
    """
    raw_result = adapt_meeting_analysis_item_shapes(
        canonicalize_meeting_analysis_aliases(raw_result)
    )

    raw_metadata = raw_result.get("_metadata") if isinstance(raw_result.get("_metadata"), dict) else {}
    resolved_prompt_version = (
        prompt_version
        or raw_metadata.get("prompt_version")
        or DEFAULT_PROMPT_VERSION
    )
    resolved_rag_chunk_ids = (
        rag_chunk_ids
        if rag_chunk_ids is not None
        else raw_metadata.get("rag_chunk_ids")
    )
    if not isinstance(resolved_rag_chunk_ids, list):
        resolved_rag_chunk_ids = []

    analysis = MeetingAnalysisSchema(
        meeting_title=_text(raw_result.get("meeting_title")),
        meeting_type=_meeting_type(raw_result.get("meeting_type")),
        meeting_type_confidence=_confidence(raw_result.get("meeting_type_confidence"), default=0.0),
        meeting_title_candidate=_text(raw_result.get("meeting_title_candidate")),
        title_basis=_text_list(raw_result.get("title_basis")),
        meeting_agenda=_agenda_items(raw_result.get("meeting_agenda") or raw_result.get("agenda")),
        meeting_summary=_text(raw_result.get("meeting_summary") or raw_result.get("summary")),
        key_conclusions=_key_conclusions(raw_result.get("key_conclusions") or raw_result.get("decisions")),
        action_items=_action_items(raw_result.get("action_items")),
        unresolved_issues=_unresolved_issues(raw_result.get("unresolved_issues") or raw_result.get("open_questions")),
        risks_and_focus=_risks(raw_result.get("risks_and_focus") or raw_result.get("risks")),
        topics=_topics(raw_result.get("topics")),
        metadata=MeetingAnalysisMetadata(
            schema_version=ANALYSIS_SCHEMA_VERSION,
            model_name=model_name,
            prompt_version=str(resolved_prompt_version),
            rag_chunk_ids=[str(chunk_id) for chunk_id in resolved_rag_chunk_ids],
            rag_dataset_version=_text(raw_metadata.get("rag_dataset_version")) or None,
            rag_chunk_schema_version=_text(raw_metadata.get("rag_chunk_schema_version")) or None,
            rag_collection_name=_text(raw_metadata.get("rag_collection_name")) or None,
            rag_embedding_model=_text(raw_metadata.get("rag_embedding_model")) or None,
            retrieved_chunk_ids=[
                str(chunk_id)
                for chunk_id in (
                    raw_metadata.get("retrieved_chunk_ids")
                    if isinstance(
                        raw_metadata.get("retrieved_chunk_ids"),
                        list,
                    )
                    else resolved_rag_chunk_ids
                )
            ],
            retrieval_version=_text(raw_metadata.get("retrieval_version")) or None,
            scenario_taxonomy_version=_text(
                raw_metadata.get("scenario_taxonomy_version")
            )
            or None,
            rag_retrieval_strategy=_text(
                raw_metadata.get(
                    "rag_retrieval_strategy"
                )
            ) or None,
            rag_retrieval_buckets=(
                raw_metadata.get(
                    "rag_retrieval_buckets"
                )
                if isinstance(
                    raw_metadata.get(
                        "rag_retrieval_buckets"
                    ),
                    dict,
                )
                else {}
            ),
            rag_routed_meeting_type=_text(
                raw_metadata.get(
                    "rag_routed_meeting_type"
                )
            ) or None,
            rag_routed_scenario=_text(
                raw_metadata.get(
                    "rag_routed_scenario"
                )
            ) or None,
            rag_fallback_reason=_text(
                raw_metadata.get(
                    "rag_fallback_reason"
                )
            ) or None,
            result_source=_text(raw_metadata.get("result_source")) or None,
            confidence_score=0.0,
        ),
    )
    analysis.metadata.confidence_score = _confidence_score(analysis)
    return analysis


def analysis_to_persistence_payload(analysis: MeetingAnalysisSchema) -> dict[str, Any]:
    """
    Single mapping from trusted business schema to current DB-compatible payload.
    Legacy fields are kept only for backward compatibility.
    """

    agenda = [item.model_dump() for item in analysis.meeting_agenda]
    topics = [item.model_dump() for item in analysis.topics]
    conclusions = [item.model_dump() for item in analysis.key_conclusions]
    actions = [item.model_dump() for item in analysis.action_items]
    for item in actions:
        item["source_segment_id"] = persistence_source_segment_id(item.get("source_segment_id"))
    issues = [item.model_dump() for item in analysis.unresolved_issues]
    risks = [item.model_dump() for item in analysis.risks_and_focus]

    return {
        "overview": analysis.meeting_summary,
        "meeting_title": analysis.meeting_title,
        "meeting_type": analysis.meeting_type,
        "meeting_type_confidence": analysis.meeting_type_confidence,
        "meeting_title_candidate": analysis.meeting_title_candidate,
        "title_basis": analysis.title_basis,
        "agenda": agenda,
        "topics": topics,
        "speaker_summaries": [],
        "decisions": [{"decision": item.get("conclusion", ""), "reason": "", "source": item.get("source_text", ""), **item} for item in conclusions],
        "action_items": actions,
        "risks": [{"risk": item.get("risk", ""), "impact": item.get("impact", ""), "mitigation": item.get("mitigation", ""), **item} for item in risks],
        "open_questions": [{"question": item.get("issue", ""), "owner": "", "source": item.get("source_text", ""), **item} for item in issues],
        "next_steps": [
            {
                "item": item.task,
                "owner": item.owner_name or "",
                "time": item.deadline or "",
                "note": item.source_text,
            }
            for item in analysis.action_items
        ],
        "meeting_agenda": agenda,
        "meeting_summary": analysis.meeting_summary,
        "key_conclusions": conclusions,
        "unresolved_issues": issues,
        "risks_and_focus": risks,
        "model_name": analysis.metadata.model_name,
        "confidence_score": analysis.metadata.confidence_score,
        "metadata": analysis.metadata.model_dump(),
    }
