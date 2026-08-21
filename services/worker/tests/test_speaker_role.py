import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.speaker_identity import build_meeting_speaker_id
from app.speaker_role import (
    ManualRoleConfirmation,
    OrganizationRoleProfile,
    RoleResolver,
    SuggestedRole,
)


class SpeakerRoleTest(unittest.TestCase):
    def test_manual_role_has_highest_priority(self) -> None:
        resolver = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Product Manager",
                    confirmed_by="reviewer-1",
                )
            ],
            organization_profiles=[
                OrganizationRoleProfile(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Engineering Lead",
                )
            ],
            suggested_roles=[
                SuggestedRole(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="QA",
                )
            ],
        )

        context = resolver.resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        self.assertEqual(context.confirmed_role, "Product Manager")
        self.assertIsNone(context.suggested_role)
        self.assertEqual(context.role_status, "confirmed")
        self.assertEqual(context.role_source, "manual_confirmation")
        self.assertEqual(context.evidence[0].confirmed_by, "reviewer-1")

    def test_organization_role_is_second_priority(self) -> None:
        resolver = RoleResolver(
            organization_profiles=[
                OrganizationRoleProfile(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Engineering Lead",
                    person_id="person-1",
                )
            ],
            suggested_roles=[
                SuggestedRole(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="QA",
                )
            ],
        )

        context = resolver.resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        self.assertEqual(context.confirmed_role, "Engineering Lead")
        self.assertIsNone(context.suggested_role)
        self.assertEqual(context.role_status, "confirmed")
        self.assertEqual(context.role_source, "organization_profile")
        self.assertEqual(context.evidence[0].person_id, "person-1")

    def test_suggestion_does_not_override_confirmed_role(self) -> None:
        speaker_id = build_meeting_speaker_id("meeting-1", "speaker_2")
        resolver = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    speaker_id=speaker_id,
                    role="Customer Representative",
                )
            ],
            suggested_roles=[
                SuggestedRole(
                    speaker_id=speaker_id,
                    role="Project Manager",
                    metadata={"signal": "not transcript-confirmed"},
                )
            ],
        )

        context = resolver.resolve(speaker_id=speaker_id)

        self.assertEqual(context.confirmed_role, "Customer Representative")
        self.assertIsNone(context.suggested_role)
        self.assertEqual(context.role_status, "confirmed")
        self.assertEqual(context.role_source, "manual_confirmation")
        self.assertEqual(len(context.evidence), 1)

    def test_suggested_role_returns_unconfirmed_context(self) -> None:
        resolver = RoleResolver(
            suggested_roles=[
                SuggestedRole(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Project Manager",
                    confidence=0.55,
                )
            ]
        )

        context = resolver.resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        self.assertIsNone(context.confirmed_role)
        self.assertEqual(context.suggested_role, "Project Manager")
        self.assertEqual(context.role_status, "suggested")
        self.assertEqual(context.role_source, "suggested_role")
        self.assertEqual(context.confidence, 0.55)
        self.assertTrue(context.evidence[0].metadata["requires_confirmation"])

    def test_unknown_role_returns_empty_context(self) -> None:
        context = RoleResolver().resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        self.assertEqual(context.speaker_id, "meeting:meeting-1:speaker_1")
        self.assertIsNone(context.confirmed_role)
        self.assertIsNone(context.suggested_role)
        self.assertEqual(context.role_status, "unknown")
        self.assertEqual(context.role_source, "unknown")
        self.assertEqual(context.confidence, 0.0)
        self.assertEqual(context.evidence, [])

    def test_role_records_require_explicit_target(self) -> None:
        with self.assertRaises(ValidationError):
            ManualRoleConfirmation(role="Product Manager")
        with self.assertRaises(ValidationError):
            OrganizationRoleProfile(role="Engineering Lead")
        with self.assertRaises(ValidationError):
            SuggestedRole(role="QA")


if __name__ == "__main__":
    unittest.main()
