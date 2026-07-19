from __future__ import annotations

from dataclasses import dataclass, field

from app.semantic_event_schema import SemanticEvent
from app.topic_event_schema import TopicEventGroup


_NON_EVENT_INTENT = "non_event"
_UNKNOWN_STATUS = "unknown"

_EXPLICIT_TOPIC_SWITCH_MARKERS = (
    "next topic",
    "moving on",
    "switch to",
    "let's discuss",
    "now discuss",
    "another topic",
    "接下来",
    "下一个",
    "另一个",
    "切换到",
    "换个话题",
    "下面讨论",
    "我们再看",
)

_RESOLUTION_MARKERS = (
    "resolved",
    "fixed",
    "closed",
    "answered",
    "solved",
    "完成",
    "解决",
    "已处理",
    "有方案",
    "确认",
)

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

_RESOLVING_INTENTS = {
    "decision",
    "progress_update",
    "commitment",
    "task_assignment",
    "requirement",
    "information",
}

_MITIGATION_INTENTS = {
    "decision",
    "proposal",
    "task_assignment",
    "commitment",
    "requirement",
    "progress_update",
}

_TRANSITIONS = {
    ("proposal", "decision"),
    ("task_assignment", "progress_update"),
}


@dataclass
class _TopicDraft:
    events: list[SemanticEvent] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    topic_terms: set[str] = field(default_factory=set)
    focus_terms: set[str] = field(default_factory=set)
    matter_keys: set[str] = field(default_factory=set)
    resolved_issue_keys: set[str] = field(default_factory=set)
    mitigated_risk_keys: set[str] = field(default_factory=set)


