from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.unresolved_candidate_recall import UnresolvedCandidate
from app.unresolved_ranking import RankedUnresolvedCandidate, rank_and_deduplicate_unresolved


def candidate(
    text: str,
    *,
    segment_id: str = "seg-1",
    event_id: str = "evt-1",
    confidence: float = 0.72,
    reasons: tuple[str, ...] = ("unresolved_marker",),
) -> UnresolvedCandidate:
    return UnresolvedCandidate(
        issue=text,
        source_text=text,
        source_segment_id=segment_id,
        source_event_ids=(event_id,),
        confidence=confidence,
        recall_reason=reasons,
    )


class UnresolvedRankingTest(unittest.TestCase):
    def test_payment_candidates_are_merged_into_one_issue_object(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("支付……现在还没通。", segment_id="seg-1", event_id="evt-1"),
                candidate(
                    "还没百分百确定。现在看像第三方 SDK 和他们最新文档有差异。",
                    segment_id="seg-2",
                    event_id="evt-2",
                ),
                candidate("昨天下午回了一次，没解决。", segment_id="seg-3", event_id="evt-3"),
                candidate("所以现在闭环还是跑不了？", segment_id="seg-4", event_id="evt-4"),
            ]
        )

        self.assertEqual(1, len(ranked))
        self.assertIsInstance(ranked[0], RankedUnresolvedCandidate)
        self.assertEqual("payment_external_dependency", ranked[0].issue_object)
        self.assertEqual(4, len(ranked[0].merged_source_texts))
        self.assertEqual({"evt-1", "evt-2", "evt-3", "evt-4"}, set(ranked[0].merged_source_event_ids))

    def test_different_unresolved_objects_are_preserved(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("支付成功回调签名验证原因还没确认。", segment_id="seg-1", event_id="evt-1"),
                candidate("声纹低置信度样本原因未知。", segment_id="seg-2", event_id="evt-2"),
            ]
        )

        self.assertEqual(2, len(ranked))
        self.assertEqual(
            {"payment_external_dependency", "声纹低置信度样本"},
            {item.issue_object for item in ranked},
        )

    def test_action_like_candidate_is_filtered(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("AI分析失败，后端明天下午修复。"),
            ]
        )

        self.assertEqual([], ranked)

    def test_risk_candidate_is_filtered(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("支付可能延期，可能影响上线。"),
            ]
        )

        self.assertEqual([], ranked)

    def test_meeting_question_is_filtered(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("还有遗漏吗？", reasons=("open_issue_intent",)),
            ]
        )

        self.assertEqual([], ranked)

    def test_weak_context_confirmation_fragment_is_filtered(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("对，还没确定。"),
            ]
        )

        self.assertEqual([], ranked)

    def test_high_value_markers_score_above_generic_open_issue(self) -> None:
        ranked = rank_and_deduplicate_unresolved(
            [
                candidate("支付回调签名验证为什么失败，目前还没确认。", segment_id="seg-1", event_id="evt-1"),
                candidate("相关事项待讨论。", segment_id="seg-2", event_id="evt-2", reasons=("open_issue_intent",)),
            ]
        )

        self.assertGreaterEqual(len(ranked), 1)
        self.assertEqual("payment_external_dependency", ranked[0].issue_object)
        self.assertGreater(ranked[0].score, 0.6)


if __name__ == "__main__":
    unittest.main()
