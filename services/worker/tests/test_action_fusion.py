import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.action_fusion import fuse_action_items
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor
from app.meeting_analysis_schema import MeetingActionItem, MeetingAnalysisSchema


def analysis_with_actions(actions: list[MeetingActionItem]) -> MeetingAnalysisSchema:
    return MeetingAnalysisSchema(
        meeting_summary="summary",
        meeting_agenda=[],
        key_conclusions=[],
        action_items=actions,
        unresolved_issues=[],
        risks_and_focus=[],
    )


class ActionFusionTest(unittest.TestCase):
    def test_duplicate_legacy_and_semantic_are_grouped_not_deleted(self) -> None:
        legacy = MeetingActionItem(
            owner_name="Product",
            task="补充验收标准",
            deadline="周五",
            priority="high",
            source_text="Product 周五补充验收标准。",
            confidence=0.95,
        )
        semantic = {
            "owner_name": "Other",
            "task": "补充验收标准",
            "deadline": None,
            "priority": "medium",
            "source_text": "Other 补充验收标准。",
            "confidence": 0.8,
        }
        audit: list[dict] = []

        result = fuse_action_items(analysis_with_actions([legacy]), [semantic], audit=audit)

        self.assertEqual(len(result.action_items), 2)
        self.assertEqual({item.task for item in result.action_items}, {"补充验收标准"})
        self.assertEqual({event["source_type"] for event in audit}, {"legacy", "semantic"})
        self.assertEqual(len({event["duplicate_group"] for event in audit}), 1)

    def test_semantic_candidate_supplements_missing_action(self) -> None:
        legacy = MeetingActionItem(
            task="补充验收标准",
            source_text="Product 补充验收标准。",
            confidence=0.9,
        )
        semantic = {
            "task": "推进支付闭环验证",
            "source_text": "Backend 推进支付闭环验证。",
            "confidence": 0.86,
        }

        result = fuse_action_items(analysis_with_actions([legacy]), [semantic])

        self.assertEqual(
            [item.task for item in result.action_items],
            ["补充验收标准", "推进支付闭环验证"],
        )

    def test_weak_commitment_candidate_is_filtered(self) -> None:
        semantic = {
            "task": "我会处理",
            "source_text": "我会处理。",
            "confidence": 0.82,
        }

        result = fuse_action_items(analysis_with_actions([]), [semantic])

        self.assertEqual(result.action_items, [])

    def test_payment_progress_regression_candidates_are_clustered(self) -> None:
        semantic_candidates = [
            {
                "task": "支付推进",
                "source_text": "产品推进支付闭环。",
                "confidence": 0.8,
            },
            {
                "task": "支付回归",
                "source_text": "测试做支付回归。",
                "confidence": 0.8,
            },
            {
                "task": "支付稳定性验证",
                "source_text": "测试负责支付稳定性验证。",
                "confidence": 0.85,
            },
        ]

        result = fuse_action_items(analysis_with_actions([]), semantic_candidates)

        self.assertEqual(len(semantic_candidates), 3)
        self.assertEqual(len(result.action_items), 1)
        self.assertIn(result.action_items[0].task, {"支付推进", "支付回归", "支付稳定性验证"})

    def test_semantic_evidence_wins_over_legacy_priority_in_duplicate_group(self) -> None:
        legacy = MeetingActionItem(
            owner_name="测试",
            task="支付回归",
            deadline="周五",
            source_text="测试周五完成支付回归。",
            confidence=0.95,
        )
        semantic = {
            "owner_name": "测试",
            "task": "支付稳定性验证",
            "source_text": "测试周五完成支付稳定性验证。",
            "deadline": "周五",
            "confidence": 0.9,
        }

        result = fuse_action_items(analysis_with_actions([legacy]), [semantic])

        self.assertEqual(len(result.action_items), 2)
        self.assertEqual(result.action_items[0].task, "支付稳定性验证")

    def test_discussion_style_weak_candidate_is_filtered(self) -> None:
        semantic = {
            "task": "建议后续跟进支付",
            "source_text": "这里建议后续跟进支付问题，具体还要再讨论。",
            "confidence": 0.88,
        }

        result = fuse_action_items(analysis_with_actions([]), [semantic])

        self.assertEqual(result.action_items, [])

    def test_same_task_with_different_owner_is_kept(self) -> None:
        semantic_candidates = [
            {
                "owner_name": "前端",
                "task": "修复支付问题",
                "source_text": "前端修复支付问题。",
                "confidence": 0.85,
            },
            {
                "owner_name": "后端",
                "task": "修复支付问题",
                "source_text": "后端修复支付问题。",
                "confidence": 0.85,
            },
        ]

        result = fuse_action_items(analysis_with_actions([]), semantic_candidates)

        self.assertEqual(len(result.action_items), 2)
        self.assertEqual({item.owner_name for item in result.action_items}, {"前端", "后端"})

    def test_same_task_with_different_deadline_is_kept(self) -> None:
        semantic_candidates = [
            {
                "owner_name": "测试",
                "task": "完成支付回归",
                "deadline": "周三",
                "source_text": "测试周三完成支付回归。",
                "confidence": 0.85,
            },
            {
                "owner_name": "测试",
                "task": "完成支付回归",
                "deadline": "周五",
                "source_text": "测试周五完成支付回归。",
                "confidence": 0.85,
            },
        ]

        result = fuse_action_items(analysis_with_actions([]), semantic_candidates)

        self.assertEqual(len(result.action_items), 2)
        self.assertEqual({item.deadline for item in result.action_items}, {"周三", "周五"})

    def test_empty_candidates_keep_legacy_actions(self) -> None:
        legacy = MeetingActionItem(
            task="同步发布计划",
            source_text="PM 同步发布计划。",
            confidence=0.9,
        )

        result = fuse_action_items(analysis_with_actions([legacy]), [])

        self.assertEqual(len(result.action_items), 1)
        self.assertEqual(result.action_items[0].task, "同步发布计划")


    def test_semantic_candidate_source_segment_id_is_passed_through(self) -> None:
        semantic = {
            "task": "update release notes",
            "source_text": "PM will update release notes by Friday.",
            "source_segment_id": "seg-1,seg-2",
            "confidence": 0.9,
        }

        result = fuse_action_items(analysis_with_actions([]), [semantic])

        self.assertEqual(len(result.action_items), 1)
        self.assertEqual(result.action_items[0].source_text, "PM will update release notes by Friday.")
        self.assertEqual(result.action_items[0].source_segment_id, "seg-1,seg-2")

    def test_semantic_duplicate_survives_legacy_shorter_candidate(self) -> None:
        legacy = MeetingActionItem(
            task="修复AI分析失败状态",
            priority="high",
            source_text="后端明天下午修复AI分析失败状态。",
            confidence=0.95,
        )
        semantic = {
            "task": "修复AI分析失败状态返回机制",
            "source_text": "后端明天下午修复AI分析失败状态返回机制。",
            "deadline": "明天下午",
            "confidence": 0.9,
        }
        audit: list[dict] = []

        result = fuse_action_items(analysis_with_actions([legacy]), [semantic], audit=audit)

        self.assertEqual(len(result.action_items), 2)
        self.assertEqual(result.action_items[0].task, "修复AI分析失败状态返回机制")
        self.assertEqual(len({event["duplicate_group"] for event in audit}), 1)

    def test_semantic_survives_when_legacy_is_removed_by_postprocessor(self) -> None:
        legacy = MeetingActionItem(
            task="修复AI分析失败状态",
            source_text="不在原文里的 legacy source。",
            confidence=0.95,
        )
        semantic = {
            "task": "修复AI分析失败状态返回机制",
            "source_text": "项目经理：后端明天下午修复AI分析失败状态返回机制。",
            "deadline": "明天下午",
            "confidence": 0.9,
        }

        fused = fuse_action_items(analysis_with_actions([legacy]), [semantic])
        result = MeetingAnalysisPostProcessor().process(
            fused,
            "项目经理：后端明天下午修复AI分析失败状态返回机制。",
        )

        self.assertEqual([item.task for item in result.action_items], ["修复AI分析失败状态返回机制"])

    def test_knowledge_copy_adjust_and_provide_are_same_task_object(self) -> None:
        semantic_candidates = [
            {
                "task": "调整知识库文案",
                "source_text": "前端调整知识库文案。",
                "confidence": 0.86,
            },
            {
                "task": "提供知识库文案",
                "source_text": "产品提供知识库文案。",
                "confidence": 0.84,
            },
        ]

        result = fuse_action_items(analysis_with_actions([]), semantic_candidates)

        self.assertEqual(len(result.action_items), 1)
        self.assertIn(result.action_items[0].task, {"调整知识库文案", "提供知识库文案"})


if __name__ == "__main__":
    unittest.main()
