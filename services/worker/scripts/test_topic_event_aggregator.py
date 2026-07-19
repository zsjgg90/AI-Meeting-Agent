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
from app.topic_event_aggregator import TopicEventAggregator  # noqa: E402


def make_event(
    event_id: str,
    intent: str,
    *,
    subject: str = "checkout",
    action: str = "discuss",
    object_: str = "payment flow",
    project: str = "commerce",
    feature: str = "payment",
    speaker: str = "Speaker 1",
    status: str = "confirmed",
    text: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
) -> SemanticEvent:
    source_text = text or f"{subject} {action} {object_}"
    return SemanticEvent.model_validate(
        {
            "event_id": event_id,
            "utterance_id": f"utt-{event_id}",
            "segment_id": f"seg-{event_id}",
            "speaker": speaker,
            "speaker_role": None,
            "start_time": start_time,
            "end_time": end_time,
            "source_text": source_text,
            "normalized_text": source_text,
            "primary_intent": intent,
            "secondary_intents": [],
            "event_type": "information",
            "subject": subject,
            "action": action,
            "object": object_,
            "entities": {
                "persons": [],
                "teams": [],
                "projects": [project] if project else [],
                "features": [feature] if feature else [],
                "dates": [],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": None,
                "deadline": None,
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
                "intent": 0.9,
                "entity": 0.9,
                "overall": 0.9,
            },
            "needs_review": False,
        }
    )


class TopicEventAggregatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = TopicEventAggregator()

    def test_same_topic_continuous_events(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "proposal", action="propose", start_time=1.0),
                make_event("e2", "task_assignment", action="assign", end_time=3.0),
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual(["e1", "e2"], groups[0].event_ids)
        self.assertEqual(1.0, groups[0].start_time)
        self.assertEqual(3.0, groups[0].end_time)

    def test_explicit_topic_switch(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "decision", project="commerce", feature="payment"),
                make_event(
                    "e2",
                    "proposal",
                    project="growth",
                    feature="referral",
                    object_="referral page",
                    text="next topic: discuss referral page",
                ),
            ]
        )

        self.assertEqual(2, len(groups))
        self.assertEqual("commerce", groups[0].title)
        self.assertEqual("growth", groups[1].title)

    def test_speaker_change_does_not_switch_topic(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "open_issue", speaker="Speaker 1", status="blocked"),
                make_event("e2", "decision", speaker="Speaker 2", text="payment flow is resolved"),
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual("resolved", groups[0].status)

    def test_proposal_turns_into_decision(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "proposal", action="propose", status="proposed"),
                make_event("e2", "decision", action="decide", status="confirmed"),
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual(1, len(groups[0].events))
        self.assertEqual("decision", groups[0].events[0].primary_intent)
        self.assertEqual(["e1", "e2"], groups[0].event_ids)

    def test_issue_resolved(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "open_issue", status="blocked", text="payment flow has an open question"),
                make_event("e2", "decision", status="confirmed", text="payment flow is resolved by callback retry"),
            ]
        )

        self.assertEqual("resolved", groups[0].status)
        self.assertEqual("completed", groups[0].events[0].attributes.status)

    def test_issue_unresolved(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "open_issue", status="blocked", text="payment flow has no answer yet"),
                make_event("e2", "information", status="unknown", text="payment flow needs more data"),
            ]
        )

        self.assertEqual("open", groups[0].status)

    def test_risk_and_mitigation(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "risk_warning", status="pending", text="payment flow may timeout"),
                make_event("e2", "task_assignment", status="confirmed", text="add fallback mitigation for payment flow"),
            ]
        )

        self.assertEqual("mitigated", groups[0].status)
        self.assertIn("task_assignment", groups[0].events[0].secondary_intents)

    def test_duplicate_event_dedupes_and_merges_evidence(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "decision", action="decide", text="decide payment flow plan"),
                make_event("e2", "decision", action="decide", text="repeat decide payment flow plan"),
            ]
        )

        self.assertEqual(1, len(groups[0].events))
        self.assertEqual(["e1", "e2"], groups[0].event_ids)
        self.assertIn("repeat decide payment flow plan", groups[0].events[0].evidence.source_text)

    def test_multi_topic_meeting(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "decision", project="commerce", feature="payment"),
                make_event("e2", "task_assignment", project="commerce", feature="payment"),
                make_event(
                    "e3",
                    "proposal",
                    project="growth",
                    feature="referral",
                    object_="referral page",
                    text="next topic: referral page proposal",
                ),
                make_event("e4", "decision", project="growth", feature="referral", object_="referral page"),
            ]
        )

        self.assertEqual(2, len(groups))
        self.assertEqual(["e1", "e2"], groups[0].event_ids)
        self.assertEqual(["e3", "e4"], groups[1].event_ids)

    def test_non_event_filtered(self) -> None:
        groups = self.aggregator.aggregate(
            [
                make_event("e1", "non_event", status="unknown", text="thanks everyone"),
                make_event("e2", "decision"),
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual(["e2"], groups[0].event_ids)


if __name__ == "__main__":
    unittest.main()
