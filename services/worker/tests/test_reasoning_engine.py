import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory_retriever import RetrievedMemoryContext, RetrievedMemoryItem
from app.reasoning_engine import ReasoningContext, ReasoningEngine
from app.responsibility_evidence_matrix import ResponsibilityCandidate, ResponsibilityEvidenceMatrix, ResponsibilityEvidenceMatrixRow
from app.responsibility_extractor import ResponsibilityEvidence


NOW = datetime(2026, 8, 3, 10, 20, tzinfo=UTC)


def retrieved_context(*items: RetrievedMemoryItem) -> RetrievedMemoryContext:
    return RetrievedMemoryContext(
        as_of=NOW,
        source_snapshot_as_of=NOW,
        current_meeting_id="meeting-current",
        retrieved_at=NOW,
        token_budget=1200,
        token_cost=sum(item.token_cost for item in items),
        memories=list(items),
    )


def memory_item(
    *,
    memory_id: str = "mem:meeting:login-risk",
    text: str = "Login API stability is blocking beta release.",
    meeting_id: str = "meeting-history-1",
    meeting_memory_type: str = "risk",
    confidence: float = 0.86,
) -> RetrievedMemoryItem:
    return RetrievedMemoryItem(
        memory_id=memory_id,
        memory_type="meeting",
        content={
            "meeting_memory_type": meeting_memory_type,
            "text": text,
            "effective_status": "active",
        },
        relevance_score=0.84,
        evidence=[
            {
                "evidence_id": f"{memory_id}:evidence",
                "source_type": "transcript_segment",
                "meeting_id": meeting_id,
                "source_id": f"{meeting_id}:segment-4",
                "segment_id": f"{meeting_id}:segment-4",
                "supported_fields": ["text", "meeting_memory_type"],
                "source_text": text,
                "confidence": confidence,
            }
        ],
        token_cost=32,
    )


class ReasoningEngineTest(unittest.TestCase):
    def test_risk_reasoning_uses_retrieved_memory_evidence(self) -> None:
        result = ReasoningEngine().generate(
            retrieved_memory_context=retrieved_context(memory_item()),
            current_meeting_context={
                "project_id": "project-beta",
                "meeting_id": "meeting-current",
                "focus_terms": ["login API", "beta release"],
            },
        )

        risks = [item for item in result if item.reasoning_type == "risk_assessment"]
        self.assertEqual(len(risks), 1)
        candidate = risks[0]
        self.assertIsInstance(candidate, ReasoningContext)
        self.assertIn("Login API stability", candidate.claim)
        self.assertEqual(candidate.evidence_refs[0].memory_id, "mem:meeting:login-risk")
        self.assertEqual(candidate.evidence_refs[0].support_level, "supports")
        self.assertGreaterEqual(candidate.confidence, 0.86)
        self.assertFalse(candidate.requires_confirmation)
        self.assertIn("change_risk_status", candidate.suggested_next_step.blocked_actions)

    def test_responsibility_conflict_requires_confirmation(self) -> None:
        matrix = ResponsibilityEvidenceMatrix(
            rows=[
                ResponsibilityEvidenceMatrixRow(
                    task_key="task:login-api",
                    action_owner="Bob",
                    responsibility_candidates=[
                        ResponsibilityCandidate(
                            responsibility_id="resp:meeting-1:seg-4:alice",
                            responsibility_type="explicit_owner",
                            task="Investigate login API stability",
                            owner="Alice",
                            confidence=0.84,
                            requires_confirmation=False,
                        )
                    ],
                    evidence=[
                        ResponsibilityEvidence(
                            type="explicit_owner_text",
                            source_type="semantic_event",
                            meeting_id="meeting-current",
                            segment_id="segment-4",
                            source_text="Alice owns the login API stability investigation.",
                            owner_text="Alice",
                            task_text="Investigate login API stability",
                            supported_fields=["task", "owner"],
                            confidence=0.84,
                        )
                    ],
                    confidence=0.84,
                    consistency_status="owner_conflict",
                )
            ]
        )

        result = ReasoningEngine().generate(
            responsibility_matrix=matrix,
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(len(result), 1)
        candidate = result[0]
        self.assertEqual(candidate.reasoning_type, "responsibility_analysis")
        self.assertTrue(candidate.requires_confirmation)
        self.assertTrue(any(ref.support_level == "conflicts" for ref in candidate.evidence_refs))
        self.assertIn("Bob", candidate.claim)
        self.assertIn("Alice", candidate.claim)
        self.assertIn("assign_owner", candidate.suggested_next_step.blocked_actions)

    def test_trend_detection_requires_repeated_evidence(self) -> None:
        result = ReasoningEngine().generate(
            retrieved_memory_context=retrieved_context(
                memory_item(
                    memory_id="mem:meeting:login-risk-1",
                    text="Login API stability blocks beta release.",
                    meeting_id="meeting-history-1",
                ),
                memory_item(
                    memory_id="mem:meeting:login-risk-2",
                    text="Login API stability blocks beta readiness.",
                    meeting_id="meeting-history-2",
                ),
            ),
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        trends = [item for item in result if item.reasoning_type == "trend_detection"]
        self.assertEqual(len(trends), 1)
        candidate = trends[0]
        self.assertIn("appears repeatedly", candidate.claim)
        self.assertTrue(candidate.requires_confirmation)
        self.assertEqual(len(candidate.evidence_refs), 2)
        self.assertEqual(
            set(candidate.impact_scope.meeting_ids),
            {"meeting-current", "meeting-history-1", "meeting-history-2"},
        )
        self.assertEqual(candidate.suggested_next_step.step_type, "compare_with_prior_memory")

    def test_no_evidence_is_rejected(self) -> None:
        result = ReasoningEngine().generate(
            retrieved_memory_context=retrieved_context(
                RetrievedMemoryItem(
                    memory_id="mem:meeting:unsupported-risk",
                    memory_type="meeting",
                    content={
                        "meeting_memory_type": "risk",
                        "text": "Unsupported launch risk.",
                        "effective_status": "active",
                    },
                    relevance_score=0.8,
                    evidence=[],
                    token_cost=10,
                )
            ),
            current_meeting_context={"project_id": "project-beta", "meeting_id": "meeting-current"},
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
