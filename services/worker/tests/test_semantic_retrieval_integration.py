import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from app.meeting_analyst_service import (
    MeetingAnalystService,
    build_semantic_retrieval_request,
)
from app.rag_retriever import RagContext
from app.semantic_intelligence.retrieval_bridge import RetrievalBridge


class FakeRetriever:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []
        self.max_context_chars = 2000

    def build_context_payload(self, **kwargs) -> RagContext:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("semantic retrieval failed")

        query = kwargs["query"]
        target_dimension = kwargs.get("target_dimension")
        return RagContext(
            text=f"context for {query}",
            chunks=[
                {
                    "chunk_id": "chunk-1",
                    "content": f"rule for {query}",
                    "dimension": target_dimension,
                }
            ],
            chunk_ids=["chunk-1"],
            collection_name="meeting_analyst_rules_gate_b_v3_4_2_bge_m3_dense_v1",
            embedding_model="BAAI/bge-m3",
            dataset_version="gate-b",
            chunk_schema_version="rag-chunk-v3",
            retrieved_chunk_ids=["chunk-1"],
            retrieval_strategy="v3_dimension_pool_routing",
            retrieval_trace={
                "query": query,
                "target_dimension": target_dimension,
            },
        )

    def search(self, **kwargs) -> list[dict]:
        return self.build_context_payload(**kwargs).chunks


class SemanticRetrievalIntegrationTest(unittest.TestCase):
    def test_bridge_returns_formal_rag_context(self) -> None:
        retriever = FakeRetriever()
        bridge = RetrievalBridge(retriever)

        context = bridge.retrieve_context(
            {
                "query": "extract_action_item action_rule owner_deadline",
                "top_k": 3,
                "metadata_filter": {
                    "dimension": "action_items",
                },
                "transcript": "张伟下午测试接口",
            }
        )

        self.assertIsInstance(context, RagContext)
        self.assertEqual(context.chunks[0]["chunk_id"], "chunk-1")
        self.assertEqual(context.chunk_ids, ["chunk-1"])
        self.assertEqual(
            context.collection_name,
            "meeting_analyst_rules_gate_b_v3_4_2_bge_m3_dense_v1",
        )
        self.assertEqual(context.embedding_model, "BAAI/bge-m3")
        self.assertEqual(
            retriever.calls[0]["target_dimension"],
            "action_items",
        )

    def test_proposal_text_guides_not_decision_retrieval(self) -> None:
        request = build_semantic_retrieval_request(
            "这个功能后面可以研究一下",
            top_k=5,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("prevent_false_decision", request["query"])
        self.assertIn("decision_boundary", request["query"])
        self.assertIn("negative_examples", request["query"])
        self.assertIn("proposal", request["query"])
        self.assertIn("not_decision", request["query"])
        self.assertEqual(
            request["metadata_filter"]["dimension"],
            "key_conclusions",
        )

    def test_confirmed_decision_text_guides_decision_retrieval(self) -> None:
        request = build_semantic_retrieval_request(
            "确认下周上线这个功能",
            top_k=5,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("extract_confirmed_decision", request["query"])
        self.assertIn("decision_rule", request["query"])
        self.assertIn("positive_examples", request["query"])
        self.assertIn("confirmed", request["query"])
        self.assertEqual(
            request["metadata_filter"]["dimension"],
            "key_conclusions",
        )

    def test_action_text_guides_owner_deadline_retrieval(self) -> None:
        request = build_semantic_retrieval_request(
            "张伟下午测试接口",
            top_k=5,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("extract_action_item", request["query"])
        self.assertIn("action_rule", request["query"])
        self.assertIn("owner_deadline", request["query"])
        self.assertIn("owner", request["query"])
        self.assertIn("deadline", request["query"])
        self.assertEqual(
            request["metadata_filter"]["dimension"],
            "action_items",
        )

    def test_formal_rag_context_uses_semantic_bridge(self) -> None:
        retriever = FakeRetriever()
        service = MeetingAnalystService(
            retriever=retriever,
            llm_client=object(),
        )

        context = service._build_formal_rag_context(
            transcript="确认下周上线这个功能",
            top_k=5,
        )

        self.assertEqual(len(retriever.calls), 1)
        self.assertEqual(
            retriever.calls[0]["target_dimension"],
            "key_conclusions",
        )
        self.assertIn(
            "extract_confirmed_decision",
            retriever.calls[0]["query"],
        )
        self.assertEqual(
            context.retrieval_strategy,
            "semantic_guided_v3_dimension_pool_routing",
        )
        self.assertEqual(context.chunk_ids, ["chunk-1"])
        self.assertIn(
            "semantic_guided_retrieval",
            context.retrieval_trace,
        )

    def test_semantic_failure_falls_back_to_existing_formal_rag(self) -> None:
        service = MeetingAnalystService(
            retriever=FakeRetriever(fail=True),
            llm_client=object(),
        )
        fallback = RagContext(
            text="fallback context",
            chunks=[],
            chunk_ids=[],
            collection_name="fallback",
            embedding_model="fallback",
            dataset_version="fallback",
            chunk_schema_version="fallback",
        )

        with patch.object(
            service,
            "_build_default_formal_rag_context",
            return_value=fallback,
        ) as default_context:
            context = service._build_formal_rag_context(
                transcript="确认下周上线这个功能",
                top_k=5,
            )

        self.assertIs(context, fallback)
        default_context.assert_called_once_with(
            transcript="确认下周上线这个功能",
            top_k=5,
        )


if __name__ == "__main__":
    unittest.main()
