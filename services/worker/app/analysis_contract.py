from __future__ import annotations

from typing import Any

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


def _text(value: object) -> str:
    return str(value or "").strip()


def _confidence(value: object, default: float = 0.7) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_items(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in _list(value) if isinstance(item, dict)]


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
