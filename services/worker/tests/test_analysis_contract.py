import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    analysis_to_persistence_payload,
    normalize_meeting_analysis_result,
)


class AnalysisContractTest(unittest.TestCase):
    def test_normalizes_qwen_result_to_authoritative_schema(self) -> None:
        raw = {
            "meeting_agenda": ["同步背景", {"title": "评估方案"}],
            "meeting_summary": "本次会议围绕项目上线计划进行对齐，确认了范围、节奏和主要风险。",
            "key_conclusions": [
                {"conclusion": "按当前方案推进", "source_text": "就按这个方案推进", "confidence": 0.86}
            ],
            "action_items": [
                {
                    "owner_name": "产品",
                    "task": "补充验收标准",
                    "deadline": None,
                    "priority": "high",
                    "source_text": "产品补充验收标准",
                    "confidence": 0.82,
                }
            ],
            "unresolved_issues": [
                {"issue": "外部接口交付时间未确认", "source_text": "外部接口时间还没确认", "confidence": 0.74}
            ],
            "risks_and_focus": [
                {"risk": "接口延期可能影响联调", "impact": "联调延期", "source_text": "接口延期会影响联调", "confidence": 0.8}
            ],
            "_metadata": {"result_source": "legacy_qwen_rag"},
        }

        analysis = normalize_meeting_analysis_result(raw, model_name="qwen3:14b+rag")

        self.assertEqual(analysis.metadata.schema_version, ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(analysis.metadata.model_name, "qwen3:14b+rag")
        self.assertEqual(analysis.metadata.result_source, "legacy_qwen_rag")
        self.assertEqual(analysis.meeting_agenda[0].order, 1)
        self.assertEqual(analysis.action_items[0].owner_name, "产品")
        self.assertGreater(analysis.metadata.confidence_score, 0)

    def test_maps_authoritative_schema_to_current_persistence_payload(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "会议完成主要事项对齐。",
                "key_conclusions": [{"conclusion": "冻结范围", "source_text": "范围冻结", "confidence": 0.9}],
                "action_items": [{"task": "完成开发", "owner_name": "研发", "source_text": "研发完成开发"}],
            },
            model_name="qwen3:14b+rag",
        )

        payload = analysis_to_persistence_payload(analysis)

        self.assertEqual(payload["overview"], analysis.meeting_summary)
        self.assertEqual(payload["meeting_summary"], analysis.meeting_summary)
        self.assertEqual(payload["decisions"][0]["decision"], "冻结范围")
        self.assertEqual(payload["action_items"][0]["owner_name"], "研发")
        self.assertEqual(payload["metadata"]["schema_version"], ANALYSIS_SCHEMA_VERSION)
        self.assertIsNone(payload["metadata"]["result_source"])


if __name__ == "__main__":
    unittest.main()
