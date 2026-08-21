from __future__ import annotations

from dataclasses import dataclass

from app.semantic_event_schema import SemanticEvent
from app.six_dimension_schema import (
    ActionItem,
    AgendaItem,
    DecisionItem,
    OpenIssueItem,
    RiskItem,
    SixDimensionResult,
    SummaryItem,
)
from app.topic_event_schema import TopicEventGroup


_NON_EVENT_INTENT = "non_event"
_CONFIRMED_STATUSES = {"confirmed", "completed", "rejected"}
_ACTION_INTENTS = {"task_assignment", "commitment"}
_SUMMARY_INTENTS = {"progress_update", "information"}
_MITIGATION_INTENTS = {
    "decision",
    "proposal",
    "task_assignment",
    "commitment",
    "requirement",
    "progress_update",
}
_MITIGATION_MARKERS = (
    "mitigate",
    "mitigation",
    "fallback",
    "rollback",
    "plan b",
    "降级",
    "兜底",
    "回滚",
    "预案",
    "应对",
)
_DIMENSION_PRIORITY = {
    "action": 5,
    "decision": 4,
    "issue": 3,
    "risk": 2,
    "summary": 1,
}


@dataclass
class _MappedCandidate:
    dimension: str
    key: str
    item: AgendaItem | SummaryItem | DecisionItem | ActionItem | OpenIssueItem | RiskItem
    event: SemanticEvent


