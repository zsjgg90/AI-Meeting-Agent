import unittest
from pathlib import Path
import sys

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import (
    AGENT_CONTRACT_SCHEMA_VERSION,
    AgentActionItem,
    AgentActionProposal,
    AgentContext,
    CustomerRequest,
    Decision,
    Dependency,
    EvidenceRef,
    Issue,
    Milestone,
    ProjectState,
    Requirement,
    Risk,
)
from app.meeting_analysis_schema import MeetingAnalysisSchema


class AgentContractTest(unittest.TestCase):
    def evidence(self) -> EvidenceRef:
        return EvidenceRef(
            source_type="transcript",
            source_meeting_id="meeting-1",
            source_segment_id="seg-1",
            source_text="Product confirms checkout refactor for v1.2.",
            start_time=1.0,
            end_time=3.5,
            speaker="PM",
            confidence=0.88,
            metadata={"utterance_id": "utt-1"},
        )

    def assert_round_trip(self, value) -> None:
        dumped = value.model_dump(mode="json")
        loaded = value.__class__.model_validate(dumped)

        self.assertEqual(loaded.model_dump(mode="json"), dumped)

    def test_core_business_objects_round_trip(self) -> None:
        evidence = self.evidence()
        objects = [
            Requirement(requirement_id="req-1", title="Checkout refactor", source_meeting_id="meeting-1", evidence=[evidence]),
            Decision(decision_id="dec-1", topic="Scope", decision="Freeze checkout scope", evidence=[evidence]),
            AgentActionItem(action_item_id="act-1", title="Draft API contract", evidence=[evidence]),
            Issue(issue_id="iss-1", title="API timing unclear", evidence=[evidence]),
            Risk(risk_id="risk-1", title="Late API delivery", evidence=[evidence]),
            Dependency(dependency_id="dep-1", upstream_object_id="req-1", downstream_object_id="act-1", evidence=[evidence]),
            Milestone(milestone_id="mile-1", title="v1.2 release", evidence=[evidence]),
            CustomerRequest(customer_request_id="cust-1", title="SSO support", evidence=[evidence]),
            ProjectState(project_id="project-1"),
            AgentActionProposal(proposal_id="prop-1", title="Create action item", evidence=[evidence]),
        ]

        for value in objects:
            with self.subTest(model=value.__class__.__name__):
                self.assert_round_trip(value)

    def test_required_status_enums_reject_invalid_values(self) -> None:
        with self.assertRaises(ValidationError):
            Requirement(status="done")

        with self.assertRaises(ValidationError):
            AgentActionItem(status="todo")

        with self.assertRaises(ValidationError):
            Risk(level="severe")

        with self.assertRaises(ValidationError):
            Risk(status="watching")

    def test_evidence_confidence_allows_none_and_rejects_out_of_range(self) -> None:
        self.assertIsNone(EvidenceRef(source_type="manual").confidence)

        with self.assertRaises(ValidationError):
            EvidenceRef(source_type="manual", confidence=-0.1)

        with self.assertRaises(ValidationError):
            EvidenceRef(source_type="manual", confidence=1.1)

    def test_evidence_source_type_rejects_unknown_enum_values(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceRef(source_type="email")

    def test_all_business_objects_share_evidence_ref_structure(self) -> None:
        evidence = self.evidence()

        objects = [
            Requirement(evidence=[evidence]),
            Decision(evidence=[evidence]),
            AgentActionItem(evidence=[evidence]),
            Issue(evidence=[evidence]),
            Risk(evidence=[evidence]),
            Dependency(evidence=[evidence]),
            Milestone(evidence=[evidence]),
            CustomerRequest(evidence=[evidence]),
            AgentActionProposal(evidence=[evidence]),
        ]

        for value in objects:
            with self.subTest(model=value.__class__.__name__):
                self.assertIsInstance(value.evidence[0], EvidenceRef)
                self.assertEqual(value.evidence[0].source_type, "transcript")

    def test_mutable_defaults_do_not_leak_between_instances(self) -> None:
        first = Requirement()
        second = Requirement()

        first.evidence.append(self.evidence())

        self.assertEqual(len(first.evidence), 1)
        self.assertEqual(second.evidence, [])

        first_context = AgentContext()
        second_context = AgentContext()
        first_context.requirements.append(first)
        first_context.runtime_metadata["trace_id"] = "trace-1"

        self.assertEqual(second_context.requirements, [])
        self.assertNotIn("trace_id", second_context.runtime_metadata)

    def test_agent_context_runtime_metadata_defaults_and_merges(self) -> None:
        default_context = AgentContext()
        self.assertEqual(default_context.runtime_metadata["schema_version"], AGENT_CONTRACT_SCHEMA_VERSION)

        context = AgentContext(runtime_metadata={"schema_version": "bad-version", "trace_id": "trace-1"})

        self.assertEqual(context.runtime_metadata["schema_version"], AGENT_CONTRACT_SCHEMA_VERSION)
        self.assertEqual(context.runtime_metadata["trace_id"], "trace-1")

    def test_agent_context_keeps_transcript_and_meeting_analysis_loose(self) -> None:
        context = AgentContext(
            transcript=[{"speaker": "PM", "text": "Confirm scope."}],
            meeting_analysis={"meeting_summary": "Scope confirmed."},
            project_state={"project_id": "project-1", "health": "normal"},
            requirements=[Requirement(title="Checkout")],
            decisions=[Decision(decision="Freeze scope")],
            action_proposals=[AgentActionProposal(title="Update requirement")],
        )

        dumped = context.model_dump(mode="json")
        loaded = AgentContext.model_validate(dumped)

        self.assertEqual(loaded.transcript[0]["text"], "Confirm scope.")
        self.assertEqual(loaded.meeting_analysis["meeting_summary"], "Scope confirmed.")
        self.assertEqual(loaded.runtime_metadata["schema_version"], AGENT_CONTRACT_SCHEMA_VERSION)

    def test_agent_contract_import_does_not_change_meeting_analysis_schema(self) -> None:
        analysis = MeetingAnalysisSchema(meeting_summary="Formal result remains unchanged.")

        self.assertEqual(analysis.metadata.schema_version, "meeting-analysis-v1")
        self.assertEqual(analysis.meeting_summary, "Formal result remains unchanged.")
        self.assertFalse(hasattr(analysis, "requirements"))


if __name__ == "__main__":
    unittest.main()
