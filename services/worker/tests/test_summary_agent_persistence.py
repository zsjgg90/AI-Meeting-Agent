import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import ActionItem
from app.summary_agent import save_summary


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def execute(self, _statement: object) -> None:
        return None

    def flush(self) -> None:
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, _item: object) -> None:
        return None


def base_payload(action_items: list[dict]) -> dict:
    return {
        "overview": "Summary",
        "meeting_title": "",
        "meeting_type": "",
        "meeting_type_confidence": 0.0,
        "meeting_title_candidate": "",
        "title_basis": [],
        "agenda": [],
        "topics": [],
        "speaker_summaries": [],
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "next_steps": [],
        "meeting_agenda": [],
        "meeting_summary": "Summary",
        "key_conclusions": [],
        "action_items": action_items,
        "unresolved_issues": [],
        "risks_and_focus": [],
        "model_name": "test-model",
        "confidence_score": 0.8,
        "metadata": {"prompt_version": "test", "rag_chunk_ids": []},
    }


class SummaryAgentPersistenceTest(unittest.TestCase):
    FIRST_SEGMENT_ID = "11111111-1111-4111-8111-111111111111"
    SECOND_SEGMENT_ID = "22222222-2222-4222-8222-222222222222"

    def test_save_summary_persists_single_segment_uuid(self) -> None:
        db = FakeDb()
        meeting = SimpleNamespace(id="meeting-1", title="", title_source="", status="summarizing")

        save_summary(
            db,  # type: ignore[arg-type]
            meeting,  # type: ignore[arg-type]
            base_payload(
                [
                    {
                        "task": "Validate payment flow",
                        "source_text": "PM: Validate payment flow.",
                        "source_segment_id": self.FIRST_SEGMENT_ID,
                    }
                ]
            ),
        )

        action = next(item for item in db.added if isinstance(item, ActionItem))
        self.assertEqual(action.source_segment_id, self.FIRST_SEGMENT_ID)
        self.assertTrue(db.committed)

    def test_save_summary_persists_first_uuid_for_multi_segment_evidence(self) -> None:
        db = FakeDb()
        meeting = SimpleNamespace(id="meeting-1", title="", title_source="", status="summarizing")
        source_text = "PM: Validate payment flow.\nQA: QA will rerun regression."

        save_summary(
            db,  # type: ignore[arg-type]
            meeting,  # type: ignore[arg-type]
            base_payload(
                [
                    {
                        "task": "Validate payment flow and rerun regression",
                        "source_text": source_text,
                        "source_segment_id": f"{self.FIRST_SEGMENT_ID},{self.SECOND_SEGMENT_ID}",
                    }
                ]
            ),
        )

        action = next(item for item in db.added if isinstance(item, ActionItem))
        self.assertEqual(action.source_segment_id, self.FIRST_SEGMENT_ID)
        self.assertNotIn(",", action.source_segment_id)
        self.assertEqual(action.source_text, source_text)

    def test_save_summary_uses_none_when_no_valid_segment_uuid_exists(self) -> None:
        db = FakeDb()
        meeting = SimpleNamespace(id="meeting-1", title="", title_source="", status="summarizing")

        save_summary(
            db,  # type: ignore[arg-type]
            meeting,  # type: ignore[arg-type]
            base_payload(
                [
                    {
                        "task": "Fix search flicker",
                        "source_text": "FE: Fix search flicker.",
                        "source_segment_id": "seg-a,seg-b",
                    }
                ]
            ),
        )

        action = next(item for item in db.added if isinstance(item, ActionItem))
        self.assertIsNone(action.source_segment_id)


if __name__ == "__main__":
    unittest.main()
