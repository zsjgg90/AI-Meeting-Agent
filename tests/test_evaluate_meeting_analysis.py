import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_meeting_analysis import (
    evaluate_results,
    render_markdown_report,
    write_report,
)


class EvaluateMeetingAnalysisTest(unittest.TestCase):
    def test_metric_calculation_with_mock_data(self):
        transcript = (
            "产品：确认上线方案采用灰度发布。"
            "研发：张三下周三完成接口联调。"
            "测试：支付链路超时会影响发布。"
        )
        expected = {
            "meeting_agenda": [{"item": "确认上线方案", "order": 1}],
            "meeting_summary": "讨论上线方案、任务和风险。",
            "key_conclusions": [
                {"conclusion": "上线方案采用灰度发布", "source_text": "确认上线方案采用灰度发布"}
            ],
            "action_items": [
                {"task": "张三完成接口联调", "source_text": "张三下周三完成接口联调"}
            ],
            "unresolved_issues": [],
            "risks_and_focus": [
                {"risk": "支付链路超时影响发布", "source_text": "支付链路超时会影响发布"}
            ],
        }
        actual = {
            "meeting_agenda": [{"item": "确认上线方案", "order": 1}],
            "meeting_summary": "讨论上线方案、任务和风险。",
            "key_conclusions": [
                {"conclusion": "上线方案采用灰度发布", "source_text": "确认上线方案采用灰度发布"},
                {"conclusion": "新增海外发布计划", "source_text": "海外发布计划已经确认"},
            ],
            "action_items": [
                {"task": "张三完成接口联调", "source_text": "张三下周三完成接口联调"}
            ],
            "unresolved_issues": [],
            "risks_and_focus": [
                {"risk": "支付链路超时影响发布", "source_text": "支付链路超时会影响发布"}
            ],
        }

        evaluation = evaluate_results(expected, actual, transcript)

        self.assertTrue(evaluation["schema"]["passed"])
        self.assertEqual(0.5, evaluation["metrics"]["decision_precision"])
        self.assertEqual(1.0, evaluation["metrics"]["task_recall"])
        self.assertEqual(1.0, evaluation["metrics"]["risk_recall"])
        self.assertEqual(0.25, evaluation["metrics"]["hallucination_rate"])
        self.assertEqual(0.75, evaluation["metrics"]["evidence_coverage"])

    def test_empty_expected_actual_defaults_are_stable(self):
        expected = {
            "meeting_agenda": [],
            "meeting_summary": "",
            "key_conclusions": [],
            "action_items": [],
            "unresolved_issues": [],
            "risks_and_focus": [],
        }
        actual = dict(expected)

        evaluation = evaluate_results(expected, actual, "")

        self.assertEqual(1.0, evaluation["metrics"]["decision_precision"])
        self.assertEqual(1.0, evaluation["metrics"]["task_recall"])
        self.assertEqual(1.0, evaluation["metrics"]["risk_recall"])
        self.assertEqual(0.0, evaluation["metrics"]["hallucination_rate"])
        self.assertEqual(1.0, evaluation["metrics"]["evidence_coverage"])

    def test_markdown_report_contains_baseline_metadata_and_metrics(self):
        evaluation = {
            "schema": {
                "passed": True,
                "missing_canonical_fields": [],
            },
            "metrics": {
                "decision_precision": 1.0,
                "task_recall": 1.0,
                "risk_recall": 0.5,
                "hallucination_rate": 0.0,
                "evidence_coverage": 1.0,
            },
            "counts": {
                "expected_decisions": 1,
                "actual_decisions": 1,
                "expected_tasks": 1,
                "actual_tasks": 1,
                "expected_risks": 2,
                "actual_risks": 1,
                "actual_evidence_items": 3,
                "evidence_covered_items": 3,
                "hallucinated_items": 0,
            },
            "details": {"hallucinated_items": []},
        }

        report = render_markdown_report(
            evaluation,
            {
                "model": "qwen3:14b",
                "prompt_version": "meeting_analyst_qwen3.md",
                "rag_version": "meeting_analyst_rules",
            },
        )

        self.assertIn("Model: qwen3:14b", report)
        self.assertIn("Prompt Version: meeting_analyst_qwen3.md", report)
        self.assertIn("RAG Version: meeting_analyst_rules", report)
        self.assertIn("Decision Precision", report)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "baseline.md"
            write_report(output, report)
            self.assertTrue(output.exists())
            self.assertIn("Metrics Result", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
