import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.action_validator_trace import build_action_validator_trace, write_action_validator_trace


def action(task: str, source_segment_id: str) -> dict:
    return {
        "task": task,
        "source_text": f"{task} source",
        "source_segment_id": source_segment_id,
        "confidence": 0.78,
    }


class ActionValidatorTraceTest(unittest.TestCase):
    def test_build_trace_records_keep_and_remove_reasons(self) -> None:
        validator_input = {
            "action_items": [
                action("fix search flicker", "seg-1"),
                action("update docs", "seg-2"),
                action("run regression", "seg-3"),
            ]
        }
        validator_output = {
            "action_items": [
                action("fix search flicker", "seg-1"),
                action("run regression", "seg-3"),
            ]
        }
        audit = [
            {
                "field": "action_items",
                "action": "remove",
                "reason": "suggestion_or_direction_without_assignment",
                "before": action("update docs", "seg-2"),
            }
        ]

        trace = build_action_validator_trace(validator_input, validator_output, audit)

        self.assertEqual(trace["input_action_count"], 3)
        self.assertEqual(trace["output_action_count"], 2)
        self.assertEqual(trace["removed_action_count"], 1)
        self.assertEqual(
            trace["removed_items"][0]["rule_name"],
            "suggestion_or_direction_without_assignment",
        )
        self.assertEqual(
            trace["items"][1]["validator_result"]["decision"],
            "remove",
        )
        self.assertEqual(
            trace["items"][0]["after_validator"]["final_task_list"],
            ["fix search flicker", "run regression"],
        )

    def test_write_trace_creates_required_artifacts(self) -> None:
        validator_input = {"action_items": [action("keep one", "seg-1"), action("drop one", "seg-2")]}
        validator_output = {"action_items": [action("keep one", "seg-1")]}

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = write_action_validator_trace(
                validator_input,
                validator_output,
                [],
                output_dir=Path(tmp),
            )

            for name in (
                "validator_input.json",
                "validator_output.json",
                "validator_removed_items.json",
            ):
                self.assertTrue((output_dir / name).exists())

            removed = json.loads((output_dir / "validator_removed_items.json").read_text(encoding="utf-8"))
            self.assertEqual(removed[0]["rule_name"], "unattributed_validator_removal")


if __name__ == "__main__":
    unittest.main()
