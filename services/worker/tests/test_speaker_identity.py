import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.speaker_identity import (
    ManualSpeakerConfirmation,
    SpeakerResolver,
    build_meeting_speaker_id,
    parse_meeting_speaker_id,
)


class SpeakerIdentityTest(unittest.TestCase):
    def test_unknown_context_uses_label_without_evidence(self) -> None:
        context = SpeakerResolver().resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        self.assertEqual(context.speaker_id, "meeting:meeting-1:speaker_1")
        self.assertEqual(context.speaker_label, "speaker_1")
        self.assertEqual(context.display_name, "speaker_1")
        self.assertIsNone(context.role)
        self.assertIsNone(context.department)
        self.assertEqual(context.confidence, 0.0)
        self.assertEqual(context.identity_source, "unknown")
        self.assertEqual(context.identity_status, "anonymous")
        self.assertEqual(context.evidence, [])

    def test_manual_confirmation_by_speaker_id_creates_confirmed_context(self) -> None:
        speaker_id = build_meeting_speaker_id("meeting-1", "speaker_1")
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    speaker_id=speaker_id,
                    display_name="Zhang San",
                    role="Product Manager",
                    department="Product",
                    confirmed_by="reviewer-1",
                    metadata={"source_record_id": "confirm-1"},
                )
            ]
        )

        context = resolver.resolve(speaker_id=speaker_id)

        self.assertEqual(context.display_name, "Zhang San")
        self.assertEqual(context.role, "Product Manager")
        self.assertEqual(context.department, "Product")
        self.assertEqual(context.confidence, 1.0)
        self.assertEqual(context.identity_source, "manual_confirmation")
        self.assertEqual(context.identity_status, "confirmed")
        self.assertEqual(len(context.evidence), 1)
        evidence = context.evidence[0]
        self.assertEqual(evidence.type, "manual_confirmation")
        self.assertEqual(evidence.source, "manual_confirmation")
        self.assertEqual(evidence.speaker_id, speaker_id)
        self.assertEqual(evidence.speaker_label, "speaker_1")
        self.assertEqual(evidence.meeting_id, "meeting-1")
        self.assertEqual(evidence.display_name, "Zhang San")
        self.assertEqual(evidence.confirmed_by, "reviewer-1")
        self.assertEqual(evidence.metadata["source_record_id"], "confirm-1")

    def test_manual_confirmation_by_meeting_and_label_creates_confirmed_context(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="Speaker A",
                    display_name="Li Si",
                    confidence=0.95,
                    note="confirmed in review",
                )
            ]
        )

        context = resolver.resolve(meeting_id="meeting-1", speaker_label="Speaker A")

        self.assertEqual(context.speaker_id, "meeting:meeting-1:Speaker A")
        self.assertEqual(context.display_name, "Li Si")
        self.assertEqual(context.confidence, 0.95)
        self.assertEqual(context.evidence[0].metadata["note"], "confirmed in review")

    def test_manual_confirmation_requires_explicit_target(self) -> None:
        with self.assertRaises(ValidationError):
            ManualSpeakerConfirmation(display_name="Zhang San")

    def test_resolver_does_not_infer_role_or_department_from_text_metadata(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_2",
                    display_name="Confirmed Name",
                    metadata={"transcript_text": "I will handle product planning as PM."},
                )
            ]
        )

        context = resolver.resolve(meeting_id="meeting-1", speaker_label="speaker_2")

        self.assertEqual(context.display_name, "Confirmed Name")
        self.assertIsNone(context.role)
        self.assertIsNone(context.department)

    def test_resolve_many_returns_context_by_speaker_label(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Confirmed Name",
                )
            ]
        )

        contexts = resolver.resolve_many(meeting_id="meeting-1", speaker_labels=["speaker_1", "speaker_2"])

        self.assertEqual(contexts["speaker_1"].identity_status, "confirmed")
        self.assertEqual(contexts["speaker_2"].identity_status, "anonymous")

    def test_speaker_id_parser_rejects_malformed_values(self) -> None:
        self.assertEqual(parse_meeting_speaker_id("meeting:meeting-1:speaker_1"), ("meeting-1", "speaker_1"))

        with self.assertRaises(ValueError):
            parse_meeting_speaker_id("speaker_1")

        with self.assertRaises(ValueError):
            SpeakerResolver().resolve(
                speaker_id="meeting:meeting-1:speaker_1",
                meeting_id="other-meeting",
            )


if __name__ == "__main__":
    unittest.main()
