from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


WORKER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WORKER_ROOT.parents[1]
for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import run_agent_shadow_live_acceptance as live_acceptance


class AgentShadowLiveAcceptanceTests(unittest.TestCase):
    def fixtures(self) -> list[dict]:
        return live_acceptance.load_fixtures()

    def test_default_cli_forbids_live_model(self) -> None:
        args = live_acceptance.parse_args([])

        self.assertFalse(args.allow_live_model)
        self.assertEqual(args.mode, "smoke")
        self.assertEqual(args.ollama_timeout, 300.0)

    def test_smoke_and_full_selection(self) -> None:
        fixtures = self.fixtures()

        smoke = live_acceptance.select_meetings(fixtures, mode="smoke")
        full = live_acceptance.select_meetings(fixtures, mode="full")

        self.assertEqual([item["meeting_id"] for item in smoke], list(live_acceptance.SMOKE_MEETING_IDS))
        self.assertEqual(len(full), 9)

    def test_meeting_id_and_scenario_selection(self) -> None:
        fixtures = self.fixtures()

        by_id = live_acceptance.select_meetings(fixtures, mode="full", meeting_id="phase5-requirement_review-2")
        by_scenario = live_acceptance.select_meetings(fixtures, mode="full", scenario="cross_department")

        self.assertEqual(len(by_id), 1)
        self.assertEqual(by_id[0]["meeting_type"], "requirement_review")
        self.assertEqual(len(by_scenario), 3)
        self.assertTrue(all(item["meeting_type"] == "cross_department" for item in by_scenario))

    def test_offline_run_does_not_call_real_qwen_rag_or_network(self) -> None:
        with patch.object(live_acceptance, "run_live_analysis_layers") as live_layers:
            with tempfile.TemporaryDirectory() as tmp:
                report = live_acceptance.run_acceptance(
                    output_root=Path(tmp),
                    timestamp="unit-offline",
                    mode="smoke",
                    meeting_id="phase5-project_weekly-1",
                    allow_live_model=False,
                    stop_on_failure=False,
                )

        live_layers.assert_not_called()
        self.assertFalse(report["run_config"]["allow_live_model"])
        self.assertEqual(report["meetings_completed"], 1)
        self.assertEqual(report["meetings"][0]["real_model_call_count"], 0)

    def test_report_and_artifact_structure_written_with_unavailable_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = live_acceptance.run_acceptance(
                output_root=Path(tmp),
                timestamp="unit-artifacts",
                mode="smoke",
                meeting_id="phase5-project_weekly-1",
                allow_live_model=False,
                stop_on_failure=False,
            )
            output_dir = Path(report["output_dir"])
            meeting_dir = output_dir / "meetings" / "phase5-project_weekly-1"

            self.assertTrue((output_dir / "run_config.json").exists())
            self.assertTrue((output_dir / "acceptance_report.json").exists())
            self.assertTrue((output_dir / "acceptance_report.md").exists())
            self.assertTrue((output_dir / "gpu_summary.json").exists())
            for artifact in live_acceptance.REQUIRED_MEETING_ARTIFACTS:
                self.assertTrue((meeting_dir / artifact).exists(), artifact)
            self.assertIn("unavailable", (meeting_dir / "prompt.txt").read_text(encoding="utf-8"))

    def test_stop_on_failure_stops_serial_execution(self) -> None:
        def fake_run(*args, **kwargs):
            meeting = kwargs["meeting"]
            return {
                "meeting_id": meeting["meeting_id"],
                "meeting_type": meeting["meeting_type"],
                "shadow_status": "failed",
                "stop_reason": "forced_failure",
                "total_duration_ms": 1,
                "tool_statuses": {"analyze_meeting": "failed"},
                "fallback_reason": None,
                "failure_reason": "forced",
                "gpu_summary": {},
                "quality_passed": False,
                "formal_isolation": {"shadow_did_not_modify_formal_result": True},
            }

        with patch.object(live_acceptance, "run_meeting_acceptance", side_effect=fake_run):
            with tempfile.TemporaryDirectory() as tmp:
                report = live_acceptance.run_acceptance(
                    output_root=Path(tmp),
                    timestamp="unit-stop",
                    mode="smoke",
                    stop_on_failure=True,
                )

        self.assertEqual(report["meetings_completed"], 1)
        self.assertEqual(report["stopped_reason"], "forced_failure")

    def test_ollama_timeout_is_passed_to_live_layer_capture(self) -> None:
        captured: dict[str, float] = {}

        def fake_layers(*, meeting, meeting_dir, ollama_timeout):
            captured["timeout"] = ollama_timeout
            result = live_acceptance.LayerCaptureResult(
                ok=True,
                artifacts={
                    "validated_result": {
                        "meeting_agenda": ["agenda"],
                        "meeting_summary": "summary",
                        "key_conclusions": [],
                        "action_items": [],
                        "unresolved_issues": [],
                        "risks_and_focus": [],
                        "_metadata": {"result_source": "legacy_qwen_rag"},
                    },
                    "validator_audit": [],
                },
                metadata={},
            )
            live_acceptance.write_missing_layer_artifacts(meeting_dir, reason="fake")
            live_acceptance.write_json(meeting_dir / "validated_result.json", result.artifacts["validated_result"])
            live_acceptance.write_json(meeting_dir / "validator_audit.json", [])
            return result

        with patch.object(live_acceptance, "run_live_analysis_layers", side_effect=fake_layers):
            with tempfile.TemporaryDirectory() as tmp:
                live_acceptance.run_acceptance(
                    output_root=Path(tmp),
                    timestamp="unit-timeout",
                    mode="smoke",
                    meeting_id="phase5-project_weekly-1",
                    allow_live_model=True,
                    ollama_timeout=123.0,
                    stop_on_failure=False,
                )

        self.assertEqual(captured["timeout"], 123.0)

    def test_gpu_monitor_failure_degrades_to_warning(self) -> None:
        with patch.object(live_acceptance.subprocess, "Popen", side_effect=FileNotFoundError("nvidia-smi")):
            with tempfile.TemporaryDirectory() as tmp:
                monitor = live_acceptance.GpuMonitor(
                    output_path=Path(tmp) / "gpu_samples.csv",
                    enabled=True,
                )
                monitor.start()
                summary = monitor.stop()

        self.assertFalse(summary["available"])
        self.assertIn("FileNotFoundError", summary["warning"])

    def test_gpu_monitor_stop_terminates_child_process(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.terminated = False
                self.killed = False
                self.stderr = None

            def terminate(self) -> None:
                self.terminated = True

            def wait(self, timeout: float | None = None) -> int:
                return 0

            def kill(self) -> None:
                self.killed = True

        fake_process = FakeProcess()
        with patch.object(live_acceptance.subprocess, "Popen", return_value=fake_process):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "gpu_samples.csv"
                monitor = live_acceptance.GpuMonitor(output_path=path, enabled=True)
                monitor.start()
                path.write_text(
                    "timestamp, memory.used [MiB], memory.total [MiB], utilization.gpu [%], temperature.gpu, power.draw [W]\n"
                    "2026/07/20 00:00:00.000, 100 MiB, 1000 MiB, 10 %, 50, 40 W\n",
                    encoding="utf-8",
                )
                summary = monitor.stop()

        self.assertTrue(fake_process.terminated)
        self.assertFalse(fake_process.killed)
        self.assertIsNone(monitor.process.stderr if monitor.process else None)
        self.assertTrue(summary["available"])

    def test_gpu_summary_parses_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gpu_samples.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "timestamp",
                        "memory.used [MiB]",
                        "memory.total [MiB]",
                        "utilization.gpu [%]",
                        "temperature.gpu",
                        "power.draw [W]",
                    ]
                )
                writer.writerow(["2026/07/20 00:00:00.000", "100 MiB", "1000 MiB", "10 %", "50", "40 W"])
                writer.writerow(["2026/07/20 00:00:01.000", "200 MiB", "1000 MiB", "30 %", "60", "80 W"])

            summary = live_acceptance.summarize_gpu_samples(path)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["peak_memory_used_mb"], 200.0)
        self.assertEqual(summary["avg_gpu_utilization_pct"], 20.0)
        self.assertEqual(summary["peak_temperature_c"], 60.0)
        self.assertEqual(summary["peak_power_draw_w"], 80.0)

    def test_gpu_summary_parses_nvidia_smi_header_spacing_and_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gpu_samples.csv"
            path.write_text(
                "timestamp, memory.used [MiB], memory.total [MiB], utilization.gpu [%], temperature.gpu, power.draw [W]\n"
                "2026/07/20 00:00:00.000, 11691 MiB, 12227 MiB, 98 %, 69, 237.78 W\n"
                "2026/07/20 00:00:01.000, 11673 MiB, 12227 MiB, 96 %, 68, 181.35 W\n",
                encoding="utf-8",
            )

            summary = live_acceptance.summarize_gpu_samples(path)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["peak_memory_used_mb"], 11691.0)
        self.assertEqual(summary["memory_total_mb"], 12227.0)
        self.assertEqual(summary["avg_gpu_utilization_pct"], 97.0)
        self.assertEqual(summary["peak_temperature_c"], 69.0)
        self.assertEqual(summary["peak_power_draw_w"], 237.78)
        numeric_fields = [
            "peak_memory_used_mb",
            "memory_total_mb",
            "avg_gpu_utilization_pct",
            "peak_temperature_c",
            "peak_power_draw_w",
        ]
        self.assertFalse(all(summary[field] is None for field in numeric_fields))

    def test_gpu_summary_skips_empty_and_na_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gpu_samples.csv"
            path.write_text(
                "timestamp, memory.used [MiB], memory.total [MiB], utilization.gpu [%], temperature.gpu, power.draw [W]\n"
                "2026/07/20 00:00:00.000, N/A, 12227 MiB, N/A, , N/A\n"
                "2026/07/20 00:00:01.000, 200 MiB, 12227 MiB, 30 %, 60, 80 W\n",
                encoding="utf-8",
            )

            summary = live_acceptance.summarize_gpu_samples(path)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["peak_memory_used_mb"], 200.0)
        self.assertEqual(summary["memory_total_mb"], 12227.0)
        self.assertEqual(summary["avg_gpu_utilization_pct"], 30.0)
        self.assertEqual(summary["peak_temperature_c"], 60.0)
        self.assertEqual(summary["peak_power_draw_w"], 80.0)

    def test_formal_result_isolation_detects_no_fixture_change(self) -> None:
        meeting = self.fixtures()[0]
        before = live_acceptance.formal_result_snapshot(meeting)
        after = live_acceptance.formal_result_snapshot(meeting)

        isolation = live_acceptance.compare_formal_snapshots(before, after)

        self.assertTrue(isolation["meeting_summary_unchanged"])
        self.assertTrue(isolation["action_items_unchanged"])
        self.assertTrue(isolation["result_source_unchanged"])
        self.assertTrue(isolation["shadow_did_not_modify_formal_result"])

    def test_stop_reason_for_unavailable_layers_is_not_live_failure_without_allow_live(self) -> None:
        reason = live_acceptance.stop_reason_for_meeting(
            shadow_status="partial",
            total_duration_ms=1,
            gpu_summary={"oom_detected": False},
            isolation={"shadow_did_not_modify_formal_result": True},
            quality={"available": False},
            layer_result=live_acceptance.LayerCaptureResult(
                ok=False,
                artifacts={},
                metadata={},
                failure_reason="--allow-live-model was not provided",
            ),
        )

        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
