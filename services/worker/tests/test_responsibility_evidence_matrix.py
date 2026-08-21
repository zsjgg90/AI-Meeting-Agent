import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.responsibility_evidence_matrix import ResponsibilityEvidenceMatrixBuilder
from app.responsibility_extractor import ResponsibilityContext, ResponsibilityEvidence


def context(
    *,
    responsibility_id: str = "resp-1",
    task: str = "Prepare launch checklist",
    owner: str | None = "Alice",
    segment_id: str = "seg-1",
    responsibility_type: str = "explicit_owner",
    confidence: float = 0.86,
) -> ResponsibilityContext:
    evidence_type = "unknown_owner" if owner is None else "explicit_owner_text"
    supported_fields = ["task"] if owner is None else ["task", "owner"]
    return ResponsibilityContext(
        responsibility_id=responsibility_id,
        responsibility_type=responsibility_type,
        task=task,
        owner=owner,
        evidence=[
            ResponsibilityEvidence(
                type=evidence_type,
                source_type="semantic_event",
                meeting_id="meeting-1",
                segment_id=segment_id,
                source_text="Alice owns the launch checklist.",
                owner_text=owner,
                task_text=task,
                supported_fields=supported_fields,
                confidence=confidence,
            )
        ],
        confidence=confidence,
        source_type="semantic_event",
    )


class ResponsibilityEvidenceMatrixTest(unittest.TestCase):
    def test_owner_match_is_confirmed(self) -> None:
        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[
                {
                    "task": "Prepare launch checklist",
                    "owner_name": "Alice",
                    "source_segment_id": "seg-1",
                    "confidence": 0.7,
                }
            ],
            responsibility_contexts=[context()],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "confirmed_match")
        self.assertEqual(row.action_owner, "Alice")
        self.assertEqual(row.responsibility_candidates[0].owner, "Alice")
        self.assertEqual(row.evidence[0].supported_fields, ["task", "owner"])
        self.assertGreaterEqual(row.confidence, 0.86)

    def test_missing_action_owner_is_flagged_without_filling_owner(self) -> None:
        action_item = {
            "task": "Prepare launch checklist",
            "owner_name": None,
            "source_segment_id": "seg-1",
        }

        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[action_item],
            responsibility_contexts=[context()],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "owner_missing")
        self.assertIsNone(row.action_owner)
        self.assertIsNone(action_item["owner_name"])
        self.assertEqual(row.responsibility_candidates[0].owner, "Alice")

    def test_conflicting_action_owner_is_flagged(self) -> None:
        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[
                {
                    "task": "Prepare launch checklist",
                    "owner_name": "Bob",
                    "source_segment_id": "seg-1",
                }
            ],
            responsibility_contexts=[context()],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "owner_conflict")
        self.assertEqual(row.action_owner, "Bob")
        self.assertEqual(row.responsibility_candidates[0].owner, "Alice")

    def test_action_without_responsibility_evidence_is_unknown(self) -> None:
        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[
                {
                    "task": "Prepare launch checklist",
                    "owner_name": None,
                    "source_segment_id": "seg-1",
                    "confidence": 0.61,
                }
            ],
            responsibility_contexts=[],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "unknown")
        self.assertEqual(row.responsibility_candidates, [])
        self.assertEqual(row.evidence, [])
        self.assertEqual(row.confidence, 0.61)

    def test_unmatched_responsibility_context_is_responsibility_only(self) -> None:
        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[],
            responsibility_contexts=[context()],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "responsibility_only")
        self.assertIsNone(row.action_owner)
        self.assertEqual(row.responsibility_candidates[0].owner, "Alice")

    def test_unknown_context_does_not_create_owner_missing(self) -> None:
        matrix = ResponsibilityEvidenceMatrixBuilder().build(
            action_items=[
                {
                    "task": "Prepare launch checklist",
                    "owner_name": None,
                    "source_segment_id": "seg-1",
                }
            ],
            responsibility_contexts=[
                context(
                    responsibility_id="resp-unknown",
                    owner=None,
                    responsibility_type="unknown",
                    confidence=0.2,
                )
            ],
        )

        row = matrix.rows[0]
        self.assertEqual(row.consistency_status, "unknown")
        self.assertIsNone(row.action_owner)
        self.assertIsNone(row.responsibility_candidates[0].owner)


if __name__ == "__main__":
    unittest.main()
