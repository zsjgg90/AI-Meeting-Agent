import json
import unittest
from pathlib import Path


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "meeting_analysis_regression_cases.json"
ALLOWED_DIMENSIONS = {
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
    "topics",
}


class RegressionFixtureTest(unittest.TestCase):
    def test_meeting_analysis_regression_fixture_shape(self) -> None:
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(cases), 18)
        case_ids = set()
        for case in cases:
            with self.subTest(case_id=case.get("case_id")):
                self.assertTrue(case.get("case_id"))
                self.assertNotIn(case["case_id"], case_ids)
                case_ids.add(case["case_id"])
                self.assertTrue(case.get("transcript"))
                dimensions = case.get("expected_dimensions")
                self.assertIsInstance(dimensions, list)
                self.assertTrue(set(dimensions).issubset(ALLOWED_DIMENSIONS))


if __name__ == "__main__":
    unittest.main()
