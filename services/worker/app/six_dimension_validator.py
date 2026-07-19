from __future__ import annotations

from dataclasses import dataclass

from app.semantic_event_schema import SemanticEvent
from app.six_dimension_schema import (
    ActionItem,
    AgendaItem,
    DecisionItem,
    DimensionItem,
    OpenIssueItem,
    RiskItem,
    SixDimensionResult,
    SummaryItem,
)
from app.topic_event_schema import TopicEventGroup


_LOW_CONFIDENCE_THRESHOLD = 0.7
_CONFIRMED_STATUSES = {"confirmed", "completed", "rejected"}
_DISALLOWED_DIRECT_INTENTS = {"proposal", "question", "non_event"}
_DIMENSION_PRIORITY = {
    "action": 5,
    "decision": 4,
    "issue": 3,
    "risk": 2,
    "summary": 1,
}


@dataclass
class _Candidate:
    dimension: str
    key: str
    item: DimensionItem


@dataclass
class _ValidationContext:
    topics_by_id: dict[str, TopicEventGroup]
    events_by_id: dict[str, SemanticEvent]
    event_topics: dict[str, TopicEventGroup]


class SixDimensionValidator:
    def validate(
        self,
        result: SixDimensionResult,
        topics: list[TopicEventGroup],
    ) -> SixDimensionResult:
        context = self._build_context(topics)

        candidates: list[_Candidate] = []
        candidates.extend(self._validate_items("agenda", result.meeting_agenda, context))
        candidates.extend(self._validate_items("summary", result.meeting_summary, context))
        candidates.extend(self._validate_items("decision", result.key_conclusions, context))
        candidates.extend(self._validate_items("action", result.action_items, context))
        candidates.extend(self._validate_items("issue", result.unresolved_issues, context))
        candidates.extend(self._validate_items("risk", result.risks_and_focus, context))

        candidates = self._dedupe_same_dimension(candidates)
        candidates = self._remove_cross_dimension_duplicates(candidates)

        validated = SixDimensionResult(meeting_id=result.meeting_id)
        for candidate in candidates:
            if candidate.dimension == "agenda":
                validated.meeting_agenda.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "summary":
                validated.meeting_summary.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "decision":
                validated.key_conclusions.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "action":
                validated.action_items.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "issue":
                validated.unresolved_issues.append(candidate.item)  # type: ignore[arg-type]
            elif candidate.dimension == "risk":
                validated.risks_and_focus.append(candidate.item)  # type: ignore[arg-type]

        return validated

    def _build_context(
        self,
        topics: list[TopicEventGroup],
    ) -> _ValidationContext:
        topics_by_id = {topic.topic_id: topic for topic in topics}
        events_by_id: dict[str, SemanticEvent] = {}
        event_topics: dict[str, TopicEventGroup] = {}

        for topic in topics:
            for event in topic.events:
                for event_id in self._event_ids(event):
                    events_by_id[event_id] = event
                    event_topics[event_id] = topic

        return _ValidationContext(
            topics_by_id=topics_by_id,
            events_by_id=events_by_id,
            event_topics=event_topics,
        )

    def _validate_items(
        self,
        dimension: str,
        items: list[DimensionItem],
        context: _ValidationContext,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []

        for raw_item in items:
            item = raw_item.model_copy(deep=True)
            events = self._referenced_events(item, context)
            errors = self._base_errors(item, events, context)

            if not errors:
                errors.extend(self._dimension_errors(dimension, item, events, context))

            if errors:
                continue

            self._repair_item(dimension, item, events, context)
            self._mark_quality(item)
            candidates.append(
                _Candidate(
                    dimension=dimension,
                    key=self._dedupe_key(item, events),
                    item=item,
                )
            )

        return candidates

    def _base_errors(
        self,
        item: DimensionItem,
        events: list[SemanticEvent],
        context: _ValidationContext,
    ) -> list[str]:
        errors: list[str] = []
        if not item.content.strip():
            errors.append("content_empty")
        if item.topic_id not in context.topics_by_id:
            errors.append("topic_id_invalid")
        if not item.source_event_ids:
            errors.append("source_event_ids_empty")
        if item.source_event_ids and len(events) != len(item.source_event_ids):
            errors.append("source_event_id_invalid")
        if not item.source_texts:
            errors.append("source_texts_empty")
        if item.confidence < 0.0 or item.confidence > 1.0:
            errors.append("confidence_out_of_range")
        if events and all(self._intent(event) in _DISALLOWED_DIRECT_INTENTS for event in events):
            errors.append("disallowed_direct_intent")
        return errors

    def _dimension_errors(
        self,
        dimension: str,
        item: DimensionItem,
        events: list[SemanticEvent],
        context: _ValidationContext,
    ) -> list[str]:
        if dimension == "decision":
            if not any(
                self._intent(event) in {"decision", "rejection"}
                and self._status(event) in _CONFIRMED_STATUSES
                for event in events
            ):
                return ["decision_source_invalid"]

        if dimension == "action":
            if not any(self._has_action_evidence(event) for event in events):
                return ["action_source_invalid"]

        if dimension == "issue":
            topic = context.topics_by_id[item.topic_id]
            if topic.status == "resolved":
                return ["resolved_topic_issue"]
            if not any(self._intent(event) == "open_issue" for event in events):
                return ["issue_source_invalid"]

        if dimension == "risk":
            if not any(self._intent(event) == "risk_warning" for event in events):
                return ["risk_source_invalid"]

        return []

    def _repair_item(
        self,
        dimension: str,
        item: DimensionItem,
        events: list[SemanticEvent],
        context: _ValidationContext,
    ) -> None:
        item.validation_errors = []

        if isinstance(item, ActionItem):
            if item.owner and not self._has_value_evidence(item.owner, events, "owner"):
                item.owner = None
            if item.deadline and not self._has_value_evidence(item.deadline, events, "deadline"):
                item.deadline = None

        if isinstance(item, RiskItem):
            topic = context.topics_by_id[item.topic_id]
            if topic.status == "mitigated":
                item.status = "mitigated"

    def _mark_quality(
        self,
        item: DimensionItem,
    ) -> None:
        if item.confidence < _LOW_CONFIDENCE_THRESHOLD:
            item.needs_review = True
            item.validation_errors = self._unique(
                [*item.validation_errors, "low_confidence"]
            )

    def _dedupe_same_dimension(
        self,
        candidates: list[_Candidate],
    ) -> list[_Candidate]:
        result: list[_Candidate] = []
        by_key: dict[tuple[str, str], _Candidate] = {}

        for candidate in candidates:
            key = (candidate.dimension, candidate.key)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = candidate
                result.append(candidate)
                continue

            self._merge_evidence(existing.item, candidate.item)

        return result

    def _remove_cross_dimension_duplicates(
        self,
        candidates: list[_Candidate],
    ) -> list[_Candidate]:
        selected: list[_Candidate] = []
        selected_by_key: dict[str, list[_Candidate]] = {}

        for candidate in candidates:
            if candidate.dimension == "agenda":
                selected.append(candidate)
                continue

            existing = selected_by_key.setdefault(candidate.key, [])
            kept_existing = self._filter_existing_for_candidate(candidate, existing)
            if len(kept_existing) != len(existing):
                selected = [
                    item
                    for item in selected
                    if item.key != candidate.key or item in kept_existing
                ]
                selected_by_key[candidate.key] = kept_existing
                existing = kept_existing

            if self._should_keep_with_existing(candidate, existing):
                selected.append(candidate)
                existing.append(candidate)

        return selected

    def _filter_existing_for_candidate(
        self,
        candidate: _Candidate,
        existing: list[_Candidate],
    ) -> list[_Candidate]:
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

        priority = _DIMENSION_PRIORITY.get(candidate.dimension, 0)
        return [
            item
            for item in existing
            if _DIMENSION_PRIORITY.get(item.dimension, 0) >= priority
        ]

    def _should_keep_with_existing(
        self,
        candidate: _Candidate,
        existing: list[_Candidate],
    ) -> bool:
        if not existing:
            return True
        if candidate.dimension == "decision" and any(item.dimension == "action" for item in existing):
            return True
        if candidate.dimension == "action" and any(item.dimension == "decision" for item in existing):
            return True

        priority = _DIMENSION_PRIORITY.get(candidate.dimension, 0)
        highest_existing = max(_DIMENSION_PRIORITY.get(item.dimension, 0) for item in existing)
        return priority > highest_existing

    def _merge_evidence(
        self,
        existing: DimensionItem,
        incoming: DimensionItem,
    ) -> None:
        existing.source_event_ids = self._unique(
            [*existing.source_event_ids, *incoming.source_event_ids]
        )
        existing.source_texts = self._unique(
            [*existing.source_texts, *incoming.source_texts]
        )
        existing.confidence = max(existing.confidence, incoming.confidence)
        existing.needs_review = existing.needs_review or incoming.needs_review
        existing.validation_errors = self._unique(
            [*existing.validation_errors, *incoming.validation_errors]
        )

    def _referenced_events(
        self,
        item: DimensionItem,
        context: _ValidationContext,
    ) -> list[SemanticEvent]:
        events: list[SemanticEvent] = []
        for event_id in item.source_event_ids:
            event = context.events_by_id.get(event_id)
            if event is not None:
                events.append(event)
        return events

    def _dedupe_key(
        self,
        item: DimensionItem,
        events: list[SemanticEvent],
    ) -> str:
        if events:
            event = events[0]
            parts = [
                item.topic_id,
                self._normalize(event.subject),
                self._normalize(event.action),
                self._normalize(event.object),
            ]
            key = "|".join(part for part in parts if part)
            if key != item.topic_id:
                return key
        return f"{item.topic_id}|{self._normalize(item.content)}"

    def _has_action_evidence(
        self,
        event: SemanticEvent,
    ) -> bool:
        return bool(self._normalize(event.action)) and self._intent(event) in {
            "task_assignment",
            "commitment",
            "requirement",
        }

    def _has_value_evidence(
        self,
        value: str,
        events: list[SemanticEvent],
        field_name: str,
    ) -> bool:
        normalized = self._normalize(value)
        for event in events:
            if field_name == "owner":
                values = [
                    event.attributes.owner,
                    *event.entities.persons,
                    event.source_text,
                    event.normalized_text,
                    event.evidence.source_text,
                    event.evidence.quote,
                ]
            else:
                values = [
                    event.attributes.deadline,
                    *event.entities.dates,
                    event.source_text,
                    event.normalized_text,
                    event.evidence.source_text,
                    event.evidence.quote,
                ]
            if any(normalized and normalized in self._normalize(candidate) for candidate in values):
                return True
        return False

    def _event_ids(
        self,
        event: SemanticEvent,
    ) -> list[str]:
        return self._unique([event.event_id, event.utterance_id, event.segment_id])

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