class SixDimensionMapper:
    def map_topics(
        self,
        meeting_id: str,
        topics: list[TopicEventGroup],
    ) -> SixDimensionResult:
        candidates: list[_MappedCandidate] = []

        for topic in topics:
            for event in topic.events:
                if self._intent(event) == _NON_EVENT_INTENT:
                    continue
                candidates.extend(self._map_event(topic, event))

        candidates = self._dedupe_candidates(candidates)

        result = SixDimensionResult(meeting_id=meeting_id)
        for candidate in candidates:
            if candidate.dimension == "agenda":
                result.meeting_agenda.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "summary":
                result.meeting_summary.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "decision":
                result.key_conclusions.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "action":
                result.action_items.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "issue":
                result.unresolved_issues.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "risk":
                result.risks_and_focus.append(candidate.item)  # type: ignore[arg-type]

        return result

    def _map_event(
        self,
        topic: TopicEventGroup,
        event: SemanticEvent,
    ) -> list[_MappedCandidate]:
        intent = self._intent(event)
        key = self._dedupe_key(topic, event)
        common = self._common_payload(topic, event)

        if intent == "agenda_statement":
            return [
                _MappedCandidate(
                    "agenda",
                    key,
                    AgendaItem(**common),
                    event,
                )
            ]

        if intent in _SUMMARY_INTENTS:
            return [
                _MappedCandidate(
                    "summary",
                    key,
                    SummaryItem(**common),
                    event,
                )
            ]

        if intent == "decision" and self._is_confirmed(event):
            return [
                _MappedCandidate(
                    "decision",
                    key,
                    DecisionItem(
                        **common,
                        status=self._status(event),
                    ),
                    event,
                )
            ]

        if intent == "rejection" and self._is_confirmed(event):
            return [
                _MappedCandidate(
                    "decision",
                    key,
                    DecisionItem(
                        **common,
                        status=self._status(event),
                    ),
                    event,
                )
            ]

        if intent in _ACTION_INTENTS or self._is_actionable_requirement(event):
            return [
                _MappedCandidate(
                    "action",
                    key,
                    ActionItem(
                        **common,
                        owner=event.attributes.owner,
                        deadline=event.attributes.deadline,
                        priority=event.attributes.priority,
                        status=self._status(event),
                    ),
                    event,
                )
            ]

        if intent == "open_issue" and topic.status != "resolved":
            return [
                _MappedCandidate(
                    "issue",
                    key,
                    OpenIssueItem(
                        **common,
                        status=self._status(event),
                    ),
                    event,
                )
            ]

        if intent == "risk_warning":
            status = "mitigated" if topic.status == "mitigated" else self._status(event)
            return [
                _MappedCandidate(
                    "risk",
                    key,
                    RiskItem(
                        **common,
                        condition=self._condition(event),
                        impact=None,
                        mitigation=self._mitigation(topic, event),
                        status=status,
                    ),
                    event,
                )
            ]

        return []

    def _dedupe_candidates(
        self,
        candidates: list[_MappedCandidate],
    ) -> list[_MappedCandidate]:
        by_dimension: list[_MappedCandidate] = []
        seen_dimension_keys: set[tuple[str, str]] = set()

        for candidate in candidates:
            dimension_key = (candidate.dimension, candidate.key)
            if dimension_key in seen_dimension_keys:
                existing = next(
                    item
                    for item in by_dimension
                    if item.dimension == candidate.dimension and item.key == candidate.key
                )
                self._merge_item_evidence(existing.item, candidate.item)
                continue
            seen_dimension_keys.add(dimension_key)
            by_dimension.append(candidate)

        selected: list[_MappedCandidate] = []
        selected_by_key: dict[str, list[_MappedCandidate]] = {}

        for candidate in by_dimension:
            if candidate.dimension == "agenda":
                selected.append(candidate)
                continue

            existing_for_key = selected_by_key.setdefault(candidate.key, [])
            kept_existing = self._filter_existing_for_candidate(candidate, existing_for_key)
            if len(kept_existing) != len(existing_for_key):
                selected = [
                    item
                    for item in selected
                    if item.key != candidate.key or item in kept_existing
                ]
                selected_by_key[candidate.key] = kept_existing
                existing_for_key = kept_existing

            if self._should_keep_with_existing(candidate, existing_for_key):
                selected.append(candidate)
                existing_for_key.append(candidate)

        return selected

    def _filter_existing_for_candidate(
        self,
        candidate: _MappedCandidate,
        existing: list[_MappedCandidate],
    ) -> list[_MappedCandidate]:
        if not existing:
            return []

        if candidate.dimension == "decision":
            return existing
        if candidate.dimension == "action":
            return [
                item
                for item in existing
                if item.dimension == "decision"
                or _DIMENSION_PRIORITY.get(item.dimension, 0)
                >= _DIMENSION_PRIORITY.get(candidate.dimension, 0)
            ]

        candidate_priority = _DIMENSION_PRIORITY.get(candidate.dimension, 0)
        return [
            item
            for item in existing
            if _DIMENSION_PRIORITY.get(item.dimension, 0) >= candidate_priority
        ]

    def _should_keep_with_existing(
        self,
        candidate: _MappedCandidate,
        existing: list[_MappedCandidate],
    ) -> bool:
        if not existing:
            return True

        if candidate.dimension == "decision" and any(item.dimension == "action" for item in existing):
            return True
        if candidate.dimension == "action" and any(item.dimension == "decision" for item in existing):
            return True

        candidate_priority = _DIMENSION_PRIORITY.get(candidate.dimension, 0)
        highest_existing = max(_DIMENSION_PRIORITY.get(item.dimension, 0) for item in existing)
        return candidate_priority > highest_existing

    def _common_payload(
        self,
        topic: TopicEventGroup,
        event: SemanticEvent,
    ) -> dict[str, object]:
        return {
            "content": self._content(event),
            "topic_id": topic.topic_id,
            "source_event_ids": self._source_event_ids(topic, event),
            "source_texts": self._source_texts(event),
            "confidence": event.confidence.overall,
        }

    def _merge_item_evidence(
        self,
        existing: AgendaItem | SummaryItem | DecisionItem | ActionItem | OpenIssueItem | RiskItem,
        incoming: AgendaItem | SummaryItem | DecisionItem | ActionItem | OpenIssueItem | RiskItem,
    ) -> None:
        existing.source_event_ids = self._unique([*existing.source_event_ids, *incoming.source_event_ids])
        existing.source_texts = self._unique([*existing.source_texts, *incoming.source_texts])
        existing.confidence = max(existing.confidence, incoming.confidence)

    def _source_event_ids(
        self,
        topic: TopicEventGroup,
        event: SemanticEvent,
    ) -> list[str]:
        if self._intent(event) in _ACTION_INTENTS and event.segment_id:
            return [event.segment_id]
        event_id = event.event_id or event.utterance_id or event.segment_id
        if event_id:
            return [event_id]
        return topic.event_ids

    def _source_texts(
        self,
        event: SemanticEvent,
    ) -> list[str]:
        return self._unique(
            [
                event.source_text,
                event.evidence.source_text,
                event.evidence.quote,
            ]
        )

    def _content(
        self,
        event: SemanticEvent,
    ) -> str:
        text = event.normalized_text or event.source_text or event.evidence.source_text
        if text:
            return text

        parts = [event.subject, event.action, event.object]
        return " ".join(part for part in parts if part)

    def _condition(
        self,
        event: SemanticEvent,
    ) -> str | None:
        return event.source_text or event.normalized_text or event.object

    def _mitigation(
        self,
        topic: TopicEventGroup,
        risk_event: SemanticEvent,
    ) -> str | None:
        if topic.status != "mitigated":
            return None

        for event in topic.events:
            if event.event_id == risk_event.event_id:
                continue
            if self._intent(event) in _MITIGATION_INTENTS or self._contains_mitigation_marker(event):
                return event.source_text or event.normalized_text or event.evidence.source_text

        if self._contains_mitigation_marker(risk_event):
            return risk_event.source_text or risk_event.normalized_text or risk_event.evidence.source_text

        return None

    def _is_confirmed(
        self,
        event: SemanticEvent,
    ) -> bool:
        return self._status(event) in _CONFIRMED_STATUSES

    def _is_actionable_requirement(
        self,
        event: SemanticEvent,
    ) -> bool:
        return self._intent(event) == "requirement" and bool(self._normalize(event.action))

    def _contains_mitigation_marker(
        self,
        event: SemanticEvent,
    ) -> bool:
        text = self._event_text(event)
        return any(marker in text for marker in _MITIGATION_MARKERS)

    def _dedupe_key(
        self,
        topic: TopicEventGroup,
        event: SemanticEvent,
    ) -> str:
        parts = [
            topic.topic_id,
            self._normalize(event.subject),
            self._normalize(event.action),
            self._normalize(event.object),
        ]
        key = "|".join(part for part in parts if part)
        if key != topic.topic_id:
            return key
        return f"{topic.topic_id}|{self._normalize(self._content(event))}"

    def _intent(
        self,
        event: SemanticEvent,
    ) -> str:
        return str(event.primary_intent)

    def _status(
        self,
        event: SemanticEvent,
    ) -> str:
        return str(event.attributes.status)

    def _event_text(
        self,
        event: SemanticEvent,
    ) -> str:
        return " ".join(
            value
            for value in (
                event.source_text,
                event.normalized_text,
                event.evidence.source_text,
                event.evidence.quote,
            )
            if value
        ).lower()

    def _normalize(
        self,
        value: str | None,
    ) -> str:
        return " ".join(value.strip().lower().split()) if value else ""

    def _unique(
        self,
        values: list[str | None],
    ) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            unique_values.append(value)
        return unique_values
