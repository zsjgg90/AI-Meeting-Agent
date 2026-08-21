import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory_snapshot_builder import MemorySnapshotBuilder
from app.responsibility_extractor import ResponsibilityContext, ResponsibilityEvidence
from app.speaker_identity import ManualSpeakerConfirmation, SpeakerResolver
from app.speaker_role import ManualRoleConfirmation, RoleResolver


CREATED_AT = datetime(2026, 8, 3, 10, 20, tzinfo=UTC)


def responsibility_context(
    *,
    responsibility_id: str = "resp:meeting-1:seg-1:abc",
    task: str = "Prepare launch checklist",
    owner: str | None = "Alice",
    source_text: str = "Alice owns the launch checklist.",
    segment_id: str = "seg-1",
    confidence: float = 0.86,
) -> ResponsibilityContext:
    return ResponsibilityContext(
        responsibility_id=responsibility_id,
        responsibility_type="explicit_owner" if owner else "unknown",
        task=task,
        owner=owner,
        evidence=[
            ResponsibilityEvidence(
                type="explicit_owner_text" if owner else "unknown_owner",
                source_type="semantic_event",
                meeting_id="meeting-1",
                segment_id=segment_id,
                source_text=source_text,
                owner_text=owner,
                task_text=task,
                supported_fields=["task", "owner"] if owner else ["task"],
                confidence=confidence,
            )
        ],
        confidence=confidence,
        source_type="semantic_event",
    )


class MemorySnapshotBuilderTest(unittest.TestCase):
    def test_speaker_and_role_context_generate_entity_memory(self) -> None:
        speaker_context = SpeakerResolver(
            [
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Alice",
                    department="Product",
                    confirmed_at=CREATED_AT,
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")
        role_context = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Product Manager",
                    confirmed_at=CREATED_AT,
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            speaker_contexts={"speaker_1": speaker_context},
            role_contexts={"speaker_1": role_context},
            created_at=CREATED_AT,
        )

        self.assertEqual(len(snapshot.memories), 1)
        memory = snapshot.memories[0]
        self.assertEqual(memory.memory_type, "entity")
        self.assertEqual(memory.content["display_name"], "Alice")
        self.assertEqual(memory.content["role"], "Product Manager")
        self.assertEqual(memory.content["department"], "Product")
        self.assertEqual({field for item in memory.evidence for field in item.supported_fields}, {"display_name", "role", "department"})

    def test_responsibility_evidence_generates_memory(self) -> None:
        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            responsibility_contexts=[responsibility_context()],
            created_at=CREATED_AT,
        )

        self.assertEqual(len(snapshot.memories), 1)
        memory = snapshot.memories[0]
        self.assertEqual(memory.memory_type, "responsibility")
        self.assertEqual(memory.content["task"], "Prepare launch checklist")
        self.assertEqual(memory.content["owner"], "Alice")
        self.assertEqual(memory.source_event.source_type, "responsibility_context")
        self.assertEqual(memory.evidence[0].source_text, "Alice owns the launch checklist.")
        self.assertEqual(memory.evidence[0].supported_fields, ["task", "owner"])

    def test_missing_evidence_does_not_generate_fact_memory(self) -> None:
        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            meeting_analysis_events=[
                {
                    "target_dimension": "key_conclusions",
                    "conclusion": "The beta release is delayed.",
                    "source_segment_id": "seg-9",
                    "confidence": 0.8,
                }
            ],
            created_at=CREATED_AT,
        )

        self.assertEqual(snapshot.memories, [])

    def test_generated_memory_status_is_candidate(self) -> None:
        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            responsibility_contexts=[responsibility_context()],
            meeting_analysis_events=[
                {
                    "target_dimension": "risks_and_focus",
                    "risk": "Login API instability may block beta.",
                    "source_text": "Login API instability may block beta.",
                    "source_segment_id": "seg-2",
                    "confidence": 0.82,
                }
            ],
            created_at=CREATED_AT,
        )

        self.assertTrue(snapshot.memories)
        self.assertTrue(all(memory.status == "candidate" for memory in snapshot.memories))

    def test_duplicate_memory_is_deduplicated_and_evidence_is_merged(self) -> None:
        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            responsibility_contexts=[
                responsibility_context(
                    responsibility_id="resp:meeting-1:seg-1:a",
                    source_text="Alice owns the launch checklist.",
                    segment_id="seg-1",
                    confidence=0.82,
                ),
                responsibility_context(
                    responsibility_id="resp:meeting-1:seg-2:b",
                    source_text="Alice owns the launch checklist before Friday.",
                    segment_id="seg-2",
                    confidence=0.9,
                ),
            ],
            created_at=CREATED_AT,
        )

        self.assertEqual(len(snapshot.memories), 1)
        memory = snapshot.memories[0]
        self.assertEqual(memory.content["task"], "Prepare launch checklist")
        self.assertEqual(memory.content["owner"], "Alice")
        self.assertEqual(len(memory.evidence), 2)
        self.assertEqual(memory.confidence, 0.9)

    def test_meeting_analysis_event_with_evidence_generates_meeting_memory(self) -> None:
        snapshot = MemorySnapshotBuilder().build(
            meeting_id="meeting-1",
            meeting_analysis_events=[
                {
                    "target_dimension": "key_conclusions",
                    "conclusion": "The beta release is delayed until login API stability is resolved.",
                    "source_text": "The team agreed to delay beta until the login API stability risk is resolved.",
                    "source_segment_id": "seg-3",
                    "confidence": 0.88,
                }
            ],
            created_at=CREATED_AT,
        )

        self.assertEqual(len(snapshot.memories), 1)
        memory = snapshot.memories[0]
        self.assertEqual(memory.memory_type, "meeting")
        self.assertEqual(memory.content["meeting_memory_type"], "decision")
        self.assertEqual(memory.evidence[0].source_id, "seg-3")


if __name__ == "__main__":
    unittest.main()
