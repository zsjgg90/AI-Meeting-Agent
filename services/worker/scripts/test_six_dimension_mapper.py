from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app.semantic_event_schema import SemanticEvent  # noqa: E402
from app.six_dimension_mapper import SixDimensionMapper  # noqa: E402
from app.topic_event_schema import TopicEventGroup  # noqa: E402


def make_event(
    event_id: str,
    intent: str,
    *,
    subject: str = "checkout",
    action: str = "discuss",
    object_: str = "payment flow",
    status: str = "confirmed",
    owner: str | None = None,
    deadline: str | None = None,
    priority: str | None = "unknown",
    text: str | None = None,
    confidence: float = 0.9,
) -> SemanticEvent:
    source_text = text or f"{subject} {action} {object_}"
    return SemanticEvent.model_validate(
        {
            "event_id": event_id,
            "utterance_id": f"utt-{event_id}",
            "segment_id": f"seg-{event_id}",
            "speaker": "Speaker 1",
            "speaker_role": None,
            "start_time": None,
            "end_time": None,
            "source_text": source_text,
            "normalized_text": source_text,
            "primary_intent": intent,
            "secondary_intents": [],
            "event_type": "information",
            "subject": subject,
            "action": action,
            "object": object_,
            "entities": {
                "persons": [owner] if owner else [],
                "teams": [],
                "projects": ["commerce"],
                "features": ["payment"],
                "dates": [deadline] if deadline else [],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": owner,
                "deadline": deadline,
                "priority": priority,
                "status": status,
                "polarity": "neutral",
                "certainty": "explicit",
            },
            "evidence": {
                "source_text": source_text,
                "quote": source_text,
            },
            "confidence": {
                "intent": confidence,
                "entity": confidence,
                "overall": confidence,
            },
            "needs_review": False,
        }
    )


def make_topic(
    topic_id: str,
    events: list[SemanticEvent],
    *,
    status: str = "active",
) -> TopicEventGroup:
    return TopicEventGroup(
        topic_id=topic_id,
        title=topic_id,
        event_ids=[event.event_id for event in events],
        events=events,
        start_time=None,
        end_time=None,
        status=status,
    )


class SixDimensionMapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = SixDimensionMapper()

    def test_all_six_dimensions_basic_mapping(self) -> None:
        topic = make_topic(
            "topic_1",
            [
                make_event("e1", "agenda_statement", text="review payment launch agenda"),
                make_event("e2", "information", object_="beta status", text="payment launch is in beta"),
                make_event("e3", "decision", object_="launch date", text="confirm payment launch on Friday"),
                make_event("e4", "task_assignment", action="ship", owner="Alice", deadline="Friday"),
                make_event("e5", "open_issue", object_="callback issue", status="blocked", text="payment callback issue is open"),
                make_event("e6", "risk_warning", object_="timeout risk", status="pending", text="payment timeout risk exists"),
            ],
            status="open",
        )

        result = self.mapper.map_topics("meeting-1", [topic])

        self.assertEqual(1, len(result.meeting_agenda))
        self.assertEqual(1, len(result.meeting_summary))
        self.assertEqual(1, len(result.key_conclusions))
        self.assertEqual(1, len(result.action_items))
        self.assertEqual(1, len(result.unresolved_issues))
        self.assertEqual(1, len(result.risks_and_focus))

    def test_proposal_does_not_enter_key_conclusions(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [make_topic("topic_1", [make_event("e1", "proposal", status="proposed")])],
        )

        self.assertEqual([], result.key_conclusions)

    def test_confirmed_decision_enters_key_conclusions(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [make_topic("topic_1", [make_event("e1", "decision", status="confirmed")])],
        )

        self.assertEqual(["e1"], result.key_conclusions[0].source_event_ids)

    def test_resolved_issue_does_not_enter_unresolved_issues(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [make_topic("topic_1", [make_event("e1", "open_issue", status="completed")], status="resolved")],
        )

        self.assertEqual([], result.unresolved_issues)

    def test_open_issue_enters_unresolved_issues(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [make_topic("topic_1", [make_event("e1", "open_issue", status="blocked")], status="open")],
        )

        self.assertEqual("blocked", result.unresolved_issues[0].status)

    def test_mitigated_risk_status_is_preserved(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [
                make_topic(
                    "topic_1",
                    [
                        make_event("e1", "risk_warning", status="pending", text="payment timeout risk"),
                        make_event("e2", "task_assignment", action="add fallback", text="add fallback mitigation"),
                    ],
                    status="mitigated",
                )
            ],
        )

        self.assertEqual("mitigated", result.risks_and_focus[0].status)
        self.assertEqual("add fallback mitigation", result.risks_and_focus[0].mitigation)

    def test_owner_and_deadline_are_not_invented(self) -> None:
        result = self.mapper.map_topics(
            "meeting-1",
            [make_topic("topic_1", [make_event("e1", "task_assignment", owner=None, deadline=None)])],
        )

        self.assertIsNone(result.action_items[0].owner)
        self.assertIsNone(result.action_items[0].deadline)

    def test_same_topic_duplicate_content_dedupes(self) -> None:
        topic = make_topic(
            "topic_1",
            [
                make_event("e1", "task_assignment", action="ship", text="ship payment flow"),
                make_event("e2", "task_assignment", action="ship", text="repeat ship payment flow"),
            ],
        )

        result = self.mapper.map_topics("meeting-1", [topic])

        self.assertEqual(1, len(result.action_items))
        self.assertEqual(["e1", "e2"], result.action_items[0].source_event_ids)
        self.assertIn("repeat ship payment flow", result.action_items[0].source_texts)

    def test_cross_dimension_duplicate_control(self) -> None:
        topic = make_topic(
            "topic_1",
            [
                make_event("e1", "information", action="ship", text="ship payment flow"),
                make_event("e2", "task_assignment", action="ship", text="ship payment flow"),
            ],
        )

        result = self.mapper.map_topics("meeting-1", [topic])

        self.assertEqual(1, len(result.action_items))
        self.assertEqual(0, len(result.meeting_summary))

    def test_evidence_and_topic_id_are_preserved(self) -> None:
        topic = make_topic(
            "topic_42",
            [make_event("e1", "decision", text="confirm launch gate", confidence=0.77)],
        )

        result = self.mapper.map_topics("meeting-1", [topic])
        item = result.key_conclusions[0]

        self.assertEqual("topic_42", item.topic_id)
        self.assertEqual(["e1"], item.source_event_ids)
        self.assertEqual(["confirm launch gate"], item.source_texts)
        self.assertEqual(0.77, item.confidence)


if __name__ == "__main__":
    unittest.main()
