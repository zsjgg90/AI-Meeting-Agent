from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import EvidenceRef, MeetingType
from app.meeting_analysis_schema import MeetingAnalysisSchema
from app.meeting_scenarios import (
    MEETING_SCENARIO_POLICY_SCHEMA_VERSION,
    MeetingClassificationResult,
    MeetingScenarioPolicy,
    MeetingScenarioRegistry,
    get_policy,
    has_policy,
    list_policies,
)


EXPECTED_MEETING_TYPES: set[MeetingType] = {
    "requirement_review",
    "project_weekly",
    "technical_review",
    "version_planning",
    "cross_department",
    "project_retrospective",
    "management_decision",
    "customer_requirement",
    "unknown",
}


class MeetingScenarioPolicyTests(unittest.TestCase):
    def test_all_formal_scenarios_and_unknown_load(self) -> None:
        policies = list_policies()
        self.assertEqual(
            {policy.meeting_type for policy in policies},
            EXPECTED_MEETING_TYPES,
        )
        self.assertTrue(has_policy("unknown"))

    def test_registry_returns_expected_policy(self) -> None:
        policy = get_policy("project_weekly")

        self.assertEqual(policy.meeting_type, "project_weekly")
        self.assertEqual(policy.display_name, "项目周会")
        self.assertIn("project_state", policy.required_context)

    def test_duplicate_registration_fails(self) -> None:
        policy = get_policy("requirement_review")

        with self.assertRaises(ValueError):
            MeetingScenarioRegistry((policy, policy))

    def test_invalid_meeting_type_does_not_silently_load(self) -> None:
        with self.assertRaises(KeyError):
            get_policy("standup")  # type: ignore[arg-type]

        self.assertFalse(has_policy("standup"))  # type: ignore[arg-type]

    def test_each_policy_has_unique_meeting_type(self) -> None:
        meeting_types = [policy.meeting_type for policy in list_policies()]

        self.assertEqual(len(meeting_types), len(set(meeting_types)))

    def test_each_policy_has_at_least_one_focus_entity(self) -> None:
        for policy in list_policies():
            self.assertGreater(
                len(policy.focus_entities),
                0,
                msg=policy.meeting_type,
            )

    def test_required_and_optional_context_do_not_overlap(self) -> None:
        for policy in list_policies():
            overlap = set(policy.required_context) & set(policy.optional_context)
            self.assertEqual(overlap, set(), msg=policy.meeting_type)

    def test_confirmation_actions_are_allowed_action_subset(self) -> None:
        for policy in list_policies():
            confirmation_actions = set(policy.confirmation_required_actions)
            allowed_actions = set(policy.allowed_actions)
            self.assertTrue(
                confirmation_actions <= allowed_actions,
                msg=policy.meeting_type,
            )

    def test_policies_round_trip_serialization(self) -> None:
        for policy in list_policies():
            payload = policy.model_dump(mode="json")
            restored = MeetingScenarioPolicy.model_validate(payload)
            self.assertEqual(restored, policy)
            self.assertEqual(
                restored.schema_version,
                MEETING_SCENARIO_POLICY_SCHEMA_VERSION,
            )

    def test_classification_result_confidence_bounds(self) -> None:
        self.assertIsNone(MeetingClassificationResult(confidence=None).confidence)
        self.assertEqual(MeetingClassificationResult(confidence=0.0).confidence, 0.0)
        self.assertEqual(MeetingClassificationResult(confidence=1.0).confidence, 1.0)

        with self.assertRaises(ValidationError):
            MeetingClassificationResult(confidence=-0.01)

        with self.assertRaises(ValidationError):
            MeetingClassificationResult(confidence=1.01)

    def test_invalid_classification_source_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            MeetingClassificationResult(source="user")  # type: ignore[arg-type]

    def test_unknown_policy_uses_safe_defaults(self) -> None:
        policy = get_policy("unknown")

        self.assertTrue(policy.needs_review)
        self.assertEqual(policy.required_context, ())
        self.assertNotIn("project_state", policy.allowed_actions)
        self.assertNotIn("update_project_health", policy.allowed_actions)
        self.assertEqual(policy.confirmation_required_actions, ())

    def test_import_does_not_change_formal_meeting_analysis_schema(self) -> None:
        before = MeetingAnalysisSchema().model_dump()

        importlib.import_module("app.meeting_scenarios.registry")

        after = MeetingAnalysisSchema().model_dump()
        self.assertEqual(after, before)

    def test_mutable_defaults_do_not_leak_between_instances(self) -> None:
        left = MeetingClassificationResult(
            evidence=[
                EvidenceRef(
                    source_type="manual",
                    source_text="manual meeting type selection placeholder",
                )
            ],
            metadata={"source": "left"},
        )
        right = MeetingClassificationResult()

        self.assertEqual(len(left.evidence), 1)
        self.assertEqual(right.evidence, [])
        self.assertEqual(right.metadata, {})

    def test_policy_is_immutable(self) -> None:
        policy = get_policy("customer_requirement")

        with self.assertRaises(ValidationError):
            policy.display_name = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
