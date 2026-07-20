from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


WORKER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WORKER_ROOT.parents[1]
for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.agent_orchestrator import AgentOrchestrator
from app.meeting_scenarios.registry import get_policy
from scripts import run_agent_shadow_acceptance as acceptance


class AgentShadowAcceptanceTests(unittest.TestCase):
    def test_fixture_set_covers_three_core_scenarios(self) -> None:
        fixtures = acceptance.load_fixtures()
        counts: dict[str, int] = {}
        for meeting in fixtures:
            counts[meeting["meeting_type"]] = counts.get(meeting["meeting_type"], 0) + 1

        self.assertEqual(len(fixtures), 9)
        self.assertEqual(counts["project_weekly"], 3)
        self.assertEqual(counts["requirement_review"], 3)
        self.assertEqual(counts["cross_department"], 3)
        self.assertTrue(all(meeting["transcript"] for meeting in fixtures))

    def test_three_scenario_plan_selection_matches_phase5_expectations(self) -> None:
        orchestrator = AgentOrchestrator()

        for meeting_type, expected_tools in acceptance.EXPECTED_ENABLED_TOOLS.items():
            plan = orchestrator.create_plan(policy=get_policy(meeting_type))
            actual_tools = [step.tool_name for step in plan.steps if step.enabled]
            self.assertEqual(actual_tools, list(expected_tools), msg=meeting_type)

    def test_manual_meeting_type_drives_scenario_strategy(self) -> None:
        meeting = next(item for item in acceptance.load_fixtures() if item["meeting_type"] == "requirement_review")
        with tempfile.TemporaryDirectory() as tmp:
            summary = acceptance.run_meeting_acceptance(
                meeting=meeting,
                output_dir=Path(tmp),
                allow_live_model=False,
                failure_injection={},
            )

        self.assertEqual(summary["manual_meeting_type"], "requirement_review")
        self.assertEqual(summary["actual_plan"], list(acceptance.EXPECTED_ENABLED_TOOLS["requirement_review"]))

    def test_missing_history_and_empty_rag_degrade_without_formal_result_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = acceptance.run_acceptance(output_root=Path(tmp), timestamp="unit-safe-degrade")

        self.assertEqual(report["meetings_total"], 9)
        self.assertEqual(report["scenario_plan_hit_rate"], 1.0)
        self.assertTrue(all(item["formal_result_unchanged"] for item in report["meetings"]))
        requirement = next(item for item in report["meetings"] if item["meeting_type"] == "requirement_review")
        self.assertEqual(requirement["tool_result_sources"]["search_meeting_history"], "fixture_empty")
        self.assertEqual(requirement["tool_result_sources"]["search_project_knowledge"], "fixture_empty")

    def test_tool_failure_timeout_and_fallback_are_counted_and_report_still_writes(self) -> None:
        injections = {
            "phase5-project_weekly-1": {"search_meeting_history": "timeout"},
            "phase5-requirement_review-1": {"search_project_knowledge": "failed"},
            "phase5-cross_department-1": {"analyze_meeting": "fallback"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            report = acceptance.run_acceptance(
                output_root=Path(tmp),
                timestamp="unit-injected",
                failure_injections=injections,
            )
            output_dir = Path(report["output_dir"])
            self.assertTrue((output_dir / "acceptance_report.json").exists())
            self.assertTrue((output_dir / "acceptance_report.md").exists())

        self.assertGreater(report["tool_failure_rate"], 0)
        self.assertGreater(report["fallback_rate"], 0)
        self.assertEqual(report["failure_index"], [])

    def test_report_is_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = acceptance.run_acceptance(output_root=Path(tmp), timestamp="unit-serializable")

        encoded = json.dumps(report, ensure_ascii=False)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["schema_version"], "agent-v1-phase5-acceptance-report-v1")

    def test_default_acceptance_does_not_call_real_model(self) -> None:
        with patch("app.agent_tools.analysis.AnalyzeMeetingTool.execute") as execute:
            with tempfile.TemporaryDirectory() as tmp:
                report = acceptance.run_acceptance(output_root=Path(tmp), timestamp="unit-no-live-model")

        execute.assert_not_called()
        self.assertEqual(report["performance"]["real_model_call_count"], 0)
        self.assertFalse(report["allow_live_model"])

    def test_live_model_requires_explicit_argument(self) -> None:
        self.assertFalse(acceptance.parse_args([]).allow_live_model)
        self.assertTrue(acceptance.parse_args(["--allow-live-model"]).allow_live_model)

    def test_import_has_no_external_side_effects(self) -> None:
        module = importlib.import_module("scripts.run_agent_shadow_acceptance")

        self.assertIsNotNone(module.DEFAULT_FIXTURE_PATH)


if __name__ == "__main__":
    unittest.main()
