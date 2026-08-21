from pathlib import Path
import sys
import unittest


WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from scripts.run_first_loss_analysis import (
    AnalysisTarget,
    determine_first_loss,
    dict_items,
    match_collection,
    render_report,
)


class FirstLossAnalysisTest(unittest.TestCase):
    def test_expected_present_reports_first_missing_stage(self) -> None:
        layer, reason = determine_first_loss(
            "present",
            {
                "Transcript": True,
                "Semantic": True,
                "RAG": True,
                "Qwen": True,
                "Fusion": False,
                "Evidence": False,
                "PostProcessor": False,
                "Validator": False,
                "Final": False,
            },
        )

        self.assertEqual(layer, "Fusion")
        self.assertEqual(reason, "present_before_Fusion_then_missing")

    def test_expected_present_final_survivor_has_no_first_loss(self) -> None:
        layer, reason = determine_first_loss(
            "present",
            {
                "Transcript": True,
                "Semantic": True,
                "RAG": True,
                "Qwen": False,
                "Fusion": True,
                "Evidence": True,
                "PostProcessor": True,
                "Validator": True,
                "Final": True,
            },
        )

        self.assertEqual(layer, "none")
        self.assertEqual(reason, "survived_to_final")

    def test_expected_present_paraphrase_survivor_is_not_first_loss(self) -> None:
        target = AnalysisTarget(
            key="decision_ai_stability_priority",
            label="Decision: AI stability priority",
            dimension="Decision",
            expectation="present",
            keywords=("AI分析稳定性优先级最高",),
            semantic_groups=(
                ("AI分析稳定性", "稳定性问题"),
                ("最高", "优先解决", "优先级最高"),
            ),
        )
        final_match = match_collection(
            [
                {
                    "conclusion": "AI分析稳定性问题需优先解决",
                    "source_text": "稳定性问题最高。先把六维输出稳定。",
                }
            ],
            target,
        )

        layer, reason = determine_first_loss(
            "present",
            {
                "Transcript": True,
                "Semantic": False,
                "RAG": True,
                "Qwen": True,
                "Fusion": True,
                "Evidence": True,
                "PostProcessor": True,
                "Validator": True,
                "Final": True,
            },
            {"Final": final_match},
        )

        self.assertTrue(final_match["semantic_equivalent_match"])
        self.assertEqual(layer, "none")
        self.assertEqual(reason, "survived_to_final/paraphrased")

    def test_qwen_raw_string_items_are_matchable(self) -> None:
        target = AnalysisTarget(
            key="risk_model_resource",
            label="Risk: model resource",
            dimension="Risk",
            expectation="present",
            keywords=("服务器压力可能会比较明显", "云GPU"),
            semantic_groups=(
                ("服务器压力", "模型资源"),
                ("用户量", "云GPU"),
                ("风险",),
            ),
        )
        items = dict_items(
            {
                "risks_and_focus": [
                    "服务器压力风险：随着用户量增加，可能需要云GPU等方案"
                ]
            },
            "risks_and_focus",
        )
        match = match_collection(items, target)

        self.assertTrue(match["matched"])
        self.assertTrue(match["semantic_equivalent_match"])

    def test_expected_absent_reports_first_false_positive_layer(self) -> None:
        layer, reason = determine_first_loss(
            "absent",
            {
                "Transcript": True,
                "Semantic": False,
                "RAG": True,
                "Qwen": True,
                "Fusion": True,
                "Evidence": True,
                "PostProcessor": True,
                "Validator": True,
                "Final": True,
            },
        )

        self.assertEqual(layer, "Qwen")
        self.assertEqual(reason, "false_positive_introduced_at_Qwen")

    def test_report_contains_required_summary_columns(self) -> None:
        report = render_report(
            {
                "metadata": {
                    "run_id": "unit",
                    "generated_at": "2026-08-12T00:00:00Z",
                    "input_file": "input.txt",
                    "meeting_id": "meeting-1",
                    "rag_collection_name": "meeting_analyst_rules_v3_2_0",
                    "rag_dataset_version": "meeting_analyst_rag_v3_2_0",
                    "retrieval_version": "meeting-rag-retrieval-v2",
                    "scenario_taxonomy_version": "meeting-scenario-9-v1",
                    "output_dir": "out",
                },
                "targets": [
                    {
                        "label": "Action target",
                        "expectation": "present",
                        "presence": {
                            "Transcript": True,
                            "Semantic": True,
                            "RAG": True,
                            "Qwen": False,
                            "Fusion": False,
                            "Evidence": False,
                            "PostProcessor": False,
                            "Validator": False,
                            "Final": False,
                        },
                        "first_loss_layer": "Qwen",
                        "first_loss_reason": "present_before_Qwen_then_missing",
                        "transcript_evidence": [],
                        "semantic_candidates": [],
                        "rag": {
                            "final_selected_chunks": [],
                            "candidate_chunks": [],
                            "fallback_reason": None,
                        },
                        "qwen_raw_candidates": [],
                        "fusion_result": [],
                        "evidence_result": [],
                        "postprocessor_audit": [],
                        "validator_audit": [],
                        "action_fusion_audit": [],
                        "final_result": [],
                    }
                ],
            }
        )

        self.assertIn(
            "| 目标 | Semantic | RAG | Qwen | Fusion | PostProcessor | Validator | Final | First Loss |",
            report,
        )
        self.assertIn("Action target", report)
        self.assertIn("Qwen: present_before_Qwen_then_missing", report)


if __name__ == "__main__":
    unittest.main()
