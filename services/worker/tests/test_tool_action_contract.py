import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.action_proposal_engine import ActionProposalEngine
from app.responsibility_evidence_matrix import ResponsibilityCandidate, ResponsibilityEvidenceMatrix, ResponsibilityEvidenceMatrixRow
from app.responsibility_extractor import ResponsibilityEvidence
from app.tool_action_contract import ToolActionContractBuilder, action_shadow_audit_payload


def responsibility_evidence() -> ResponsibilityEvidence:
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
        requires_confirmation=False,
    )


class ToolActionContractTest(unittest.TestCase):
    def test_create_task_candidate_maps_to_blocked_tool_contract(self) -> None:
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
        candidates = ActionProposalEngine().generate(
            responsibility_matrix=matrix,
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        contracts = ToolActionContractBuilder().build(candidates)
        audit = action_shadow_audit_payload(meeting_id="meeting-current", candidates=candidates, contracts=contracts)

        self.assertEqual(len(contracts), 1)
        contract = contracts[0]
        self.assertEqual(contract.tool_id, "task.create")
        self.assertEqual(contract.action_id, candidates[0].action_id)
        self.assertIn("task:create", contract.required_permissions)
        self.assertIn("audit:write", contract.required_permissions)
        self.assertTrue(contract.confirmation_required)
        self.assertEqual(contract.execution_mode, "disabled")
        self.assertIn("writes_disabled", contract.blocked_reason)
        self.assertFalse(audit["execution_attempted"])
        self.assertFalse(audit["writes_performed"])
        self.assertEqual(audit["candidate_count"], 1)
        self.assertEqual(audit["contract_count"], 1)


if __name__ == "__main__":
    unittest.main()
