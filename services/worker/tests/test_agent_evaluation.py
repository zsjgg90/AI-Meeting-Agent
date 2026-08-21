import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_evaluation import (
    AgentEvalCaseLoader,
    AgentEvalMetricRunner,
    AgentRegressionPipeline,
    AgentEvalScorecard,
    MarkdownReportGenerator,
)
from scripts.validate_agent_eval_dataset import validate_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = PROJECT_ROOT / "fixtures" / "agent_eval"


class AgentEvaluationHarnessTest(unittest.TestCase):
    def test_case_loading_reads_golden_cases_and_artifacts(self) -> None:
        loader = AgentEvalCaseLoader(FIXTURE_ROOT)
        cases = loader.load_cases()

        self.assertEqual(len(cases), 10)
        self.assertEqual(
            {
                "conflict_cases",
                "cross_department",
                "long_meeting",
                "negative_cases",
                "project_weekly",
                "requirement_review",
                "risk_review",
                "technical_review",
            },
            {case.scenario for case in cases},
        )
        self.assertEqual(cases[0].case_version, "agent-eval-case-v1")
        artifacts = loader.load_artifacts(cases[0])
        self.assertIn("agent_output", artifacts)
        self.assertIn("transcript", artifacts)
        self.assertIn("formal_summary", artifacts)

    def test_dataset_validation_covers_required_stage8_7_3_structure(self) -> None:
        summary = validate_dataset(FIXTURE_ROOT)

        self.assertEqual(summary["case_count"], 10)
        self.assertIn("long_meeting", summary["scenarios"])

    def test_metric_calculation_passes_safe_case(self) -> None:
        loader = AgentEvalCaseLoader(FIXTURE_ROOT)
        case = next(item for item in loader.load_cases() if item.case_id == "agent_eval:project_weekly:001")
        result = AgentEvalMetricRunner().run_case(case, loader.load_artifacts(case))

        self.assertTrue(result.passed)
        by_metric = {metric.metric_id: metric for metric in result.metrics}
        self.assertEqual(by_metric["evidence_coverage"].score, 1.0)
        self.assertTrue(by_metric["action_safety"].passed)
        self.assertTrue(by_metric["formal_payload_isolation"].passed)

    def test_hard_gate_failure_blocks_unsafe_case(self) -> None:
        loader = AgentEvalCaseLoader(FIXTURE_ROOT)
        case = next(item for item in loader.load_cases() if item.case_id == "agent_eval:requirement_review:unsafe_001")
        result = AgentEvalMetricRunner().run_case(case, loader.load_artifacts(case))

        self.assertFalse(result.passed)
        by_metric = {metric.metric_id: metric for metric in result.metrics}
        self.assertFalse(by_metric["hallucination_hard_gates"].passed)
        self.assertFalse(by_metric["unsupported_owner_detection"].passed)
        self.assertFalse(by_metric["unsupported_deadline_detection"].passed)
        self.assertFalse(by_metric["unsupported_priority_detection"].passed)
        self.assertFalse(by_metric["action_safety"].passed)
        self.assertFalse(by_metric["permission_conservatism"].passed)
        self.assertFalse(by_metric["formal_payload_isolation"].passed)
        self.assertTrue(any(not gate.passed for gate in result.gates))

    def test_markdown_report_generation_is_deterministic(self) -> None:
        loader = AgentEvalCaseLoader(FIXTURE_ROOT)
        runner = AgentEvalMetricRunner()
        results = [runner.run_case(case, loader.load_artifacts(case)) for case in loader.load_cases()]
        scorecard = AgentEvalScorecard().build(results)
        report = MarkdownReportGenerator().generate(results, scorecard)

        self.assertIn("# Agent Evaluation Report", report)
        self.assertIn("`evidence_coverage`", report)
        self.assertIn("agent_eval:project_weekly:001", report)
        self.assertIn("agent_eval:requirement_review:unsafe_001", report)
        self.assertEqual(report, MarkdownReportGenerator().generate(results, scorecard))

    def test_regression_pipeline_generates_reports_and_suite_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "agent_evaluation"
            pipeline = AgentRegressionPipeline(
                fixture_root=FIXTURE_ROOT,
                output_root=output_root,
                run_id="unit-regression",
            )

            suite_summary = pipeline.run(validate_dataset(FIXTURE_ROOT))

            run_dir = output_root / "unit-regression"
            self.assertFalse(suite_summary["passed"])
            self.assertEqual(suite_summary["status"], "FAIL")
            self.assertTrue((run_dir / "suite_summary.json").exists())
            self.assertTrue((run_dir / "suite_summary.md").exists())
            self.assertTrue((run_dir / "baseline_comparison.json").exists())
            self.assertTrue((run_dir / "failure_report.json").exists())
            case_scorecard = run_dir / "cases" / "agent_eval__requirement_review__unsafe_001" / "case_scorecard.json"
            evidence_audit = run_dir / "cases" / "agent_eval__requirement_review__unsafe_001" / "evidence_audit.json"
            self.assertTrue(case_scorecard.exists())
            self.assertTrue(evidence_audit.exists())
            hard_gates = suite_summary["hard_gates"]
            self.assertFalse(hard_gates["evidence_gap"]["passed"])
            self.assertFalse(hard_gates["hallucination"]["passed"])
            self.assertFalse(hard_gates["unsupported_owner_deadline_priority"]["passed"])
            self.assertFalse(hard_gates["execution_leakage"]["passed"])
            self.assertFalse(hard_gates["permission_leakage"]["passed"])
            self.assertFalse(hard_gates["formal_payload_leakage"]["passed"])

    def test_regression_pipeline_writes_validation_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(temp_dir) / "fixtures"
            output_root = Path(temp_dir) / "output"
            fixture_root.mkdir()
            pipeline = AgentRegressionPipeline(
                fixture_root=fixture_root,
                output_root=output_root,
                run_id="validation-failure",
            )

            with self.assertRaises(ValueError) as context:
                validate_dataset(fixture_root)
            suite_summary = pipeline.write_validation_failure(str(context.exception))

            run_dir = output_root / "validation-failure"
            self.assertEqual(suite_summary["status"], "FAIL")
            self.assertFalse(suite_summary["validation"]["passed"])
            self.assertTrue((run_dir / "suite_summary.json").exists())
            self.assertIn("no agent evaluation cases", (run_dir / "failure_report.json").read_text(encoding="utf-8"))

    def test_baseline_comparison_uses_previous_suite_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "agent_evaluation"
            first = AgentRegressionPipeline(
                fixture_root=FIXTURE_ROOT,
                output_root=output_root,
                run_id="baseline-run",
            )
            first.run(validate_dataset(FIXTURE_ROOT))

            second = AgentRegressionPipeline(
                fixture_root=FIXTURE_ROOT,
                output_root=output_root,
                run_id="current-run",
                baseline=output_root / "baseline-run",
            )
            second.run(validate_dataset(FIXTURE_ROOT))

            comparison = json.loads(
                (output_root / "current-run" / "baseline_comparison.json").read_text(encoding="utf-8")
            )
            self.assertTrue(comparison["available"])
            self.assertEqual(comparison["baseline_run_id"], "baseline-run")
            self.assertEqual(comparison["current_run_id"], "current-run")
            self.assertEqual(comparison["overall_score_delta"], 0.0)

    def test_regression_command_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "agent_evaluation"
            command = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "run-agent-regression.ps1"),
                "-OutputRoot",
                str(output_root),
                "-RunId",
                "command-run",
            ]

            completed = subprocess.run(command, capture_output=True, text=True)

            self.assertEqual(completed.returncode, 1)
            summary_path = output_root / "command-run" / "suite_summary.json"
            self.assertTrue(summary_path.exists(), completed.stderr)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
