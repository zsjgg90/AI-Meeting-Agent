import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from app.config import get_settings
from app.rag_retriever import RagRetriever


class RagV3RetrieverTest(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

    @staticmethod
    def _query_result(
        ids: list[str],
        *,
        distances: list[float] | None = None,
        scenario: str = "all",
        dimension: str = "action_items",
        retrieval_pool: str = "dynamic_boundary",
        knowledge_type: str = "boundary_rule",
        speech_act: str = "action",
        subtype: str = "assignment_positive",
        semantic_state: str = "open",
    ) -> dict:
        resolved_distances = distances or [
            0.1 + index * 0.01
            for index in range(len(ids))
        ]

        return {
            "ids": [ids],
            "documents": [
                [
                    f"content for {chunk_id}"
                    for chunk_id in ids
                ]
            ],
            "metadatas": [
                [
                    {
                        "chunk_id": chunk_id,
                        "title": chunk_id,
                        "scenario": scenario,
                        "dimension": dimension,
                        "retrieval_pool": retrieval_pool,
                        "knowledge_type": knowledge_type,
                        "speech_act": speech_act,
                        "observed_speech_act": speech_act,
                        "subtype": subtype,
                        "state": semantic_state,
                        "semantic_state": semantic_state,
                        "dataset_version": "meeting_analyst_rag_v3_2_0",
                        "chunk_schema_version": "rag-chunk-v3.2",
                        "scenario_taxonomy_version": "meeting-scenario-9-v1",
                        "retrieval_version": "meeting-rag-retrieval-v2",
                    }
                    for chunk_id in ids
                ]
            ],
            "distances": [resolved_distances],
        }

    def _build_retriever(
        self,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[RagRetriever, MagicMock]:
        collection = MagicMock()
        collection.count.return_value = 500

        embedding_model = MagicMock()
        embedding_model.encode.return_value.tolist.return_value = [
            [0.1, 0.2, 0.3]
        ]

        env = {
                "RAG_V3_RETRIEVAL_ENABLED": "true",
                "RAG_RERANKER_ENABLED": "false",
                "RAG_COLLECTION_NAME": "meeting_analyst_rules_v3_2_0",
                "RAG_DATASET_VERSION": "meeting_analyst_rag_v3_2_0",
                "RAG_CHUNK_SCHEMA_VERSION": "rag-chunk-v3.2",
                "RAG_SCENARIO_TAXONOMY_VERSION": "meeting-scenario-9-v1",
                "RAG_RETRIEVAL_VERSION": "meeting-rag-retrieval-v2",
                "RAG_V3_FINAL_K": "4",
                "RAG_V3_FIXED_POLICY_K": "1",
        }
        if extra_env:
            env.update(extra_env)

        with patch.dict(
            "os.environ",
            env,
            clear=False,
        ):
            get_settings.cache_clear()

            with patch(
                "app.rag_retriever.SentenceTransformer",
                return_value=embedding_model,
            ):
                with patch(
                    "app.rag_retriever.chromadb.PersistentClient"
                ) as persistent_client:
                    persistent_client.return_value.get_collection.return_value = (
                        collection
                    )

                    retriever = RagRetriever()

        return retriever, collection

    def test_no_target_dimension_uses_compatible_top_k_without_fixed_policy(self) -> None:
        retriever, collection = self._build_retriever()
        collection.query.return_value = self._query_result(
            [
                "dynamic_001",
                "example_001",
            ],
            retrieval_pool="dynamic_boundary",
        )

        context = retriever.build_context_payload(
            query="meeting analysis rules",
            top_k=2,
            transcript="general sync",
        )

        self.assertEqual(
            context.retrieval_strategy,
            "v3_compatible_top_k",
        )
        self.assertEqual(
            context.chunk_ids,
            [
                "dynamic_001",
                "example_001",
            ],
        )
        collection.get.assert_not_called()
        where_filter = collection.query.call_args.kwargs["where"]
        self.assertEqual(
            where_filter,
            {
                "retrieval_pool": {
                    "$ne": "fixed_policy"
                }
            },
        )

    def test_target_dimension_routes_dimension_pool_and_injects_fixed_policy(self) -> None:
        retriever, collection = self._build_retriever()
        collection.get.return_value = {
            "ids": [
                "fixed_action_001",
            ],
            "documents": [
                "fixed action content",
            ],
            "metadatas": [
                {
                    "chunk_id": "fixed_action_001",
                    "title": "fixed_action_001",
                    "scenario": "all",
                    "dimension": "action_items",
                    "retrieval_pool": "fixed_policy",
                    "knowledge_type": "definition",
                    "priority": "critical",
                    "dataset_version": "meeting_analyst_rag_v3_2_0",
                    "chunk_schema_version": "rag-chunk-v3.2",
                    "scenario_taxonomy_version": "meeting-scenario-9-v1",
                    "retrieval_version": "meeting-rag-retrieval-v2",
                }
            ],
        }
        collection.query.return_value = self._query_result(
            [
                "all_boundary_001",
                "scenario_example_001",
            ],
            distances=[
                0.1,
                0.2,
            ],
            scenario="project_weekly",
            dimension="action_items",
            retrieval_pool="scenario_example",
            knowledge_type="positive_example",
        )

        context = retriever.build_context_payload(
            query="extract action items",
            top_k=4,
            transcript="project weekly",
            meeting_type="project_weekly",
            target_dimension="Action",
        )

        self.assertEqual(
            context.retrieval_strategy,
            "v3_dimension_pool_routing",
        )
        self.assertEqual(
            context.chunk_ids[0],
            "fixed_action_001",
        )
        self.assertEqual(
            context.retrieval_version,
            "meeting-rag-retrieval-v2",
        )
        self.assertEqual(
            context.scenario_taxonomy_version,
            "meeting-scenario-9-v1",
        )
        self.assertIn(
            "action_items",
            context.retrieval_trace["resolved_dimensions"],
        )
        self.assertEqual(
            context.retrieval_trace["meeting_scenario"],
            "project_weekly",
        )

        query_where = collection.query.call_args.kwargs["where"]
        self.assertEqual(
            query_where["$and"][0],
            {
                "dimension": {
                    "$in": [
                        "action_items",
                        "cross_dimension",
                        "evidence",
                    ]
                }
            },
        )
        self.assertEqual(
            query_where["$and"][1],
            {
                "retrieval_pool": {
                    "$in": [
                        "dynamic_boundary",
                        "scenario_example",
                        "reasoning_pattern",
                    ]
                }
            },
        )

    def test_scenario_is_soft_boost_not_hard_filter(self) -> None:
        retriever, collection = self._build_retriever()
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        collection.query.return_value = {
            "ids": [
                [
                    "other_scenario_001",
                    "weekly_scenario_001",
                ]
            ],
            "documents": [
                [
                    "other content",
                    "weekly content",
                ]
            ],
            "metadatas": [
                [
                    {
                        "chunk_id": "other_scenario_001",
                        "title": "other",
                        "scenario": "technical_review",
                        "dimension": "risks_and_focus",
                        "retrieval_pool": "scenario_example",
                        "knowledge_type": "negative_example",
                        "dataset_version": "meeting_analyst_rag_v3_2_0",
                        "chunk_schema_version": "rag-chunk-v3.2",
                        "scenario_taxonomy_version": "meeting-scenario-9-v1",
                        "retrieval_version": "meeting-rag-retrieval-v2",
                    },
                    {
                        "chunk_id": "weekly_scenario_001",
                        "title": "weekly",
                        "scenario": "project_weekly",
                        "dimension": "risks_and_focus",
                        "retrieval_pool": "scenario_example",
                        "knowledge_type": "positive_example",
                        "dataset_version": "meeting_analyst_rag_v3_2_0",
                        "chunk_schema_version": "rag-chunk-v3.2",
                        "scenario_taxonomy_version": "meeting-scenario-9-v1",
                        "retrieval_version": "meeting-rag-retrieval-v2",
                    },
                ]
            ],
            "distances": [
                [
                    0.1,
                    0.2,
                ]
            ],
        }

        context = retriever.build_context_payload(
            query="extract risks",
            top_k=2,
            meeting_type="project_weekly",
            target_dimension="Risk",
        )

        candidate_ids = [
            item["chunk_id"]
            for item in context.retrieval_trace[
                "candidate_chunks"
            ]
        ]
        self.assertIn(
            "other_scenario_001",
            candidate_ids,
        )
        self.assertIn(
            "weekly_scenario_001",
            candidate_ids,
        )
        self.assertNotIn(
            {
                "scenario": "project_weekly"
            },
            collection.query.call_args.kwargs[
                "where"
            ]["$and"],
        )

    def test_low_confidence_meeting_type_uses_all_global_fallback(self) -> None:
        retriever, collection = self._build_retriever()
        collection.query.return_value = self._query_result(
            [
                "dynamic_001",
            ],
        )

        context = retriever.build_context_payload(
            query="meeting rules",
            top_k=1,
            meeting_type="project_weekly",
            meeting_type_confidence=0.2,
        )

        self.assertEqual(
            context.fallback_reason,
            "meeting_scenario_low_confidence_all_global_fallback",
        )
        self.assertEqual(
            context.retrieval_trace["meeting_scenario"],
            "all",
        )

    def test_meeting_type_aliases_are_rag_layer_only(self) -> None:
        retriever, collection = self._build_retriever()
        collection.query.return_value = self._query_result(
            [
                "dynamic_001",
            ],
        )

        context = retriever.build_context_payload(
            query="meeting rules",
            top_k=1,
            meeting_type="cross_department",
        )

        self.assertEqual(
            context.routed_scenario,
            "cross_team_coordination",
        )

    def test_reranker_disabled_preserves_dense_order_and_trace(self) -> None:
        retriever, collection = self._build_retriever()
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        collection.query.return_value = self._query_result(
            [
                "dense_first",
                "dense_second",
            ],
            distances=[
                0.1,
                0.2,
            ],
        )

        context = retriever.build_context_payload(
            query="extract action items",
            top_k=2,
            target_dimension="Action",
        )

        self.assertEqual(
            context.chunk_ids,
            [
                "dense_first",
                "dense_second",
            ],
        )
        self.assertNotIn(
            "reranker",
            context.retrieval_trace,
        )
        self.assertNotIn(
            "rerank_score",
            context.retrieval_trace[
                "candidate_chunks"
            ][0],
        )

    def test_reranker_enabled_reorders_dense_candidates(self) -> None:
        retriever, collection = self._build_retriever(
            {
                "RAG_RERANKER_ENABLED": "true",
            }
        )
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        collection.query.return_value = {
            "ids": [
                [
                    "action_positive",
                    "quoted_negative",
                ]
            ],
            "documents": [
                [
                    "explicit owner assignment example",
                    "quoted example should not become action",
                ]
            ],
            "metadatas": [
                [
                    {
                        "chunk_id": "action_positive",
                        "title": "action positive",
                        "scenario": "all",
                        "dimension": "action_items",
                        "retrieval_pool": "scenario_example",
                        "knowledge_type": "positive_example",
                        "speech_act": "action",
                        "observed_speech_act": "action",
                        "subtype": "assignment_positive",
                        "state": "open",
                        "semantic_state": "open",
                        "dataset_version": "meeting_analyst_rag_v3_2_0",
                        "chunk_schema_version": "rag-chunk-v3.2",
                    },
                    {
                        "chunk_id": "quoted_negative",
                        "title": "quoted negative",
                        "scenario": "all",
                        "dimension": "action_items",
                        "retrieval_pool": "scenario_example",
                        "knowledge_type": "negative_example",
                        "speech_act": "quoted_example",
                        "observed_speech_act": "quoted_example",
                        "subtype": "quoted_negative",
                        "state": "negative_example",
                        "semantic_state": "negative_example",
                        "dataset_version": "meeting_analyst_rag_v3_2_0",
                        "chunk_schema_version": "rag-chunk-v3.2",
                    },
                ]
            ],
            "distances": [
                [
                    0.1,
                    0.11,
                ]
            ],
        }

        context = retriever.build_context_payload(
            query="quoted example should not be an Action",
            top_k=2,
            target_dimension="Action",
        )

        self.assertEqual(
            context.chunk_ids[0],
            "quoted_negative",
        )
        self.assertEqual(
            context.retrieval_trace["reranker"][
                "fallback"
            ],
            False,
        )

        quoted_trace = next(
            item
            for item in context.retrieval_trace[
                "candidate_chunks"
            ]
            if item["chunk_id"] == "quoted_negative"
        )
        self.assertEqual(
            quoted_trace["dense_original_rank"],
            2,
        )
        self.assertEqual(
            quoted_trace["rerank_final_rank"],
            1,
        )
        self.assertTrue(
            quoted_trace["selected"]
        )
        self.assertFalse(
            quoted_trace["dropped"]
        )

    def test_reranker_preserves_candidate_metadata_and_count(self) -> None:
        retriever, collection = self._build_retriever(
            {
                "RAG_RERANKER_ENABLED": "true",
                "RAG_V3_FIXED_POLICY_K": "0",
            }
        )
        collection.query.return_value = self._query_result(
            [
                "candidate_1",
                "candidate_2",
                "candidate_3",
            ],
            distances=[
                0.1,
                0.11,
                0.12,
            ],
            scenario="project_weekly",
            dimension="action_items",
            retrieval_pool="scenario_example",
            knowledge_type="positive_example",
            speech_act="action",
            subtype="assignment_owner",
            semantic_state="open",
        )

        context = retriever.build_context_payload(
            query="extract action items",
            top_k=2,
            meeting_type="project_weekly",
            target_dimension="Action",
        )

        self.assertEqual(
            context.retrieval_trace["reranker"][
                "candidate_count"
            ],
            3,
        )
        self.assertEqual(
            len(
                context.retrieval_trace[
                    "candidate_chunks"
                ]
            ),
            3,
        )
        self.assertEqual(
            len(context.chunks),
            2,
        )
        self.assertEqual(
            context.chunks[0]["scenario"],
            "project_weekly",
        )
        self.assertEqual(
            context.chunks[0]["retrieval_pool"],
            "scenario_example",
        )
        self.assertIn(
            "dimension",
            context.chunks[0],
        )
        self.assertTrue(
            any(
                item["dropped"]
                for item in context.retrieval_trace[
                    "candidate_chunks"
                ]
            )
        )

    def test_reranker_exception_falls_back_to_dense_order(self) -> None:
        retriever, collection = self._build_retriever(
            {
                "RAG_RERANKER_ENABLED": "true",
            }
        )
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        collection.query.return_value = self._query_result(
            [
                "dense_first",
                "dense_second",
            ],
            distances=[
                0.1,
                0.2,
            ],
        )

        with patch.object(
            retriever,
            "_rerank_v3_vector_chunks",
            side_effect=RuntimeError("rerank boom"),
        ):
            context = retriever.build_context_payload(
                query="extract action items",
                top_k=2,
                target_dimension="Action",
            )

        self.assertEqual(
            context.chunk_ids,
            [
                "dense_first",
                "dense_second",
            ],
        )
        self.assertTrue(
            context.retrieval_trace["reranker"][
                "fallback"
            ]
        )
        self.assertIn(
            "RuntimeError",
            context.retrieval_trace["reranker"][
                "fallback_reason"
            ],
        )


if __name__ == "__main__":
    unittest.main()