class TopicEventAggregator:
    def aggregate(
        self,
        events: list[SemanticEvent],
    ) -> list[TopicEventGroup]:
        groups: list[TopicEventGroup] = []
        current = _TopicDraft()

        for raw_event in events:
            if self._intent(raw_event) == _NON_EVENT_INTENT:
                continue

            event = raw_event.model_copy(deep=True)

            if self._should_start_new_topic(current, event):
                groups.append(self._finalize_group(current, len(groups) + 1))
                current = _TopicDraft()

            self._add_event(current, event)

        if current.events:
            groups.append(self._finalize_group(current, len(groups) + 1))

        return groups

    def _should_start_new_topic(
        self,
        group: _TopicDraft,
        event: SemanticEvent,
    ) -> bool:
        if not group.events:
            return False

        focus_terms = self._focus_terms(event)
        topic_terms = self._topic_terms(event)
        matter_key = self._matter_key(event)
        has_explicit_switch = self._has_explicit_topic_switch(event)
        related = (
            bool(focus_terms & group.focus_terms)
            or matter_key in group.matter_keys
            or self._has_transition_target(group, event)
            or self._is_resolution_for_open_issue(group, event, matter_key)
            or self._is_mitigation_for_risk(group, event, matter_key)
        )

        if topic_terms and group.topic_terms and not (topic_terms & group.topic_terms):
            return True

        if has_explicit_switch:
            return not related

        if focus_terms and group.focus_terms and not related:
            return True

        return False

    def _add_event(
        self,
        group: _TopicDraft,
        event: SemanticEvent,
    ) -> None:
        event_id = self._event_id(event)
        matter_key = self._matter_key(event)
        focus_terms = self._focus_terms(event)
        topic_terms = self._topic_terms(event)

        group.event_ids.append(event_id)

        for existing in group.events:
            if self._is_duplicate(existing, event):
                self._merge_evidence(existing, event)
                self._merge_secondary_intents(existing, event)
                group.topic_terms.update(topic_terms)
                group.focus_terms.update(focus_terms)
                group.matter_keys.add(matter_key)
                return

            if self._is_state_transition(existing, event):
                self._apply_state_transition(existing, event)
                if self._intent(existing) == "open_issue":
                    group.resolved_issue_keys.add(self._matter_key(existing))
                if self._intent(existing) == "risk_warning":
                    group.mitigated_risk_keys.add(self._matter_key(existing))
                group.topic_terms.update(topic_terms)
                group.focus_terms.update(focus_terms)
                group.matter_keys.add(matter_key)
                return

        group.events.append(event)
        group.topic_terms.update(topic_terms)
        group.focus_terms.update(focus_terms)
        group.matter_keys.add(matter_key)

    def _finalize_group(
        self,
        group: _TopicDraft,
        number: int,
    ) -> TopicEventGroup:
        start_times = [event.start_time for event in group.events if event.start_time is not None]
        end_times = [event.end_time for event in group.events if event.end_time is not None]

        return TopicEventGroup(
            topic_id=f"topic_{number}",
            title=self._title_for_group(group),
            event_ids=self._unique(group.event_ids),
            events=group.events,
            start_time=min(start_times) if start_times else None,
            end_time=max(end_times) if end_times else None,
            status=self._status_for_group(group),
        )

    def _status_for_group(
        self,
        group: _TopicDraft,
    ) -> str:
        open_issue_keys = {
            self._matter_key(event)
            for event in group.events
            if self._intent(event) == "open_issue"
            and self._status(event) not in {"completed", "confirmed"}
        }
        unresolved_issue_keys = open_issue_keys - group.resolved_issue_keys
        if unresolved_issue_keys:
            return "open"

        risk_keys = {
            self._matter_key(event)
            for event in group.events
            if self._intent(event) == "risk_warning"
            and self._status(event) not in {"completed", "confirmed"}
        }
        unmitigated_risk_keys = risk_keys - group.mitigated_risk_keys
        if unmitigated_risk_keys:
            return "at_risk"

        if open_issue_keys or group.resolved_issue_keys:
            return "resolved"

        if risk_keys or group.mitigated_risk_keys:
            return "mitigated"

        return "active"

    def _title_for_group(
        self,
        group: _TopicDraft,
    ) -> str:
        first = group.events[0]
        entities = first.entities
        for values in (
            entities.projects,
            entities.features,
            [first.object] if first.object else [],
            [first.subject] if first.subject else [],
        ):
            for value in values:
                normalized = self._normalize(value)
                if normalized:
                    return value

        text = first.normalized_text or first.source_text or first.event_id
        return text[:40]

    def _has_transition_target(
        self,
        group: _TopicDraft,
        event: SemanticEvent,
    ) -> bool:
        return any(self._is_state_transition(existing, event) for existing in group.events)

    def _is_state_transition(
        self,
        existing: SemanticEvent,
        incoming: SemanticEvent,
    ) -> bool:
        if not self._same_matter(existing, incoming):
            return False

        pair = (self._intent(existing), self._intent(incoming))
        if pair in _TRANSITIONS:
            return True
        if pair[0] == "open_issue" and self._is_resolving_event(incoming):
            return True
        if pair[0] == "risk_warning" and self._is_mitigation_event(incoming):
            return True
        return False

    def _apply_state_transition(
        self,
        existing: SemanticEvent,
        incoming: SemanticEvent,
    ) -> None:
        original_intent = self._intent(existing)
        self._merge_evidence(existing, incoming)
        self._merge_secondary_intents(existing, incoming)

        if original_intent == "open_issue":
            existing.attributes.status = "completed"
            return

        if original_intent == "risk_warning":
            existing.attributes.status = "completed"
            return

        existing.primary_intent = incoming.primary_intent
        existing.event_type = incoming.event_type
        existing.action = incoming.action or existing.action
        existing.object = incoming.object or existing.object
        existing.normalized_text = incoming.normalized_text or existing.normalized_text
        if self._status(incoming) != _UNKNOWN_STATUS:
            existing.attributes.status = incoming.attributes.status

    def _is_resolution_for_open_issue(
        self,
        group: _TopicDraft,
        event: SemanticEvent,
        matter_key: str,
    ) -> bool:
        if not self._is_resolving_event(event):
            return False
        return any(
            self._intent(existing) == "open_issue"
            and self._matter_key(existing) == matter_key
            for existing in group.events
        )

    def _is_mitigation_for_risk(
        self,
        group: _TopicDraft,
        event: SemanticEvent,
        matter_key: str,
    ) -> bool:
        if not self._is_mitigation_event(event):
            return False
        return any(
            self._intent(existing) == "risk_warning"
            and self._matter_key(existing) == matter_key
            for existing in group.events
        )

    def _is_resolving_event(
        self,
        event: SemanticEvent,
    ) -> bool:
        if self._intent(event) not in _RESOLVING_INTENTS:
            return False
        status = self._status(event)
        if status in {"completed", "confirmed"}:
            return True
        text = self._event_text(event)
        return any(marker in text for marker in _RESOLUTION_MARKERS)

    def _is_mitigation_event(
        self,
        event: SemanticEvent,
    ) -> bool:
        if self._intent(event) not in _MITIGATION_INTENTS:
            return False
        text = self._event_text(event)
        return any(marker in text for marker in _MITIGATION_MARKERS)

    def _is_duplicate(
        self,
        existing: SemanticEvent,
        incoming: SemanticEvent,
    ) -> bool:
        return (
            self._intent(existing) == self._intent(incoming)
            and self._dedupe_key(existing) == self._dedupe_key(incoming)
        )

    def _same_matter(
        self,
        left: SemanticEvent,
        right: SemanticEvent,
    ) -> bool:
        left_terms = self._focus_terms(left)
        right_terms = self._focus_terms(right)
        return (
            self._matter_key(left) == self._matter_key(right)
            or bool(left_terms & right_terms)
        )

    def _dedupe_key(
        self,
        event: SemanticEvent,
    ) -> str:
        parts = [
            self._normalize(event.subject),
            self._normalize(event.action),
            self._normalize(event.object),
        ]
        joined = "|".join(part for part in parts if part)
        return joined or self._matter_key(event)

    def _matter_key(
        self,
        event: SemanticEvent,
    ) -> str:
        terms = sorted(self._focus_terms(event))
        if terms:
            return "|".join(terms)

        parts = [
            self._normalize(event.subject),
            self._normalize(event.object),
            self._normalize(event.action),
        ]
        joined = "|".join(part for part in parts if part)
        if joined:
            return joined

        return self._normalize(event.normalized_text or event.source_text or event.event_id)

    def _focus_terms(
        self,
        event: SemanticEvent,
    ) -> set[str]:
        entities = event.entities
        raw_terms = [
            *entities.projects,
            *entities.features,
            event.object,
            event.subject,
        ]
        return {
            normalized
            for normalized in (self._normalize(term) for term in raw_terms)
            if normalized
        }

    def _topic_terms(
        self,
        event: SemanticEvent,
    ) -> set[str]:
        entities = event.entities
        return {
            normalized
            for normalized in (
                self._normalize(term)
                for term in [*entities.projects, *entities.features]
            )
            if normalized
        }

    def _has_explicit_topic_switch(
        self,
        event: SemanticEvent,
    ) -> bool:
        text = self._event_text(event)
        return any(marker in text for marker in _EXPLICIT_TOPIC_SWITCH_MARKERS)

    def _merge_evidence(
        self,
        existing: SemanticEvent,
        incoming: SemanticEvent,
    ) -> None:
        texts = self._unique(
            [
                existing.source_text,
                existing.evidence.source_text,
                incoming.source_text,
                incoming.evidence.source_text,
            ]
        )
        merged_source = "\n".join(text for text in texts if text)
        if merged_source:
            existing.source_text = merged_source
            existing.evidence.source_text = merged_source

        if not existing.evidence.quote and incoming.evidence.quote:
            existing.evidence.quote = incoming.evidence.quote

    def _merge_secondary_intents(
        self,
        existing: SemanticEvent,
        incoming: SemanticEvent,
    ) -> None:
        existing.secondary_intents = self._unique(
            [
                *existing.secondary_intents,
                self._intent(incoming),
                *incoming.secondary_intents,
            ]
        )

    def _event_id(
        self,
        event: SemanticEvent,
    ) -> str:
        return event.event_id or event.utterance_id or event.segment_id

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
        values: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique_values.append(value)
        return unique_values
