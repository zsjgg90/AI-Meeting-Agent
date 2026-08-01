import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_pipeline import six_dimension_result_to_analysis_dict
from app.six_dimension_schema import ActionItem, SixDimensionResult


class MeetingAnalysisPipelineOutputTest(unittest.TestCase):
    def test_action_owner_deadline_export_requires_source_text_evidence(self) -> None:
        result = SixDimensionResult(
            meeting_id="meeting-1",
            action_items=[
                ActionItem(
                    content="I will ship payment flow on Friday",
                    topic_id="topic-1",
                    source_event_ids=["event-1"],
                    source_texts=["I will ship payment flow on Friday"],
                    owner="Backend Lead",
                    deadline="Friday",
                    confidence=0.9,
                ),
                ActionItem(
                    content="Alice will prepare launch notes on Monday",
                    topic_id="topic-2",
                    source_event_ids=["event-2"],
                    source_texts=["Alice will prepare launch notes on Monday"],
                    owner="Alice",
                    deadline="Monday",
                    confidence=0.9,
                ),
            ],
        )

        payload = six_dimension_result_to_analysis_dict(result)
        first, second = payload["action_items"]

        self.assertIsNone(first["owner_name"])
        self.assertEqual(first["deadline"], "Friday")
        self.assertEqual(second["owner_name"], "Alice")
        self.assertEqual(second["deadline"], "Monday")


if __name__ == "__main__":
    unittest.main()
