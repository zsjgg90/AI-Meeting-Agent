import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.action_proposal_engine import ActionCandidate, ActionProposalEngine
from app.reasoning_engine import EvidenceRef, ImpactScope, ReasoningContext, SuggestedNextStep
from app.responsibility_evidence_matrix import ResponsibilityCandidate, ResponsibilityEvidenceMatrix, ResponsibilityEvidenceMatrixRow
from app.responsibility_extractor import ResponsibilityEvidence


def reasoning_context(
    *,
    reasoning_type: str = "risk_assessment",
    support_level: str = "supports",
    evidence_status: str = "active",
) -> ReasoningContext:
    return ReasoningContext(
        reasoning_id=f"reason:{reasoning_type}:login-risk",
        reasoning_type=reasoning_type,
        claim="Login API instability may block beta release.",
        evidence_refs=[
            EvidenceRef(
                evidence_ref_id="eref:login-risk",
                source_type="transcript_segment",
                source_id="segment-4",
                meeting_id="meeting-current",
                supported_claim_parts=["risk_subject", "impact"],
                support_level=support_level,
                confidence=0.86,
                evidence_status=evidence_status,
            )
        ],
        confidence=0.86,
        impact_scope=ImpactScope(
            project_id="project-beta",
            meeting_ids=["meeting-current"],
            affected_risks=["mem:meeting:login-risk"],
            time_horizon="near_term",
        ),
        requires_confirmation=support_level == "conflicts",
        suggested_next_step=SuggestedNextStep(
            step_type="human_review",
            text="Review risk evidence.",
            target_refs=["mem:meeting:login-risk"],
            blocked_actions=["notify_owner", "create_task"],
        ),
    )


def responsibility_evidence(*, requires_confirmation: bool = False) -> ResponsibilityEvidence:
    return ResponsibilityEvidence(
        type="explicit_owner_text",
        source_type="transcript",
        meeting_id="meeting-current",
        segment_id="segment-8",
        source_text="Alice owns preparing the launch checklist.",
        owner_text="Alice",
        task_text="Prepare launch checklist",
        supported_fields=["task", "owner"],
        confidence=0.88,
        requires_confirmation=requires_confirmation,
    )


class ActionProposalEngineTest(unittest.TestCase):
    def test_risk_reasoning_proposes_confirmation(self) -> None:
        result = ActionProposalEngine().generate(
            reasoning_contexts=[reasoning_context()],
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertIsInstance(candidate, ActionCandidate)
        self.assertEqual(candidate.action_type, "request_confirmation")
        self.assertTrue(candidate.action_id.startswith("action:request_confirmation:"))
        self.assertEqual(candidate.target.target_type, "risk_review")
        self.assertEqual(candidate.target.target_id, "reason:risk_assessment:login-risk")
        self.assertEqual(candidate.reason.risk_or_gap, "risk_reasoning")
        self.assertEqual(candidate.evidence_refs[0].source_id, "segment-4")
        self.assertEqual(candidate.permission_state.state, "proposal_only")
        self.assertTrue(candidate.requires_confirmation)

    def test_confirmed_responsibility_only_proposes_create_task(self) -> None:
        matrix = ResponsibilityEvidenceMatrix(
            rows=[
                ResponsibilityEvidenceMatrixRow(
                    task_key="task:launch-checklist",
                    action_owner=None,
                    responsibility_candidates=[
                        ResponsibilityCandidate(
                            responsibility_id="resp:meeting-current:segment-8:alice",
                            responsibility_type="explicit_owner",
                            task="Prepare launch checklist",
                            owner="Alice",
                            confidence=0.88,
                            requires_confirmation=False,
                        )
                    ],
                    evidence=[responsibility_evidence()],
                    confidence=0.88,
                    consistency_status="responsibility_only",
                )
            ]
        )

        result = ActionProposalEngine().generate(
            responsibility_matrix=matrix,
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.action_type, "create_task")
        self.assertTrue(candidate.action_id.startswith("action:create_task:"))
        self.assertEqual(candidate.target.target_type, "task")
        self.assertEqual(candidate.target.target_label, "Prepare launch checklist")
        self.assertEqual(candidate.target.owner_candidate, "Alice")
        self.assertEqual(candidate.reason.risk_or_gap, "responsibility_only")
        self.assertEqual(candidate.permission_state.state, "blocked_pending_confirmation")
        self.assertIn("task:create", candidate.permission_state.required_permissions)
        self.assertTrue(candidate.requires_confirmation)
        self.assertEqual(candidate.evidence_refs[0].support_level, "supports")

    def test_conflicting_responsibility_proposes_confirmation(self) -> None:
        matrix = ResponsibilityEvidenceMatrix(
            rows=[
                ResponsibilityEvidenceMatrixRow(
                    task_key="task:launch-checklist",
                    action_owner="Bob",
                    responsibility_candidates=[
                        ResponsibilityCandidate(
                            responsibility_id="resp:meeting-current:segment-8:alice",
                            responsibility_type="explicit_owner",
                            task="Prepare launch checklist",
                            owner="Alice",
                            confidence=0.88,
                            requires_confirmation=False,
                        )
                    ],
                    evidence=[responsibility_evidence()],
                    confidence=0.88,
                    consistency_status="owner_conflict",
                )
            ]
        )

        result = ActionProposalEngine().generate(
            responsibility_matrix=matrix,
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.action_type, "request_confirmation")
        self.assertEqual(candidate.target.target_type, "responsibility_conflict")
        self.assertEqual(candidate.reason.risk_or_gap, "responsibility_conflict")
        self.assertTrue(any(ref.support_level == "conflicts" for ref in candidate.evidence_refs))
        self.assertEqual(candidate.permission_state.allowed_next_step, "show_for_review")
        self.assertTrue(candidate.requires_confirmation)

    def test_no_evidence_is_rejected(self) -> None:
        result = ActionProposalEngine().generate(
            memory_context={
                "memories": [
                    {
                        "memory_id": "mem:meeting:unsupported",
                        "content": {"text": "Create a launch task."},
                        "evidence": [],
                    }
                ]
            },
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
