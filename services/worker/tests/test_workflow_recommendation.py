import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow_recommendation import WorkflowRecommendation
from app.workflow_recommendation_builder import WorkflowRecommendationBuilder


def evidence(
    *,
    evidence_ref_id: str = "eref:workflow:1",
    source_id: str = "segment-1",
    support_level: str = "supports",
    confidence: float = 0.86,
    evidence_status: str = "active",
) -> dict[str, object]:
    return {
        "evidence_ref_id": evidence_ref_id,
        "source_type": "transcript_segment",
        "source_id": source_id,
        "meeting_id": "meeting-current",
        "supports": ["observed_state"],
        "support_level": support_level,
        "confidence": confidence,
        "evidence_status": evidence_status,
    }


def observation(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_id": "workflow:project_delivery:project-beta",
        "workflow_type": "project_delivery",
        "observed_state": "development_in_progress",
        "previous_state": "requirements_confirmed",
        "transition": {
            "from_state": "requirements_confirmed",
            "to_state": "development_in_progress",
            "transition_type": "forward",
            "reason": "Observed evidence indicates forward workflow progress.",
        },
        "evidence_refs": [evidence()],
        "confidence": 0.86,
        "requires_confirmation": False,
    }
    payload.update(overrides)
    return payload


class WorkflowRecommendationBuilderTest(unittest.TestCase):
    def test_dependency_recommendation_is_generated(self) -> None:
        recommendation = WorkflowRecommendationBuilder().build(
            observation=observation(),
            dependencies=[
                {
                    "dependency_id": "dep:release-check",
                    "from_ref": "task:qa",
                    "to_ref": "workflow:release",
                    "dependency_type": "blocks",
                    "status": "active",
                    "reason": "Release review is blocked by QA sign-off.",
                    "evidence_refs": ["eref:dep:qa"],
                    "confidence": 0.82,
                }
            ],
        )

        self.assertIsInstance(recommendation, WorkflowRecommendation)
        assert recommendation is not None
        self.assertEqual(recommendation.recommendation_type, "review_dependency")
        self.assertEqual(recommendation.workflow_id, "workflow:project_delivery:project-beta")
        self.assertTrue(recommendation.requires_confirmation)
        self.assertTrue(any(ref.evidence_ref_id == "eref:dep:qa" for ref in recommendation.evidence_refs))

    def test_evidence_refresh_is_generated_for_missing_evidence_blocker(self) -> None:
        recommendation = WorkflowRecommendationBuilder().build(
            observation=observation(
                observed_state="blocked",
                transition={
                    "from_state": "requirements_confirmed",
                    "to_state": "blocked",
                    "transition_type": "blocked",
                    "reason": "Observed evidence indicates a blocking condition.",
                },
            ),
            blockers=[
                {
                    "blocker_id": "blocker:missing-test-evidence",
                    "blocker_type": "missing_evidence",
                    "subject_ref": "workflow:project_delivery:project-beta",
                    "severity": "medium",
                    "reason": "Verification cannot be trusted without current QA evidence.",
                    "evidence_refs": ["eref:missing:qa"],
                    "confidence": 0.78,
                }
            ],
        )

        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertEqual(recommendation.recommendation_type, "refresh_evidence")
        self.assertFalse(recommendation.requires_confirmation)
        self.assertIn("QA evidence", recommendation.reason)

    def test_conflict_confirmation_is_generated(self) -> None:
        recommendation = WorkflowRecommendationBuilder().build(
            observation=observation(
                workflow_type="meeting_follow_up",
                observed_state="needs_review",
                previous_state="pending",
                transition={
                    "from_state": "pending",
                    "to_state": "needs_review",
                    "transition_type": "requires_confirmation",
                    "reason": "Observed evidence is conflicted or reviewable and requires confirmation.",
                },
                evidence_refs=[
                    evidence(evidence_ref_id="eref:pending", source_id="segment-pending"),
                    evidence(
                        evidence_ref_id="eref:done-conflict",
                        source_id="segment-done",
                        support_level="conflicts",
                        evidence_status="conflicted",
                    ),
                ],
                confidence=0.7,
                requires_confirmation=True,
            ),
            blockers=[
                {
                    "blocker_id": "blocker:owner-conflict",
                    "blocker_type": "conflicting_evidence",
                    "subject_ref": "task:follow-up",
                    "severity": "high",
                    "reason": "Two evidence records support incompatible follow-up states.",
                    "evidence_refs": ["eref:done-conflict"],
                    "confidence": 0.85,
                }
            ],
        )

        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertEqual(recommendation.recommendation_type, "request_confirmation")
        self.assertTrue(recommendation.requires_confirmation)
        self.assertTrue(any(ref.support_level == "conflicts" for ref in recommendation.evidence_refs))

    def test_no_action_is_generated_when_no_review_signal_exists(self) -> None:
        recommendation = WorkflowRecommendationBuilder().build(
            observation=observation(
                observed_state="ready_for_release",
                transition={
                    "from_state": "testing_in_progress",
                    "to_state": "ready_for_release",
                    "transition_type": "forward",
                    "reason": "Observed evidence indicates forward workflow progress.",
                },
                previous_state="testing_in_progress",
                confidence=0.91,
                evidence_refs=[
                    evidence(
                        evidence_ref_id="eref:release-ready",
                        source_id="segment-release",
                        confidence=0.91,
                    )
                ],
            ),
            blockers=[],
            dependencies=[],
        )

        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertEqual(recommendation.recommendation_type, "no_action")
        self.assertFalse(recommendation.requires_confirmation)
        self.assertGreaterEqual(recommendation.confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
