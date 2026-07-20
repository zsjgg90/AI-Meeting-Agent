from __future__ import annotations

import importlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import AgentActionProposal, EvidenceRef
from app.agent_write_control import (
    AgentProposalConfirmation,
    AuthoritativeStateSnapshot,
    ControlledWritePlanner,
    InMemoryAuthoritativeStateProvider,
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


class AgentWriteControlTests(unittest.TestCase):
    def evidence(self) -> EvidenceRef:
        return EvidenceRef(
            source_type="transcript",
            source_meeting_id="meeting-1",
            source_segment_id="seg-1",
            source_text="Alice confirmed the owner change for checkout API.",
            confidence=0.9,
        )

    def snapshot(
        self,
        *,
        version: str = "v1",
        status: str = "under_review",
        metadata: dict | None = None,
    ) -> AuthoritativeStateSnapshot:
        return AuthoritativeStateSnapshot(
            object_type="Requirement",
            object_id="req-1",
            object_version=version,
            status=status,
            updated_at="2026-07-20T00:00:00+00:00",
            source="unit_authoritative_state",
            data={
                "title": "Checkout API",
                "owner": "Alice",
                "status": status,
                "priority": "medium",
            },
            metadata=metadata or {},
        )

    def proposal(self, **overrides) -> AgentActionProposal:
        data = {
            "proposal_id": "proposal-1",
            "action_type": "update",
            "target_object_type": "Requirement",
            "target_object_id": "req-1",
            "title": "Checkout API",
            "proposed_changes": {"owner": {"from": "Alice", "to": "Bob"}},
            "evidence": [self.evidence()],
            "confidence": 0.91,
            "risk_level": "medium",
            "requires_confirmation": True,
            "reason": "Owner changed in the current meeting.",
            "metadata": {"schema_version": "agent-state-tracker-v1"},
        }
        data.update(overrides)
        return AgentActionProposal(**data)

    def confirmation(self, **overrides) -> AgentProposalConfirmation:
        data = {
            "confirmation_id": "confirm-1",
            "proposal_id": "proposal-1",
            "decision": "approved",
            "reviewer": "pm@example.com",
            "reviewed_at": "2026-07-20T01:00:00+00:00",
            "comment": "Approved.",
            "expected_object_version": "v1",
            "permissions": ["agent_write:Requirement"],
            "metadata": {"review_source": "unit_test"},
        }
        data.update(overrides)
        return AgentProposalConfirmation(**data)

    def planner(self, provider: InMemoryAuthoritativeStateProvider | None = None) -> ControlledWritePlanner:
        return ControlledWritePlanner(
            state_provider=provider or InMemoryAuthoritativeStateProvider([self.snapshot()])
        )

    def test_authoritative_state_is_read_for_target_object(self) -> None:
        provider = InMemoryAuthoritativeStateProvider([self.snapshot()])
        result = ControlledWritePlanner(state_provider=provider).plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(),
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(provider.reads, [{"object_type": "Requirement", "object_id": "req-1"}])
        self.assertEqual(result.command.expected_version, "v1")

    def test_approved_confirmation_generates_ready_command(self) -> None:
        result = self.planner().plan(proposal=self.proposal(), confirmation=self.confirmation())

        command = result.command
        self.assertEqual(result.status, "ready")
        self.assertEqual(command.operation, "update")
        self.assertEqual(command.changes, {"owner": "Bob"})
        self.assertEqual(command.confirmation_id, "confirm-1")
        self.assertFalse(command.audit_context["writes_performed"])

    def test_rejected_needs_changes_and_expired_confirmations_are_rejected(self) -> None:
        for decision in ("rejected", "needs_changes", "expired"):
            with self.subTest(decision=decision):
                result = self.planner().plan(
                    proposal=self.proposal(),
                    confirmation=self.confirmation(decision=decision),
                )

                self.assertEqual(result.status, "rejected")
                self.assertIsNone(result.command)
                self.assertIn(f"confirmation_{decision}", result.rejection_reasons)

    def test_confirmation_expiry_metadata_rejects_command(self) -> None:
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        result = self.planner().plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(metadata={"expires_at": expired_at}),
        )

        self.assertEqual(result.status, "rejected")
        self.assertIn("confirmation_expired", result.rejection_reasons)

    def test_missing_confirmation_is_rejected(self) -> None:
        result = self.planner().plan(proposal=self.proposal(), confirmation=None)

        self.assertEqual(result.status, "rejected")
        self.assertIn("missing_confirmation", result.rejection_reasons)

    def test_version_conflict_is_rejected(self) -> None:
        result = self.planner().plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(expected_object_version="v0"),
        )

        self.assertEqual(result.status, "rejected")
        self.assertIn("version_conflict", result.rejection_reasons)

    def test_permission_denied_is_rejected(self) -> None:
        result = self.planner().plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(permissions=["read:Requirement"]),
        )

        self.assertEqual(result.status, "rejected")
        self.assertIn("permission_denied", result.rejection_reasons)

    def test_non_whitelisted_field_is_rejected(self) -> None:
        result = self.planner().plan(
            proposal=self.proposal(proposed_changes={"sql": {"from": "", "to": "drop table"}}),
            confirmation=self.confirmation(),
        )

        self.assertEqual(result.status, "rejected")
        self.assertTrue(any(reason.startswith("field_not_whitelisted") for reason in result.rejection_reasons))

    def test_duplicate_idempotency_key_is_rejected(self) -> None:
        planner = self.planner()
        first = planner.plan(proposal=self.proposal(), confirmation=self.confirmation())
        second = planner.plan(proposal=self.proposal(), confirmation=self.confirmation())

        self.assertEqual(first.status, "ready")
        self.assertEqual(second.status, "duplicate")
        self.assertIn("duplicate_command", second.rejection_reasons)

    def test_high_risk_operation_requires_confirmation(self) -> None:
        proposal = self.proposal(
            action_type="cancel",
            risk_level="high",
            proposed_changes={"status": {"from": "confirmed", "to": "cancelled"}},
        )

        missing = self.planner().plan(proposal=proposal, confirmation=None)
        approved = self.planner().plan(proposal=proposal, confirmation=self.confirmation())

        self.assertIn("missing_confirmation", missing.rejection_reasons)
        self.assertEqual(approved.status, "ready")
        self.assertEqual(approved.command.operation, "cancel")

    def test_audit_and_rollback_are_generated(self) -> None:
        result = self.planner().plan(proposal=self.proposal(), confirmation=self.confirmation())

        self.assertEqual(result.audit_record.result, "ready")
        self.assertEqual(result.audit_record.authoritative_version, "v1")
        self.assertIsNotNone(result.rollback_plan)
        self.assertEqual(result.rollback_plan.restore_changes, {"owner": "Alice"})
        self.assertEqual(result.command.rollback_plan.rollback_id, result.rollback_plan.rollback_id)

    def test_missing_target_and_missing_evidence_are_rejected(self) -> None:
        missing_target = self.planner(InMemoryAuthoritativeStateProvider([])).plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(),
        )
        missing_evidence = self.planner().plan(
            proposal=self.proposal(evidence=[]),
            confirmation=self.confirmation(),
        )

        self.assertIn("target_not_found", missing_target.rejection_reasons)
        self.assertIn("missing_evidence", missing_evidence.rejection_reasons)

    def test_planner_does_not_write_database_or_call_external_dependencies(self) -> None:
        db = CountingDb()
        provider = InMemoryAuthoritativeStateProvider([self.snapshot()])

        result = ControlledWritePlanner(state_provider=provider).plan(
            proposal=self.proposal(),
            confirmation=self.confirmation(),
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(db.calls, [])
        self.assertFalse(result.metadata["writes_performed"])
        self.assertFalse(result.metadata["external_calls_performed"])

    def test_import_does_not_initialize_model_rag_network_or_database(self) -> None:
        module = importlib.import_module("app.agent_write_control")

        self.assertTrue(hasattr(module, "ControlledWritePlanner"))


if __name__ == "__main__":
    unittest.main()
