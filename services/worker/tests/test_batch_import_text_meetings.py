import unittest
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.analysis_contract import ensure_non_empty_analysis_result
from services.worker.scripts import batch_import_text_meetings
from services.worker.scripts.batch_import_text_meetings import verify_completed_summary


class FakeQuery:
    def where(self, *_args: object) -> "FakeQuery":
        return self


def fake_select(_model: object) -> FakeQuery:
    return FakeQuery()


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeActionItem:
    meeting_id = "meeting_id"


class FakeDb:
    def __init__(self, summary: object | None, action_items: list[object] | None = None) -> None:
        self.summary = summary
        self.action_items = action_items or []
        self.expired = False

    def expire_all(self) -> None:
        self.expired = True

    def get(self, _model: object, _id: str) -> object | None:
        return self.summary

    def scalars(self, _query: object) -> FakeScalars:
        return FakeScalars(self.action_items)


class BatchImportTextMeetingsTest(unittest.TestCase):
    def test_configure_worker_import_path_prefers_worker_app(self) -> None:
        api_root = batch_import_text_meetings.API_ROOT
        fake_module_name = "app.analysis_contract"
        fake_module = ModuleType(fake_module_name)
        fake_module.__file__ = str(api_root / "app" / "analysis_contract.py")
        original_module = sys.modules.get(fake_module_name)
        original_path = list(sys.path)

        try:
            sys.path.insert(0, str(api_root))
            sys.modules[fake_module_name] = fake_module

            batch_import_text_meetings.configure_worker_import_path()

            self.assertEqual(sys.path[0], str(batch_import_text_meetings.WORKER_ROOT))
            self.assertEqual(sys.path[1], str(batch_import_text_meetings.PROJECT_ROOT))
            self.assertNotEqual(sys.modules.get(fake_module_name), fake_module)
        finally:
            sys.path = original_path
            if original_module is None:
                sys.modules.pop(fake_module_name, None)
            else:
                sys.modules[fake_module_name] = original_module

    def modules(self) -> dict[str, object]:
        return {
            "MeetingSummary": object,
            "ActionItem": FakeActionItem,
            "select": fake_select,
            "ensure_non_empty_analysis_result": ensure_non_empty_analysis_result,
        }

    def test_verify_completed_summary_rejects_empty_six_dimensions(self) -> None:
        summary = SimpleNamespace(
            meeting_id="meeting-1",
            meeting_summary="",
            overview="",
            meeting_agenda=[],
            agenda=[],
            key_conclusions=[],
            decisions=[],
            unresolved_issues=[],
            open_questions=[],
            risks_and_focus=[],
            risks=[],
        )

        with self.assertRaises(ValueError) as raised:
            verify_completed_summary(FakeDb(summary), self.modules(), "meeting-1", "summary-1")

        self.assertIn("empty_analysis_result", str(raised.exception))

    def test_verify_completed_summary_accepts_non_empty_result(self) -> None:
        summary = SimpleNamespace(
            meeting_id="meeting-1",
            meeting_summary="formal summary",
            overview="",
            meeting_agenda=[],
            agenda=[],
            key_conclusions=[],
            decisions=[],
            unresolved_issues=[],
            open_questions=[],
            risks_and_focus=[],
            risks=[],
        )

        counts = verify_completed_summary(FakeDb(summary), self.modules(), "meeting-1", "summary-1")

        self.assertEqual(counts["meeting_summary_chars"], len("formal summary"))


if __name__ == "__main__":
    unittest.main()
