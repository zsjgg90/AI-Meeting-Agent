import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory_retriever import CurrentMeetingContext, MemoryRetrievalPolicy, MemoryRetriever
from app.memory_snapshot_builder import MemoryContext, MemoryEvidence, MemorySnapshot, MemorySourceEvent


CREATED_AT = datetime(2026, 8, 3, 10, 20, tzinfo=UTC)


def memory(
    *,
    memory_id: str,
    memory_type: str = "meeting",
    text: str,
    evidence_text: str,
    confidence: float = 0.86,
    status: str = "active",
    meeting_memory_type: str = "project_fact",
) -> MemoryContext:
    content = {"text": text}
    if memory_type == "meeting":
        content["meeting_memory_type"] = meeting_memory_type
        content["effective_status"] = "current"
    if memory_type == "responsibility":
        content = {
            "task": text,
            "owner": "Alice",
            "responsibility_type": "explicit_owner",
            "status": "open",
        }
    if memory_type == "entity":
        content = {
            "entity_type": "person",
            "display_name": text,
            "role": "Product Manager",
            "scope": "meeting",
        }
    return MemoryContext(
        memory_id=memory_id,
        memory_type=memory_type,  # type: ignore[arg-type]
        content=content,
        source_event=MemorySourceEvent(
            source_type="formal_summary_item",
            meeting_id="meeting-history-1",
            source_id=f"{memory_id}:source",
            occurred_at=CREATED_AT,
        ),
        evidence=[
            MemoryEvidence(
                evidence_id=f"{memory_id}:evidence",
                source_type="transcript_segment",
                meeting_id="meeting-history-1",
                source_id=f"{memory_id}:segment",
                segment_id=f"{memory_id}:segment",
                source_text=evidence_text,
                supported_fields=["text"],
                confidence=confidence,
                created_at=CREATED_AT,
            )
        ],
        confidence=confidence,
        created_at=CREATED_AT,
        status=status,  # type: ignore[arg-type]
    )


class MemoryRetrieverTest(unittest.TestCase):
    def test_retrieves_relevant_memory_by_current_context(self) -> None:
        snapshot = MemorySnapshot(
            meeting_id="meeting-current",
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:meeting:login-risk",
                    text="Login API stability is blocking beta release.",
                    evidence_text="The login API stability risk blocks beta release.",
                    meeting_memory_type="risk",
                ),
                memory(
                    memory_id="mem:meeting:office-move",
                    text="Office seating plan was updated.",
                    evidence_text="The office seating plan was updated.",
                ),
            ],
        )

        result = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context=CurrentMeetingContext(
                meeting_id="meeting-current",
                title="Beta release risk review",
                focus_terms=["login API", "beta release", "stability"],
            ),
            retrieved_at=CREATED_AT,
        )

        self.assertEqual([item.memory_id for item in result.memories], ["mem:meeting:login-risk"])
        self.assertGreater(result.memories[0].relevance_score, 0.12)
        self.assertEqual(result.memories[0].evidence[0]["source_text"], "The login API stability risk blocks beta release.")

    def test_filters_unrelated_memory(self) -> None:
        snapshot = MemorySnapshot(
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:meeting:office-move",
                    text="Office seating plan was updated.",
                    evidence_text="The office seating plan was updated.",
                )
            ],
        )

        result = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context={"meeting_id": "meeting-current", "summary": "Discuss login API beta release risks."},
            retrieved_at=CREATED_AT,
        )

        self.assertEqual(result.memories, [])

    def test_token_budget_limits_selected_memories(self) -> None:
        snapshot = MemorySnapshot(
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:meeting:login-risk",
                    text="Login API stability is blocking beta release.",
                    evidence_text="Login API blocks beta.",
                    confidence=0.9,
                ),
                memory(
                    memory_id="mem:responsibility:login-owner",
                    memory_type="responsibility",
                    text="Investigate login API stability",
                    evidence_text="Alice will investigate login API stability.",
                    confidence=0.88,
                ),
            ],
        )

        unbounded = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context="login API stability beta",
            policy=MemoryRetrievalPolicy(token_budget=1000),
            retrieved_at=CREATED_AT,
        )
        limited = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context="login API stability beta",
            policy=MemoryRetrievalPolicy(token_budget=unbounded.memories[0].token_cost),
            retrieved_at=CREATED_AT,
        )

        self.assertEqual(len(unbounded.memories), 2)
        self.assertEqual(len(limited.memories), 1)
        self.assertLessEqual(limited.token_cost, limited.token_budget)

    def test_low_confidence_memory_is_filtered(self) -> None:
        snapshot = MemorySnapshot(
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:meeting:low-confidence",
                    text="Login API may block beta release.",
                    evidence_text="Login API may block beta release.",
                    confidence=0.42,
                    status="candidate",
                )
            ],
        )

        result = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context="login API beta release",
            policy=MemoryRetrievalPolicy(min_confidence=0.65),
            retrieved_at=CREATED_AT,
        )

        self.assertEqual(result.memories, [])

    def test_type_and_status_filters_are_applied(self) -> None:
        snapshot = MemorySnapshot(
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:entity:alice",
                    memory_type="entity",
                    text="Alice",
                    evidence_text="Alice is the product owner.",
                    confidence=0.9,
                    status="confirmed",
                ),
                memory(
                    memory_id="mem:responsibility:login-owner",
                    memory_type="responsibility",
                    text="Investigate login API stability",
                    evidence_text="Alice will investigate login API stability.",
                    confidence=0.88,
                    status="needs_review",
                ),
            ],
        )

        result = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context="Alice login API stability",
            policy=MemoryRetrievalPolicy(
                memory_types={"responsibility"},
                allowed_statuses={"needs_review"},
                min_confidence=0.8,
            ),
            retrieved_at=CREATED_AT,
        )

        self.assertEqual([item.memory_id for item in result.memories], ["mem:responsibility:login-owner"])

    def test_evidence_is_compressed(self) -> None:
        snapshot = MemorySnapshot(
            as_of=CREATED_AT,
            memories=[
                memory(
                    memory_id="mem:meeting:long-evidence",
                    text="Login API stability is blocking beta release.",
                    evidence_text="Login API stability evidence " * 20,
                )
            ],
        )

        result = MemoryRetriever().retrieve(
            snapshot=snapshot,
            current_context="login API stability",
            policy=MemoryRetrievalPolicy(max_evidence_chars=40),
            retrieved_at=CREATED_AT,
        )

        self.assertTrue(result.memories[0].evidence[0]["source_text"].endswith("..."))
        self.assertLessEqual(len(result.memories[0].evidence[0]["source_text"]), 43)


if __name__ == "__main__":
    unittest.main()
