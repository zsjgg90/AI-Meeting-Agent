import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evidence_resolver import resolve_meeting_analysis_evidence
from app.meeting_analysis_postprocessor import source_is_continuous
from app.meeting_analysis_schema import (
    KeyConclusion,
    MeetingActionItem,
    MeetingAnalysisSchema,
    RiskAndFocus,
    UnresolvedIssue,
)
from app.transcript_builder import build_transcript_text


TRANSCRIPT = "\n".join(
    [
        "PM: Payment API must finish stability validation by October 15.",
        "Frontend: Frontend will fix search result flicker tomorrow afternoon.",
        "Backend: The third-party dependency is still unresolved and needs follow-up.",
        "QA: Payment delay may compress testing time, which is the main launch risk.",
    ]
)


def base_analysis(**kwargs) -> MeetingAnalysisSchema:
    data = {
        "meeting_summary": "Summary",
        "key_conclusions": [],
        "action_items": [],
        "unresolved_issues": [],
        "risks_and_focus": [],
    }
    data.update(kwargs)
    return MeetingAnalysisSchema(**data)


def formal_transcript(segments: list[dict]) -> str:
    return build_transcript_text(segments)


class EvidenceResolverTest(unittest.TestCase):
    def test_resolves_non_action_claims_to_continuous_transcript_evidence(self) -> None:
        analysis = base_analysis(
            key_conclusions=[
                KeyConclusion(
                    conclusion="Payment API stability validation by October 15",
                    source_text="Payment API stability validation",
                )
            ],
            action_items=[
                MeetingActionItem(
                    owner_name="Frontend",
                    task="Fix search result flicker",
                    source_text="Handle task list display issue.",
                )
            ],
            unresolved_issues=[
                UnresolvedIssue(
                    issue="Third-party dependency is unresolved",
                    source_text="External service blocker still pending",
                )
            ],
            risks_and_focus=[
                RiskAndFocus(
                    risk="Payment delay may compress testing time",
                    focus_area="Launch risk",
                    source_text="Payment delay affects testing schedule",
                )
            ],
        )

        resolved = resolve_meeting_analysis_evidence(analysis, TRANSCRIPT)

        self.assertEqual(
            resolved.key_conclusions[0].source_text,
            "PM: Payment API must finish stability validation by October 15.",
        )
        self.assertEqual(
            resolved.action_items[0].source_text,
            "Handle task list display issue.",
        )
        self.assertEqual(
            resolved.unresolved_issues[0].source_text,
            "Backend: The third-party dependency is still unresolved and needs follow-up.",
        )
        self.assertEqual(
            resolved.risks_and_focus[0].source_text,
            "QA: Payment delay may compress testing time, which is the main launch risk.",
        )
        self.assertTrue(source_is_continuous(resolved.key_conclusions[0].source_text, TRANSCRIPT))
        self.assertFalse(source_is_continuous(resolved.action_items[0].source_text, TRANSCRIPT))
        self.assertTrue(source_is_continuous(resolved.unresolved_issues[0].source_text, TRANSCRIPT))
        self.assertTrue(source_is_continuous(resolved.risks_and_focus[0].source_text, TRANSCRIPT))

    def test_leaves_action_unchanged_when_no_conservative_match_exists(self) -> None:
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    task="Create database backup policy",
                    source_text="Create database backup policy",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(analysis, TRANSCRIPT)

        self.assertEqual(resolved.action_items[0].source_text, "Create database backup policy")
        self.assertIsNone(resolved.action_items[0].source_segment_id)

    def test_keeps_existing_valid_source_text(self) -> None:
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    task="Fix search result flicker",
                    source_text="Frontend: Frontend will fix search result flicker tomorrow afternoon.",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(analysis, TRANSCRIPT)

        self.assertEqual(
            resolved.action_items[0].source_text,
            "Frontend: Frontend will fix search result flicker tomorrow afternoon.",
        )

    def test_replaces_invalid_action_source_segment_id_when_source_text_matches_transcript(self) -> None:
        segments = [
            {
                "id": "legacy-seg-1",
                "speaker_label": "Product",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "text": "PM will update launch notes by Friday.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="PM",
                    task="Update launch notes",
                    source_text="Product: PM will update launch notes by Friday.",
                    source_segment_id="semantic-seg-1",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_segment_id, "legacy-seg-1")
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_fills_legacy_source_segment_id_from_existing_source_text(self) -> None:
        segments = [
            {
                "id": "seg-qa-1",
                "speaker_label": "QA",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "text": "QA will validate checkout by Friday.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="QA",
                    task="Validate checkout",
                    source_text="QA will validate checkout by Friday.",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-qa-1")
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_leaves_source_segment_id_empty_when_evidence_not_found(self) -> None:
        segments = [
            {
                "id": "seg-qa-1",
                "speaker_label": "QA",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "text": "QA will validate checkout by Friday.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="PM",
                    task="Prepare launch notes",
                    source_text="PM will prepare launch notes by Monday.",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertIsNone(resolved.action_items[0].source_segment_id)

    def test_does_not_generate_action_evidence_from_task(self) -> None:
        segments = [
            {
                "id": "seg-frontend-1",
                "speaker_label": "Frontend",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "text": "Frontend will fix search flicker tomorrow.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="Frontend",
                    task="Fix search flicker",
                    source_text="Handle task list display issue.",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, "Handle task list display issue.")
        self.assertIsNone(resolved.action_items[0].source_segment_id)

    def test_fills_contiguous_multi_segment_source_segment_id(self) -> None:
        segments = [
            {
                "id": "seg-1",
                "speaker_label": "Frontend",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "text": "Frontend will update UI tests.",
            },
            {
                "id": "seg-2",
                "speaker_label": "QA",
                "segment_index": 1,
                "start_time": 5.0,
                "end_time": 8.0,
                "text": "QA will rerun checkout regression.",
            },
            {
                "id": "seg-3",
                "speaker_label": "PM",
                "segment_index": 2,
                "start_time": 10.0,
                "end_time": 13.0,
                "text": "PM will publish release notes.",
            },
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="QA",
                    task="Update UI tests and rerun checkout regression",
                    source_text="Frontend will update UI tests. QA will rerun checkout regression.",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-1,seg-2")
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_rebuilds_action_source_text_from_contiguous_source_segment_id(self) -> None:
        segments = [
            {
                "id": "seg-1",
                "speaker_label": "Frontend",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 2.0,
                "text": "Search result flickers.",
            },
            {
                "id": "seg-2",
                "speaker_label": "Frontend",
                "segment_index": 1,
                "start_time": 2.0,
                "end_time": 4.0,
                "text": "Use request id to cancel stale requests.",
            },
            {
                "id": "seg-3",
                "speaker_label": "PM",
                "segment_index": 2,
                "start_time": 4.0,
                "end_time": 6.0,
                "text": "Send the result tomorrow.",
            },
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="Frontend",
                    task="Cancel stale search requests",
                    source_text="Search result flickers.\nUse request id to cancel stale requests.\nUse request id to cancel stale requests.",
                    source_segment_id="seg-1,seg-2,seg-3",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(
            resolved.action_items[0].source_text,
            transcript,
        )
        self.assertEqual(resolved.action_items[0].source_text.count("Use request id to cancel stale requests."), 1)
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_rejects_non_contiguous_action_source_segment_id_without_forging_evidence(self) -> None:
        segments = [
            {
                "id": "seg-1",
                "speaker_label": "Frontend",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 2.0,
                "text": "Search result flickers.",
            },
            {
                "id": "seg-2",
                "speaker_label": "PM",
                "segment_index": 1,
                "start_time": 2.0,
                "end_time": 4.0,
                "text": "Talk about release notes.",
            },
            {
                "id": "seg-3",
                "speaker_label": "Frontend",
                "segment_index": 2,
                "start_time": 4.0,
                "end_time": 6.0,
                "text": "Use request id to cancel stale requests.",
            },
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="Frontend",
                    task="Cancel stale search requests",
                    source_text="Search result flickers.\nUse request id to cancel stale requests.",
                    source_segment_id="seg-1,seg-3",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(
            resolved.action_items[0].source_text,
            "Search result flickers.\nUse request id to cancel stale requests.",
        )
        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-1,seg-3")
        self.assertFalse(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_rebuilds_single_segment_action_source_text_with_transcript_shape(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "FE",
                "segment_index": 0,
                "start_time": 1.0,
                "end_time": 2.5,
                "text": "Fix search result flicker tomorrow.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="FE",
                    task="Fix search result flicker",
                    source_text="Fix search result flicker tomorrow.",
                    source_segment_id="seg-a",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, transcript)
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_rebuilds_three_segment_action_source_text_as_formal_transcript_substring(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "PM",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "Search result flicker still exists.",
            },
            {
                "id": "seg-b",
                "speaker_label": "FE",
                "segment_index": 1,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "We will cancel stale requests with request id.",
            },
            {
                "id": "seg-c",
                "speaker_label": "QA",
                "segment_index": 2,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "QA will verify it tomorrow.",
            },
            {
                "id": "seg-d",
                "speaker_label": "PM",
                "segment_index": 3,
                "start_time": 3.0,
                "end_time": 4.0,
                "text": "Then we discuss payment status.",
            },
        ]
        transcript = formal_transcript(segments)
        expected_window = formal_transcript(segments[:3])
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="FE",
                    task="Cancel stale search requests and verify tomorrow",
                    source_text="Search result flicker still exists.\nWe will cancel stale requests with request id.\nQA will verify it tomorrow.",
                    source_segment_id="seg-a,seg-b,seg-c",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, expected_window)
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_source_segment_ids_are_resolved_in_transcript_order(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "PM",
                "segment_index": 2,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "PM will publish the release note.",
            },
            {
                "id": "seg-b",
                "speaker_label": "QA",
                "segment_index": 1,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "QA will rerun the regression.",
            },
            {
                "id": "seg-c",
                "speaker_label": "FE",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "FE will fix the search flicker.",
            },
        ]
        ordered_segments = [segments[2], segments[1], segments[0]]
        transcript = formal_transcript(ordered_segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="FE",
                    task="Fix search flicker and rerun regression",
                    source_text="FE will fix the search flicker.\nQA will rerun the regression.",
                    source_segment_id="seg-c,seg-b",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-c,seg-b")
        self.assertEqual(resolved.action_items[0].source_text, formal_transcript(ordered_segments[:2]))
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_rejects_repeated_center_segment_window(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "PM",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "A context.",
            },
            {
                "id": "seg-b",
                "speaker_label": "FE",
                "segment_index": 1,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "B action.",
            },
            {
                "id": "seg-c",
                "speaker_label": "QA",
                "segment_index": 2,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "C verification.",
            },
        ]
        transcript = formal_transcript(segments)
        original_source = "A context.\nB action.\nC verification.\nB action."
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="FE",
                    task="Finish B action",
                    source_text=original_source,
                    source_segment_id="seg-a,seg-b,seg-c,seg-b",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, original_source)
        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-a,seg-b,seg-c,seg-b")
        self.assertFalse(source_is_continuous(resolved.action_items[0].source_text, transcript))

    def test_missing_source_segment_id_does_not_forge_source_text(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "PM",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "PM will confirm scope.",
            }
        ]
        transcript = formal_transcript(segments)
        original_source = "FE will fix search result flicker."
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="FE",
                    task="Fix search result flicker",
                    source_text=original_source,
                    source_segment_id="seg-missing",
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, original_source)
        self.assertEqual(resolved.action_items[0].source_segment_id, "seg-missing")

    def test_preserves_existing_legal_continuous_action_source_text(self) -> None:
        segments = [
            {
                "id": "seg-a",
                "speaker_label": "PM",
                "segment_index": 0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "PM will confirm the payment verification state.",
            }
        ]
        transcript = formal_transcript(segments)
        analysis = base_analysis(
            action_items=[
                MeetingActionItem(
                    owner_name="PM",
                    task="Confirm payment verification state",
                    source_text=transcript,
                )
            ]
        )

        resolved = resolve_meeting_analysis_evidence(
            analysis,
            transcript,
            transcript_segments=segments,
        )

        self.assertEqual(resolved.action_items[0].source_text, transcript)
        self.assertTrue(source_is_continuous(resolved.action_items[0].source_text, transcript))


if __name__ == "__main__":
    unittest.main()
