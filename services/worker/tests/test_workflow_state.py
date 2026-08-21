import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow_state import WorkflowStateObservation
from app.workflow_state_builder import WorkflowStateObservationBuilder


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


class WorkflowStateObservationBuilderTest(unittest.TestCase):
    def test_project_delivery_state_observation_is_generated(self) -> None:
        observation = WorkflowStateObservationBuilder().build(
            workflow_context={
                "workflow_id": "workflow:project_delivery:project-beta",
                "workflow_type": "project_delivery",
                "states": [
                    {
                        "state_id": "state:workflow:development",
                        "state_value": "development_in_progress",
                        "evidence_refs": ["eref:workflow:1"],
                        "confidence": 0.84,
                    }
                ],
                "evidence_refs": [evidence()],
                "confidence": 0.84,
            }
        )

        self.assertIsInstance(observation, WorkflowStateObservation)
        assert observation is not None
        self.assertEqual(observation.workflow_type, "project_delivery")
        self.assertEqual(observation.observed_state, "development_in_progress")
        self.assertIsNone(observation.previous_state)
        self.assertEqual(observation.transition.transition_type, "no_previous_state")
        self.assertEqual(observation.evidence_refs[0].evidence_ref_id, "eref:workflow:1")
        self.assertFalse(observation.requires_confirmation)

    def test_transition_is_identified_from_previous_state(self) -> None:
        observation = WorkflowStateObservationBuilder().build(
            workflow_context={
                "workflow_id": "workflow:project_delivery:project-beta",
                "workflow_type": "project_delivery",
                "previous_state": "requirements_confirmed",
                "observed_state": "testing_in_progress",
                "evidence_refs": [
                    evidence(
                        evidence_ref_id="eref:workflow:testing",
                        source_id="segment-testing",
                        confidence=0.9,
                    )
                ],
                "confidence": 0.9,
            }
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.previous_state, "requirements_confirmed")
        self.assertEqual(observation.observed_state, "testing_in_progress")
        self.assertEqual(observation.transition.from_state, "requirements_confirmed")
        self.assertEqual(observation.transition.to_state, "testing_in_progress")
        self.assertEqual(observation.transition.transition_type, "forward")

    def test_no_evidence_is_rejected(self) -> None:
        observation = WorkflowStateObservationBuilder().build(
            workflow_context={
                "workflow_id": "workflow:issue_resolution:login-api",
                "workflow_type": "issue_resolution",
                "observed_state": "investigating",
                "evidence_refs": [],
                "confidence": 0.8,
            }
        )

        self.assertIsNone(observation)

    def test_conflict_requires_confirmation(self) -> None:
        observation = WorkflowStateObservationBuilder().build(
            workflow_context={
                "workflow_id": "workflow:meeting_follow_up:launch",
                "workflow_type": "meeting_follow_up",
                "previous_state": "pending",
                "states": [
                    {"state_value": "pending", "confidence": 0.82},
                    {"state_value": "completed_candidate", "confidence": 0.83},
                ],
                "evidence_refs": [
                    evidence(
                        evidence_ref_id="eref:pending",
                        source_id="segment-pending",
                        support_level="supports",
                        confidence=0.82,
                    ),
                    evidence(
                        evidence_ref_id="eref:done-conflict",
                        source_id="segment-done",
                        support_level="conflicts",
                        confidence=0.83,
                        evidence_status="conflicted",
                    ),
                ],
                "confidence": 0.82,
            }
        )

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.observed_state, "needs_review")
        self.assertTrue(observation.requires_confirmation)
        self.assertEqual(observation.transition.transition_type, "requires_confirmation")
        self.assertTrue(any(ref.support_level == "conflicts" for ref in observation.evidence_refs))


if __name__ == "__main__":
    unittest.main()
