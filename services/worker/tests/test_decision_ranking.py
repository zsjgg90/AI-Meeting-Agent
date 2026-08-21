import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decision_candidate_recall import DecisionCandidate
from app.decision_ranking import RankedDecisionCandidate, rank_and_deduplicate_decisions


def candidate(
    conclusion: str,
    *,
    decision_type: str = "confirmed",
    source_text: str | None = None,
    confidence: float = 0.9,
    segment_id: str = "seg-1",
    event_id: str = "evt-1",
    recall_reason: tuple[str, ...] = ("confirmed_decision_intent",),
) -> DecisionCandidate:
    return DecisionCandidate(
        conclusion=conclusion,
        source_text=source_text or conclusion,
        source_segment_id=segment_id,
        source_event_ids=(event_id,),
        topic_id="topic-1",
        decision_type=decision_type,
        confidence=confidence,
        recall_reason=recall_reason,
    )


class DecisionRankingTests(unittest.TestCase):
    def test_confirmed_decision_is_ranked_with_component_scores(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate("We decided to launch plan A next week."),
                candidate("Background discussion without decision markers.", confidence=0.72),
            ]
        )

        self.assertIsInstance(ranked[0], RankedDecisionCandidate)
        self.assertEqual("confirmed", ranked[0].candidate.decision_type)
        self.assertEqual("positive", ranked[0].polarity)
        self.assertGreater(ranked[0].confirmation_score, 0)
        self.assertGreater(ranked[0].evidence_score, 0)
        self.assertGreater(ranked[0].semantic_decision_score, 0)
        self.assertGreaterEqual(ranked[0].score, ranked[-1].score)

    def test_rejection_decision_is_preserved(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "We reject the legacy mode request.",
                    decision_type="rejection",
                    recall_reason=("rejection_intent",),
                )
            ]
        )

        self.assertEqual(1, len(ranked))
        self.assertEqual("rejection", ranked[0].candidate.decision_type)
        self.assertEqual("negative", ranked[0].polarity)

    def test_duplicate_decision_keeps_highest_scored_candidate(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "We decided to launch plan A next week.",
                    confidence=0.72,
                    event_id="evt-low",
                ),
                candidate(
                    "The decision is to launch plan A next week.",
                    confidence=0.95,
                    segment_id="seg-2",
                    event_id="evt-high",
                ),
            ]
        )

        self.assertEqual(1, len(ranked))
        self.assertEqual(("evt-high",), ranked[0].candidate.source_event_ids)

    def test_proposal_candidate_is_rejected(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "I suggest we launch plan A next week.",
                    recall_reason=("confirmed_decision_intent",),
                )
            ]
        )

        self.assertEqual([], ranked)

    def test_question_candidate_is_rejected(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "Should we launch plan A next week?",
                    recall_reason=("confirmed_decision_intent",),
                )
            ]
        )

        self.assertEqual([], ranked)

    def test_action_only_candidate_is_rejected(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "Alice will update the rollout document.",
                    recall_reason=("confirmed_decision_intent",),
                )
            ]
        )

        self.assertEqual([], ranked)

    def test_chinese_false_positive_candidates_are_rejected(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate("先别争这个。这个是不是这版必须改？", event_id="evt-question"),
                candidate("这个必须修。", segment_id="seg-2", event_id="evt-action"),
                candidate("先说功能问题吧，UI后面统一看。", segment_id="seg-3", event_id="evt-control"),
                candidate("建议下个版本再看看。", segment_id="seg-4", event_id="evt-proposal"),
            ]
        )

        self.assertEqual([], ranked)

    def test_chinese_scope_and_policy_candidates_are_preserved(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "飞书、邮箱、短信推送这版不上实际能力。",
                    decision_type="scope_change",
                    recall_reason=("scope_marker",),
                ),
                candidate(
                    "声纹低置信度不能强制绑定真人名字。",
                    decision_type="confirmed",
                    segment_id="seg-2",
                    event_id="evt-2",
                    recall_reason=("policy_constraint_marker",),
                ),
            ]
        )

        self.assertEqual(2, len(ranked))
        self.assertEqual(
            {"飞书、邮箱、短信推送这版不上实际能力。", "声纹低置信度不能强制绑定真人名字。"},
            {item.candidate.conclusion for item in ranked},
        )

    def test_scope_change_decision_is_preserved(self) -> None:
        ranked = rank_and_deduplicate_decisions(
            [
                candidate(
                    "We decided analytics export is out of scope for v1.",
                    decision_type="scope_change",
                    recall_reason=("confirmed_decision_intent", "scope_marker"),
                )
            ]
        )

        self.assertEqual(1, len(ranked))
        self.assertEqual("scope_change", ranked[0].candidate.decision_type)
        self.assertEqual("scope_change", ranked[0].polarity)
        self.assertGreater(ranked[0].scope_decision_score, 0)


if __name__ == "__main__":
    unittest.main()
