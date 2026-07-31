import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis_contract import normalize_meeting_analysis_result
from app.meeting_analyst_prompt import build_meeting_analyst_prompt
from app.prompt_registry import (
    MEETING_ANALYST_PROMPT_VERSION,
    get_meeting_analyst_prompt_spec,
    load_prompt_template,
)
from app.rag_retriever import RagContext, RagRetriever, build_context_text


class PromptRagVersioningTest(unittest.TestCase):
    def test_formal_prompt_is_loaded_by_version(self) -> None:
        spec = get_meeting_analyst_prompt_spec()
        template = load_prompt_template(spec.prompt_version)

        self.assertEqual(spec.prompt_version, MEETING_ANALYST_PROMPT_VERSION)
        self.assertIn("meeting_agenda", template)
        self.assertIn("meeting_summary", template)
        self.assertIn("key_conclusions", template)
        self.assertIn("action_items", template)
        self.assertIn("unresolved_issues", template)
        self.assertIn("risks_and_focus", template)

    def test_prompt_builder_injects_context_and_transcript(self) -> None:
        prompt = build_meeting_analyst_prompt(
            rag_context="规则：不要编造负责人",
            transcript="speaker_0：产品确认本周补充验收标准。",
        )

        self.assertIn("规则：不要编造负责人", prompt)
        self.assertIn("speaker_0：产品确认本周补充验收标准。", prompt)
        self.assertNotIn("{{RAG_CONTEXT}}", prompt)
        self.assertNotIn("{{TRANSCRIPT}}", prompt)

    def test_rag_context_preserves_chunk_ids(self) -> None:
        chunks = [
            {
                "chunk_id": "definition_001",
                "title": "会议议程定义",
                "section": "六大维度/会议议程",
                "knowledge_type": "definition",
                "content": "会议议程只描述讨论顺序。",
                "distance": 0.12,
            }
        ]
        context = RagContext(
            text=build_context_text(chunks),
            chunks=chunks,
            chunk_ids=[chunk["chunk_id"] for chunk in chunks],
            collection_name="meeting_analyst_rules",
            embedding_model="BAAI/bge-small-zh-v1.5",
            dataset_version="meeting_analyst_rag_v1",
            chunk_schema_version="rag-chunk-v1",
        )

        self.assertIn("会议议程定义", context.text)
        self.assertEqual(context.chunk_ids, ["definition_001"])

    def test_rag_retriever_loads_embedding_model_from_local_cache(self) -> None:
        with patch("app.rag_retriever.SentenceTransformer") as sentence_transformer:
            with patch("app.rag_retriever.chromadb.PersistentClient") as persistent_client:
                collection = MagicMock()
                collection.count.return_value = 350
                persistent_client.return_value.get_collection.return_value = collection

                RagRetriever()

        sentence_transformer.assert_called_once_with(
            "BAAI/bge-small-zh-v1.5",
            local_files_only=True,
        )

    def test_analysis_contract_persists_prompt_and_rag_metadata(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "会议围绕上线计划完成范围和风险对齐。",
                "key_conclusions": [
                    {"conclusion": "按当前方案推进", "source_text": "按当前方案推进", "confidence": 0.9}
                ],
                "_metadata": {
                    "prompt_version": "meeting-analyst-v1",
                    "rag_chunk_ids": ["definition_001", "boundary_004"],
                    "rag_dataset_version": "meeting_analyst_rag_v1",
                    "rag_chunk_schema_version": "rag-chunk-v1",
                    "rag_collection_name": "meeting_analyst_rules",
                    "rag_embedding_model": "BAAI/bge-small-zh-v1.5",
                    "rag_retrieval_strategy": "layered_1_2_3_2",
                    "rag_retrieval_buckets": {
                        "GLOBAL_FIXED": ["boundary_rule_012"],
                        "POLICY_SELECTED": ["boundary_rule_008"],
                    },
                    "rag_routed_meeting_type": "requirement_review",
                    "rag_routed_scenario": "requirement_review",
                    "rag_fallback_reason": None,
                },
            },
            model_name="qwen3:14b+rag",
        )

        self.assertEqual(analysis.metadata.prompt_version, "meeting-analyst-v1")
        self.assertEqual(analysis.metadata.rag_chunk_ids, ["definition_001", "boundary_004"])
        self.assertEqual(analysis.metadata.rag_dataset_version, "meeting_analyst_rag_v1")
        self.assertEqual(analysis.metadata.rag_chunk_schema_version, "rag-chunk-v1")
        self.assertEqual(analysis.metadata.rag_collection_name, "meeting_analyst_rules")
        self.assertEqual(
            analysis.metadata.rag_retrieval_strategy,
            "layered_1_2_3_2",
        )
        self.assertEqual(
            analysis.metadata.rag_retrieval_buckets[
                "GLOBAL_FIXED"
            ],
            ["boundary_rule_012"],
        )
        self.assertEqual(
            analysis.metadata.rag_routed_meeting_type,
            "requirement_review",
        )
        self.assertEqual(
            analysis.metadata.rag_routed_scenario,
            "requirement_review",
        )
        self.assertIsNone(
            analysis.metadata.rag_fallback_reason
        )


if __name__ == "__main__":
    unittest.main()
