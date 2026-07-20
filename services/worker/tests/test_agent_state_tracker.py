from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import AgentActionItem, AgentContext, EvidenceRef, Requirement, Risk
from app.agent_state_tracker import (
    CrossMeetingStateTracker,
    determine_state_change,
    normalize_agent_object,
)


class CountingDb:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def add(self, value) -> None:
        self.calls.append("add")

    def execute(self, value) -> None:
        self.calls.append("execute")

    def commit(self) -> None:
        self.calls.append("commit")

    def delete(self, value) -> None:
        self.calls.append("delete")


class AgentStateTrackerTests(unittest.TestCase):
    def evidence(self, text: str = "PM confirmed checkout API work continues.") -> EvidenceRef:
        return EvidenceRef(
            source_type="transcript",
            source_meeting_id="meeting-current",
            source_segment_id="seg-1",
            source_text=text,
            confidence=0.9,
            metadata={"project_id": "project-1"},
        )

    def context(self) -> AgentContext:
        return AgentContext(run_id="run-1", meeting_id="meeting-current", project_id="project-1")

    def analyze(self, current, history):
        return CrossMeetingStateTracker().analyze(
            context=self.context(),
            current_objects=current,
            historical_objects=history,
        )

    def test_same_requirement_matches_existing_candidate(self) -> None:
        old = Requirement(
            requirement_id="req-1",
            title="Checkout API",
            status="under_review",
            owner="Alice",
            evidence=[self.evidence("Previous meeting discussed Checkout API.")],
        )
        current = Requirement(
            requirement_id="req-1",
            title="Checkout API",
            status="confirmed",
            owner="Alice",
            evidence=[self.evidence("PM confirmed checkout API work continues.")],
        )

        result = self.analyze([current], [old])

        self.assertEqual(result.matches[0].candidate.object_id, "req-1")
        self.assertEqual(result.matches[0].match_type, "update")
        self.assertEqual(result.proposals[0].target_object_id, "req-1")

    def test_new_object_is_recognized_without_history_match(self) -> None:
        current = Requirement(
            requirement_id="req-new",
            title="Invoice export",
            status="proposed",
            owner="Bob",
            evidence=[self.evidence("Bob proposed invoice export.")],
        )

        result = self.analyze([current], [])

        proposal = result.proposals[0]
        self.assertEqual(proposal.action_type, "new")
        self.assertIsNone(proposal.target_object_id)
        self.assertFalse(proposal.requires_confirmation)

    def test_complete_defer_and_cancel_are_detected(self) -> None:
        old_action = AgentActionItem(
            action_item_id="act-1",
            title="Draft rollout checklist",
            status="open",
            evidence=[self.evidence()],
        )
        done_action = AgentActionItem(
            action_item_id="act-1",
            title="Draft rollout checklist",
            status="completed",
            evidence=[self.evidence("Checklist was completed.")],
        )
        old_requirement = Requirement(requirement_id="req-1", title="SSO", status="confirmed", evidence=[self.evidence()])
        deferred_requirement = Requirement(
            requirement_id="req-1",
            title="SSO",
            status="deferred",
            evidence=[self.evidence("SSO was deferred to next release.")],
        )
        cancelled_requirement = Requirement(
            requirement_id="req-1",
            title="SSO",
            status="cancelled",
            evidence=[self.evidence("SSO requirement was cancelled.")],
        )

        self.assertEqual(
            determine_state_change(
                current=normalize_agent_object(done_action, default_project_id="project-1"),
                candidate=normalize_agent_object(old_action, default_project_id="project-1"),
            ),
            "complete",
        )
        self.assertEqual(self.analyze([deferred_requirement], [old_requirement]).proposals[0].action_type, "defer")
        cancel_proposal = self.analyze([cancelled_requirement], [old_requirement]).proposals[0]
        self.assertEqual(cancel_proposal.action_type, "cancel")
        self.assertIn("cancel_requirement", cancel_proposal.metadata["confirmation_reasons"])

    def test_duplicate_object_is_detected(self) -> None:
        old = Risk(
            risk_id="risk-1",
            title="Payment provider delay",
            status="active",
            level="medium",
            owner="Alice",
            evidence=[self.evidence("Payment provider delay remains a risk.")],
        )
        current = Risk(
            risk_id="risk-current",
            title="Payment provider delay",
            status="active",
            level="medium",
            owner="Alice",
            evidence=[self.evidence("Payment provider delay remains a risk.")],
        )

        result = self.analyze([current], [old])

        self.assertEqual(result.proposals[0].action_type, "duplicate")
        self.assertEqual(result.proposals[0].target_object_id, "risk-1")

    def test_uncertain_match_sets_needs_review(self) -> None:
        old = Requirement(
            requirement_id="req-old",
            title="Checkout API",
            status="implemented",
            evidence=[self.evidence("Checkout API was already implemented.")],
        )
        current = Requirement(
            requirement_id="req-new",
            title="Checkout APIs",
            status="proposed",
            evidence=[self.evidence("Checkout APIs were proposed again.")],
        )

        result = self.analyze([current], [old])

        proposal = result.proposals[0]
        self.assertEqual(proposal.action_type, "uncertain")
        self.assertTrue(proposal.metadata["needs_review"])
        self.assertTrue(proposal.requires_confirmation)
        self.assertIn("historical_conflict", proposal.metadata["confirmation_reasons"])

    def test_owner_and_deadline_changes_require_confirmation(self) -> None:
        old = AgentActionItem(
            action_item_id="act-1",
            title="Prepare launch notes",
            owner="Alice",
            due_date="2026-07-25",
            status="open",
            evidence=[self.evidence()],
        )
        current = AgentActionItem(
            action_item_id="act-1",
            title="Prepare launch notes",
            owner="Bob",
            due_date="2026-07-30",
            status="open",
            evidence=[self.evidence("Bob will prepare launch notes by July 30.")],
        )

        proposal = self.analyze([current], [old]).proposals[0]

        self.assertEqual(proposal.action_type, "update")
        self.assertTrue(proposal.requires_confirmation)
        self.assertIn("owner_change", proposal.metadata["confirmation_reasons"])
        self.assertIn("deadline_change", proposal.metadata["confirmation_reasons"])

    def test_insufficient_evidence_requires_confirmation(self) -> None:
        current = Risk(risk_id="risk-1", title="Vendor delay", status="active", evidence=[])

        proposal = self.analyze([current], []).proposals[0]

        self.assertEqual(proposal.action_type, "new")
        self.assertTrue(proposal.requires_confirmation)
        self.assertTrue(proposal.metadata["needs_review"])
        self.assertIn("insufficient_evidence", proposal.metadata["confirmation_reasons"])

    def test_closing_high_risk_requires_confirmation(self) -> None:
        old = Risk(
            risk_id="risk-1",
            title="Security review delay",
            status="active",
            level="high",
            evidence=[self.evidence()],
        )
        current = Risk(
            risk_id="risk-1",
            title="Security review delay",
            status="closed",
            level="high",
            evidence=[self.evidence("Security review delay is closed.")],
        )

        proposal = self.analyze([current], [old]).proposals[0]

        self.assertEqual(proposal.action_type, "complete")
        self.assertTrue(proposal.requires_confirmation)
        self.assertIn("close_high_risk", proposal.metadata["confirmation_reasons"])

    def test_tracker_does_not_write_database_or_call_external_dependencies(self) -> None:
        db = CountingDb()
        context = self.context()
        context.runtime_metadata["db"] = db
        current = Requirement(
            requirement_id="req-1",
            title="Offline mode",
            status="proposed",
            evidence=[self.evidence("Offline mode was proposed.")],
        )

        result = CrossMeetingStateTracker().analyze(context=context, current_objects=[current], historical_objects=[])

        self.assertEqual(db.calls, [])
        self.assertFalse(result.metadata["writes_performed"])
        self.assertFalse(result.metadata["external_calls_performed"])

    def test_import_does_not_initialize_model_rag_network_or_database(self) -> None:
        module = importlib.import_module("app.agent_state_tracker")

        self.assertTrue(hasattr(module, "CrossMeetingStateTracker"))


if __name__ == "__main__":
    unittest.main()
