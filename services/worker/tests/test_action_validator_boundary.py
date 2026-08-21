import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.anti_hallucination_validator import filter_unassigned_or_suggested_action_items


def validate_action(task: str, source_text: str) -> tuple[list[dict], list[dict]]:
    audit: list[dict] = []
    result = filter_unassigned_or_suggested_action_items(
        {
            "action_items": [
                {
                    "task": task,
                    "source_text": source_text,
                    "confidence": 0.78,
                }
            ]
        },
        audit,
    )
    return result["action_items"], audit


class ActionValidatorBoundaryTest(unittest.TestCase):
    def test_deadline_backed_adjustment_is_kept(self) -> None:
        items, audit = validate_action(
            "调整知识库文案",
            "知识库文案周一前调整。",
        )

        self.assertEqual([item["task"] for item in items], ["调整知识库文案"])
        self.assertEqual(audit, [])

    def test_owner_backed_content_support_is_kept(self) -> None:
        items, audit = validate_action(
            "提供知识库文案",
            "产品负责提供文案支持。",
        )

        self.assertEqual([item["task"] for item in items], ["提供知识库文案"])
        self.assertEqual(audit, [])

    def test_owner_deadline_and_assignment_backed_adjustment_is_kept(self) -> None:
        items, audit = validate_action(
            "调整首页文案",
            "前端负责调整首页文案，明天下午完成。",
        )

        self.assertEqual([item["task"] for item in items], ["调整首页文案"])
        self.assertEqual(audit, [])

    def test_suggestion_adjustment_without_assignment_is_removed(self) -> None:
        items, audit = validate_action(
            "建议调整知识库文案",
            "建议调整知识库文案。",
        )

        self.assertEqual(items, [])
        self.assertEqual(audit[0]["reason"], "suggestion_or_direction_without_assignment")

    def test_consider_optimization_without_assignment_is_removed(self) -> None:
        items, audit = validate_action(
            "优化一下文案",
            "可以考虑优化一下文案。",
        )

        self.assertEqual(items, [])
        self.assertEqual(audit[0]["reason"], "suggestion_or_direction_without_assignment")

    def test_look_later_question_without_assignment_is_removed(self) -> None:
        items, audit = validate_action(
            "修改文案",
            "后面看看要不要改。",
        )

        self.assertEqual(items, [])
        self.assertEqual(audit[0]["reason"], "suggestion_or_direction_without_assignment")


if __name__ == "__main__":
    unittest.main()
