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


class LayeredRagRetrieverTest(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()

    def tearDown(self) -> None:
        get_settings.cache_clear()

    @staticmethod
    def _query_result(
        ids: list[str],
        runtime_layer: str,
        *,
        scenario: str = "all",
    ) -> dict:
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
                        "layer": "test",
                        "runtime_layer": runtime_layer,
                        "scenario": scenario,
                        "dimension": "test_dimension",
                        "knowledge_type": "test_rule",
                        "dataset_version": (
                            "meeting_analyst_rag_v2_1_1"
                        ),
                        "chunk_schema_version": (
                            "rag-chunk-v2.1.1"
                        ),
                    }
                    for chunk_id in ids
                ]
            ],
            "distances": [
                [
                    round(
                        0.1 + index * 0.01,
                        4,
                    )
                    for index in range(len(ids))
                ]
            ],
        }

    def _build_retriever(
        self,
        *,
        layered_enabled: bool,
        fallback_enabled: bool = True,
    ) -> tuple[
        RagRetriever,
        MagicMock,
    ]:
        collection = MagicMock()
        collection.count.return_value = 88

        embedding_model = MagicMock()
        embedding_model.encode.return_value.tolist.return_value = [
            [0.1, 0.2, 0.3]
        ]

        with patch.dict(
            "os.environ",
            {
                "RAG_LAYERED_RETRIEVAL_ENABLED": (
                    "true"
                    if layered_enabled
                    else "false"
                ),
                "RAG_LAYERED_FALLBACK_ENABLED": (
                    "true"
                    if fallback_enabled
                    else "false"
                ),
                "RAG_COLLECTION_NAME": (
                    "meeting_analyst_rules_v2_1_1"
                ),
            },
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

    def test_legacy_mode_preserves_top_k(self) -> None:
        retriever, collection = self._build_retriever(
            layered_enabled=False
        )

        collection.query.return_value = (
            self._query_result(
                [
                    "legacy_001",
                    "legacy_002",
                ],
                "RAG_DYNAMIC",
            )
        )

        context = retriever.build_context_payload(
            query="会议分析规则",
            top_k=2,
            transcript="本次项目周会同步本周进度。",
        )

        self.assertEqual(
            context.retrieval_strategy,
            "legacy_top_k",
        )

        self.assertEqual(
            context.chunk_ids,
            [
                "legacy_001",
                "legacy_002",
            ],
        )

        self.assertEqual(
            context.retrieval_buckets,
            {
                "LEGACY_TOP_K": [
                    "legacy_001",
                    "legacy_002",
                ]
            },
        )

        collection.query.assert_called_once()

        called_kwargs = (
            collection.query.call_args.kwargs
        )

        self.assertNotIn(
            "where",
            called_kwargs,
        )

    def test_layered_mode_returns_1_2_3_2(self) -> None:
        retriever, collection = self._build_retriever(
            layered_enabled=True
        )

        collection.get.return_value = {
            "ids": [
                "boundary_rule_012",
            ],
            "documents": [
                "global fixed content",
            ],
            "metadatas": [
                {
                    "chunk_id": "boundary_rule_012",
                    "title": "global",
                    "layer": "boundary",
                    "runtime_layer": "POLICY_FIXED",
                    "scenario": "all",
                    "dimension": "evidence",
                    "knowledge_type": "boundary_rule",
                    "dataset_version": (
                        "meeting_analyst_rag_v2_1_1"
                    ),
                    "chunk_schema_version": (
                        "rag-chunk-v2.1.1"
                    ),
                }
            ],
        }

        collection.query.side_effect = [
            self._query_result(
                [
                    "boundary_rule_012",
                    "policy_001",
                    "policy_002",
                ],
                "POLICY_FIXED",
            ),
            self._query_result(
                [
                    "dynamic_001",
                    "dynamic_002",
                    "dynamic_003",
                ],
                "RAG_DYNAMIC",
            ),
            self._query_result(
                [
                    "scenario_001",
                    "scenario_002",
                ],
                "RAG_SCENARIO",
                scenario="project_weekly",
            ),
        ]

        context = retriever.build_context_payload(
            query="会议六大维度分析规则",
            transcript=(
                "本次项目周会同步本周进度、"
                "联调进度和下周计划。"
            ),
        )

        self.assertEqual(
            context.retrieval_strategy,
            "layered_1_2_3_2",
        )

        self.assertEqual(
            context.routed_meeting_type,
            "project_weekly",
        )

        self.assertEqual(
            context.routed_scenario,
            "project_weekly",
        )

        self.assertEqual(
            len(context.chunk_ids),
            8,
        )

        self.assertEqual(
            context.retrieval_buckets,
            {
                "GLOBAL_FIXED": [
                    "boundary_rule_012",
                ],
                "POLICY_SELECTED": [
                    "policy_001",
                    "policy_002",
                ],
                "RAG_DYNAMIC": [
                    "dynamic_001",
                    "dynamic_002",
                    "dynamic_003",
                ],
                "RAG_SCENARIO": [
                    "scenario_001",
                    "scenario_002",
                ],
            },
        )

        self.assertIsNone(
            context.fallback_reason
        )

    def test_unknown_route_falls_back_to_legacy(self) -> None:
        retriever, collection = self._build_retriever(
            layered_enabled=True,
            fallback_enabled=True,
        )

        collection.query.return_value = (
            self._query_result(
                [
                    "legacy_001",
                    "legacy_002",
                ],
                "RAG_DYNAMIC",
            )
        )

        context = retriever.build_context_payload(
            query="会议分析规则",
            top_k=2,
            transcript="大家随便聊一下近期工作。",
        )

        self.assertEqual(
            context.retrieval_strategy,
            "legacy_top_k_fallback",
        )

        self.assertEqual(
            context.fallback_reason,
            "meeting_type_route_not_found",
        )

        self.assertEqual(
            context.chunk_ids,
            [
                "legacy_001",
                "legacy_002",
            ],
        )

    def test_unknown_route_raises_when_fallback_disabled(
        self,
    ) -> None:
        retriever, _collection = self._build_retriever(
            layered_enabled=True,
            fallback_enabled=False,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "meeting_type_route_not_found",
        ):
            retriever.build_context_payload(
                query="会议分析规则",
                transcript="大家随便聊一下。",
            )

    def test_layer_failure_falls_back_to_legacy(
        self,
    ) -> None:
        retriever, collection = self._build_retriever(
            layered_enabled=True,
            fallback_enabled=True,
        )

        collection.get.side_effect = RuntimeError(
            "global rule missing"
        )

        collection.query.return_value = (
            self._query_result(
                [
                    "legacy_001",
                    "legacy_002",
                ],
                "RAG_DYNAMIC",
            )
        )

        context = retriever.build_context_payload(
            query="会议分析规则",
            top_k=2,
            transcript=(
                "今天进行需求评审，"
                "确认需求范围和验收标准。"
            ),
        )

        self.assertEqual(
            context.retrieval_strategy,
            "legacy_top_k_fallback",
        )

        self.assertEqual(
            context.routed_scenario,
            "requirement_review",
        )

        self.assertIn(
            "global rule missing",
            context.fallback_reason or "",
        )


if __name__ == "__main__":
    unittest.main()