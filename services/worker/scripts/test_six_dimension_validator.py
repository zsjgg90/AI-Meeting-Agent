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
from app.six_dimension_schema import (  # noqa: E402
    ActionItem,
    AgendaItem,
    DecisionItem,
    OpenIssueItem,
    RiskItem,
    SixDimensionResult,
    SummaryItem,
)
from app.six_dimension_validator import SixDimensionValidator  # noqa: E402
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
                "priority": "unknown",
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


def base_result(**kwargs: object) -> SixDimensionResult:
    return SixDimensionResult(meeting_id="meeting-1", **kwargs)


class SixDimensionValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SixDimensionValidator()

    def test_valid_six_dimension_result_passes(self) -> None:
        events = [
            make_event("e1", "agenda_statement", text="review agenda"),
            make_event("e2", "information", object_="beta status", text="beta status"),
            make_event("e3", "decision", object_="launch date", text="confirm launch"),
            make_event("e4", "task_assignment", action="ship", owner="Alice", deadline="Friday", text="Alice ships on Friday"),
            make_event("e5", "open_issue", object_="callback", status="blocked", text="callback open"),
            make_event("e6", "risk_warning", object_="timeout", status="pending", text="timeout risk"),
        ]
        topic = make_topic("topic_1", events, status="open")
        result = base_result(
            meeting_agenda=[AgendaItem(content="review agenda", topic_id="topic_1", source_event_ids=["e1"], source_texts=["review agenda"], confidence=0.9)],
            meeting_summary=[SummaryItem(content="beta status", topic_id="topic_1", source_event_ids=["e2"], source_texts=["beta status"], confidence=0.9)],
            key_conclusions=[DecisionItem(content="confirm launch", topic_id="topic_1", source_event_ids=["e3"], source_texts=["confirm launch"], confidence=0.9)],
            action_items=[ActionItem(content="Alice ships on Friday", topic_id="topic_1", source_event_ids=["e4"], source_texts=["Alice ships on Friday"], confidence=0.9, owner="Alice", deadline="Friday")],
            unresolved_issues=[OpenIssueItem(content="callback open", topic_id="topic_1", source_event_ids=["e5"], source_texts=["callback open"], confidence=0.9)],
            risks_and_focus=[RiskItem(content="timeout risk", topic_id="topic_1", source_event_ids=["e6"], source_texts=["timeout risk"], confidence=0.9)],
        )

        validated = self.validator.validate(result, [topic])

        self.assertEqual(1, len(validated.meeting_agenda))
        self.assertEqual(1, len(validated.meeting_summary))
        self.assertEqual(1, len(validated.key_conclusions))
        self.assertEqual(1, len(validated.action_items))
        self.assertEqual(1, len(validated.unresolved_issues))
        self.assertEqual(1, len(validated.risks_and_focus))

    def test_empty_content_filtered(self) -> None:
        event = make_event("e1", "decision")
        result = base_result(
            key_conclusions=[DecisionItem(content=" ", topic_id="topic_1", source_event_ids=["e1"], source_texts=["text"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertEqual([], validated.key_conclusions)

    def test_invalid_topic_id_filtered(self) -> None:
        event = make_event("e1", "decision")
        result = base_result(
            key_conclusions=[DecisionItem(content="confirm", topic_id="missing", source_event_ids=["e1"], source_texts=["confirm"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertEqual([], validated.key_conclusions)

    def test_invalid_source_event_id_filtered(self) -> None:
        event = make_event("e1", "decision")
        result = base_result(
            key_conclusions=[DecisionItem(content="confirm", topic_id="topic_1", source_event_ids=["missing"], source_texts=["confirm"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertEqual([], validated.key_conclusions)

    def test_proposal_disguised_as_decision_filtered(self) -> None:
        event = make_event("e1", "proposal", status="proposed")
        result = base_result(
            key_conclusions=[DecisionItem(content="maybe launch", topic_id="topic_1", source_event_ids=["e1"], source_texts=["maybe launch"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertEqual([], validated.key_conclusions)

    def test_resolved_issue_filtered(self) -> None:
        event = make_event("e1", "open_issue", status="completed")
        result = base_result(
            unresolved_issues=[OpenIssueItem(content="callback", topic_id="topic_1", source_event_ids=["e1"], source_texts=["callback"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event], status="resolved")])

        self.assertEqual([], validated.unresolved_issues)

    def test_owner_and_deadline_without_evidence_are_cleared(self) -> None:
        event = make_event("e1", "task_assignment", action="ship", owner=None, deadline=None, text="ship payment flow")
        result = base_result(
            action_items=[
                ActionItem(
                    content="ship payment flow",
                    topic_id="topic_1",
                    source_event_ids=["e1"],
                    source_texts=["ship payment flow"],
                    confidence=0.9,
                    owner="Alice",
                    deadline="Friday",
                )
            ]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertIsNone(validated.action_items[0].owner)
        self.assertIsNone(validated.action_items[0].deadline)

    def test_risk_without_risk_warning_evidence_filtered(self) -> None:
        event = make_event("e1", "information")
        result = base_result(
            risks_and_focus=[RiskItem(content="timeout risk", topic_id="topic_1", source_event_ids=["e1"], source_texts=["timeout"], confidence=0.9)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertEqual([], validated.risks_and_focus)

    def test_duplicate_items_deduped(self) -> None:
        event_1 = make_event("e1", "task_assignment", action="ship", text="ship payment")
        event_2 = make_event("e2", "task_assignment", action="ship", text="repeat ship payment")
        result = base_result(
            action_items=[
                ActionItem(content="ship payment", topic_id="topic_1", source_event_ids=["e1"], source_texts=["ship payment"], confidence=0.8),
                ActionItem(content="ship payment duplicate", topic_id="topic_1", source_event_ids=["e2"], source_texts=["repeat ship payment"], confidence=0.9),
            ]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event_1, event_2])])

        self.assertEqual(1, len(validated.action_items))
        self.assertEqual(["e1", "e2"], validated.action_items[0].source_event_ids)
        self.assertEqual(0.9, validated.action_items[0].confidence)

    def test_low_confidence_marks_review(self) -> None:
        event = make_event("e1", "decision")
        result = base_result(
            key_conclusions=[DecisionItem(content="confirm", topic_id="topic_1", source_event_ids=["e1"], source_texts=["confirm"], confidence=0.65)]
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [event])])

        self.assertTrue(validated.key_conclusions[0].needs_review)
        self.assertIn("low_confidence", validated.key_conclusions[0].validation_errors)

    def test_confirmed_decision_and_action_can_coexist(self) -> None:
        decision = make_event("e1", "decision", action="ship", text="confirm shipping plan")
        action = make_event("e2", "task_assignment", action="ship", text="ship payment flow")
        result = base_result(
            key_conclusions=[DecisionItem(content="confirm shipping plan", topic_id="topic_1", source_event_ids=["e1"], source_texts=["confirm shipping plan"], confidence=0.9)],
            action_items=[ActionItem(content="ship payment flow", topic_id="topic_1", source_event_ids=["e2"], source_texts=["ship payment flow"], confidence=0.9)],
        )

        validated = self.validator.validate(result, [make_topic("topic_1", [decision, action])])

        self.assertEqual(1, len(validated.key_conclusions))
        self.assertEqual(1, len(validated.action_items))


if __name__ == "__main__":
    unittest.main()
