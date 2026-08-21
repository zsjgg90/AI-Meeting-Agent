import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_pipeline import run_semantic_shadow_trace


def workflow_transcript_rows() -> list[dict[str, object]]:
    return [
        {
            "id": f"seg-{index}",
            "speaker_label": "speaker_1" if index % 2 == 0 else "speaker_2",
            "start_time": float(index * 2),
            "end_time": float(index * 2 + 1),
            "text": text,
        }
        for index, text in enumerate(
            [
                "今天我们对齐项目进度和上线风险。",
                "我会同步接口联调结果。",
                "目前登录接口已经完成。",
                "如果验收延期，可能影响上线。",
                "需要补充回归测试清单。",
                "登录接口还有疑问没有明确。",
            ]
        )
    ]


class WorkflowShadowTraceIntegrationTest(unittest.TestCase):
    def test_workflow_shadow_artifacts_are_written_without_formal_payload_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_dir = run_semantic_shadow_trace(
                "meeting-workflow",
                workflow_transcript_rows(),
                trace_root=Path(temp_dir),
            )

            observations_path = trace_dir / "workflow_state_observations.json"
            recommendations_path = trace_dir / "workflow_recommendations.json"
            audit_path = trace_dir / "workflow_audit.json"
            final_path = trace_dir / "07_final_meeting_analysis.json"

            self.assertTrue(observations_path.exists())
            self.assertTrue(recommendations_path.exists())
            self.assertTrue(audit_path.exists())
            self.assertTrue(final_path.exists())

            observations = json.loads(observations_path.read_text(encoding="utf-8"))
            recommendations = json.loads(recommendations_path.read_text(encoding="utf-8"))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            final_payload = json.loads(final_path.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(observations["items"]), 1)
        self.assertGreaterEqual(len(recommendations["items"]), 1)
        self.assertIn(
            recommendations["items"][0]["recommendation_type"],
            {"request_confirmation", "refresh_evidence", "review_dependency", "manual_review", "no_action"},
        )
        self.assertEqual(audit["workflow_count"], len(observations["items"]))
        self.assertEqual(audit["state_observation_count"], len(observations["items"]))
        self.assertEqual(audit["recommendation_count"], len(recommendations["items"]))
        self.assertFalse(audit["execution_attempted"])
        self.assertFalse(audit["writes_performed"])
        self.assertIn("update_task_status", audit["blocked_actions"])
        self.assertIn("write_database", audit["blocked_actions"])

        self.assertNotIn("workflow_state_observations", final_payload)
        self.assertNotIn("workflow_recommendations", final_payload)
        self.assertNotIn("workflow_audit", final_payload)
        self.assertNotIn("workflow_state_observations", final_payload["analysis"])
        self.assertNotIn("workflow_recommendations", final_payload["analysis"])
        self.assertNotIn("workflow_audit", final_payload["analysis"])


if __name__ == "__main__":
    unittest.main()
