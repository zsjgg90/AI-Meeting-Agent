import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.reasoning_evidence_graph import EvidenceNode, ReasoningEvidenceGraphBuilder


def node(
    *,
    node_type: str = "evidence",
    source_id: str = "segment-1",
    content: str = "The login API is unstable and may block beta.",
    confidence: float = 0.86,
) -> EvidenceNode:
    return ReasoningEvidenceGraphBuilder().node(
        node_type=node_type,  # type: ignore[arg-type]
        source_id=source_id,
        content=content,
        confidence=confidence,
    )


class ReasoningEvidenceGraphTest(unittest.TestCase):
    def test_single_evidence_supports_claim(self) -> None:
        graph = ReasoningEvidenceGraphBuilder().build_claim_graph(
            claim="Login API stability may block beta release.",
            supporting_nodes=[
                node(
                    source_id="segment-12",
                    content="The login API is still unstable, so beta may slip.",
                    confidence=0.84,
                )
            ],
        )

        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].edge_type, "supports")
        self.assertFalse(graph.requires_confirmation)
        self.assertEqual(graph.confirmation_reasons, [])

    def test_multiple_evidence_nodes_support_claim(self) -> None:
        graph = ReasoningEvidenceGraphBuilder().build_claim_graph(
            claim="Beta release is at risk because login API stability and owner follow-up are unresolved.",
            supporting_nodes=[
                node(
                    source_id="mem:meeting:risk:login",
                    node_type="memory",
                    content="Login API stability has remained an active beta-release risk.",
                    confidence=0.88,
                ),
                node(
                    source_id="resp:meeting-1:seg-4:login",
                    node_type="responsibility",
                    content="Investigate login API stability has an evidence-supported owner candidate.",
                    confidence=0.82,
                ),
            ],
        )

        self.assertIsNotNone(graph)
        assert graph is not None
        support_edges = [edge for edge in graph.edges if edge.edge_type == "supports"]
        self.assertEqual(len(support_edges), 2)
        self.assertEqual({edge.from_node_id for edge in support_edges}, {item.node_id for item in graph.nodes if item.node_type != "claim"})
        self.assertGreater(graph.confidence, 0.82)

    def test_conflicting_evidence_triggers_confirmation(self) -> None:
        graph = ReasoningEvidenceGraphBuilder().build_claim_graph(
            claim="Alice owns the login API mitigation.",
            supporting_nodes=[
                node(
                    source_id="resp:meeting-1:seg-4:alice",
                    node_type="responsibility",
                    content="Alice owns login API mitigation.",
                    confidence=0.82,
                )
            ],
            conflicting_nodes=[
                node(
                    source_id="mem:responsibility:login-owner-bob",
                    node_type="memory",
                    content="Bob owns login API mitigation.",
                    confidence=0.78,
                )
            ],
        )

        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertTrue(graph.requires_confirmation)
        self.assertIn("conflicting_evidence", graph.confirmation_reasons)
        self.assertEqual(
            [edge.edge_type for edge in graph.edges],
            ["supports", "conflicts"],
        )
        self.assertLess(graph.confidence, 0.82)

    def test_claim_without_evidence_is_not_generated(self) -> None:
        graph = ReasoningEvidenceGraphBuilder().build_claim_graph(
            claim="Login API stability may block beta release.",
            supporting_nodes=[],
        )

        self.assertIsNone(graph)


if __name__ == "__main__":
    unittest.main()
