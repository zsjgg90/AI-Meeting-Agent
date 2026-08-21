import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_schema import MeetingAnalysisSchema, UnresolvedIssue
from app.unresolved_fusion import MAX_SEMANTIC_UNRESOLVED, fuse_unresolved_issues


def analysis_with_unresolved(issues: list[UnresolvedIssue]) -> MeetingAnalysisSchema:
    return MeetingAnalysisSchema(
        meeting_summary="summary",
        meeting_agenda=[],
        key_conclusions=[],
        action_items=[],
        unresolved_issues=issues,
        risks_and_focus=[],
    )


def legacy_issue(issue: str, *, source_text: str | None = None, confidence: float = 0.9) -> UnresolvedIssue:
    return UnresolvedIssue(
        issue=issue,
        source_text=source_text or issue,
        confidence=confidence,
    )


def candidate(
    issue: str,
    *,
    issue_object: str | None = None,
    source_text: str | None = None,
    score: float = 0.92,
    reasons: list[str] | None = None,
    source_segment_id: str = "seg-1",
) -> dict:
    return {
        "issue": issue,
        "source_text": source_text or issue,
        "source_segment_id": source_segment_id,
        "source_event_ids": ["evt-1"],
        "score": score,
        "confidence": score,
        "issue_object": issue_object or issue.lower(),
        "merged_recall_reasons": reasons or ["unresolved_marker"],
    }


class UnresolvedFusionTests(unittest.TestCase):
    def test_legacy_unresolved_has_priority_over_semantic_duplicate(self) -> None:
        legacy = legacy_issue(
            "Payment callback signature verification is not confirmed.",
            source_text="The payment callback signature verification is still not confirmed.",
            confidence=0.95,
        )

        result = fuse_unresolved_issues(
            analysis_with_unresolved([legacy]),
            [
                candidate(
                    "Payment signature verification remains unconfirmed.",
                    issue_object="payment_external_dependency",
                    source_text="Payment signature verification remains unconfirmed because the SDK docs differ.",
                    score=0.99,
                )
            ],
        )

        self.assertEqual(len(result.unresolved_issues), 1)
        self.assertEqual(result.unresolved_issues[0].issue, legacy.issue)
        self.assertEqual(result.unresolved_issues[0].confidence, 0.95)

    def test_semantic_blocker_supplements_empty_legacy(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Payment callback signature verification is blocked by external SDK differences.",
                    issue_object="payment_external_dependency",
                    source_text="Payment callback signature verification is still blocked because the external SDK docs differ.",
                    score=0.93,
                    source_segment_id="seg-payment",
                )
            ],
        )

        self.assertEqual(len(result.unresolved_issues), 1)
        self.assertEqual(
            result.unresolved_issues[0].issue,
            "Payment callback signature verification is blocked by external SDK differences.",
        )
        self.assertEqual(
            result.unresolved_issues[0].source_text,
            "Payment callback signature verification is still blocked because the external SDK docs differ.",
        )
        self.assertNotIn("source_segment_id", result.unresolved_issues[0].model_dump())

    def test_payment_external_dependency_duplicate_merges_correctly(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Payment callback is still not passing.",
                    issue_object="payment_external_dependency",
                    score=0.8,
                ),
                candidate(
                    "Payment SDK signature verification remains unresolved.",
                    issue_object="payment_external_dependency",
                    source_text="Payment SDK signature verification remains unresolved after the callback retry.",
                    score=0.96,
                    source_segment_id="seg-2",
                ),
            ],
        )

        self.assertEqual(len(result.unresolved_issues), 1)
        self.assertEqual(result.unresolved_issues[0].issue, "Payment SDK signature verification remains unresolved.")
        self.assertEqual(
            result.unresolved_issues[0].source_text,
            "Payment SDK signature verification remains unresolved after the callback retry.",
        )

    def test_action_candidate_does_not_enter_unresolved(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Action: backend owner will fix the callback by tomorrow.",
                    reasons=["action_like"],
                )
            ],
        )

        self.assertEqual(result.unresolved_issues, [])

    def test_risk_candidate_does_not_enter_unresolved(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Risk: payment delay could impact the release.",
                    reasons=["risk_like"],
                )
            ],
        )

        self.assertEqual(result.unresolved_issues, [])

    def test_meeting_question_does_not_enter_unresolved(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Any other questions?",
                    reasons=["meeting_question"],
                )
            ],
        )

        self.assertEqual(result.unresolved_issues, [])

    def test_duplicate_unresolved_is_not_added_twice(self) -> None:
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(
                    "Payment callback remains unresolved.",
                    issue_object="payment_external_dependency",
                    score=0.9,
                ),
                candidate(
                    "Payment callback remains unresolved.",
                    issue_object="payment_external_dependency",
                    score=0.88,
                ),
            ],
        )

        self.assertEqual(len(result.unresolved_issues), 1)

    def test_semantic_append_count_is_limited(self) -> None:
        issue_names = ["Payment blocker", "Voiceprint blocker", "Device blocker", "Export blocker", "Search blocker"]
        result = fuse_unresolved_issues(
            analysis_with_unresolved([]),
            [
                candidate(issue, issue_object=f"blocker-{index}", score=1.0 - index * 0.01)
                for index, issue in enumerate(issue_names)
            ],
        )

        self.assertEqual(len(result.unresolved_issues), MAX_SEMANTIC_UNRESOLVED)


if __name__ == "__main__":
    unittest.main()
