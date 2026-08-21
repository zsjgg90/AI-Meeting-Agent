import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decision_fusion import MAX_SEMANTIC_DECISIONS, fuse_key_conclusions_with_decisions
from app.meeting_analysis_schema import KeyConclusion, MeetingAnalysisSchema


def analysis_with_conclusions(conclusions: list[KeyConclusion]) -> MeetingAnalysisSchema:
    return MeetingAnalysisSchema(
        meeting_summary="summary",
        meeting_agenda=[],
        key_conclusions=conclusions,
        action_items=[],
        unresolved_issues=[],
        risks_and_focus=[],
    )


def candidate(
    conclusion: str,
    *,
    decision_type: str = "confirmed",
    polarity: str = "positive",
    decision_object: str | None = None,
    source_text: str | None = None,
    score: float = 0.9,
) -> dict:
    return {
        "conclusion": conclusion,
        "source_text": source_text or conclusion,
        "decision_type": decision_type,
        "polarity": polarity,
        "decision_object": decision_object or conclusion.lower(),
        "score": score,
    }


class DecisionFusionTests(unittest.TestCase):
    def test_semantic_decision_supplements_missing_conclusion(self) -> None:
        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([]),
            [
                candidate(
                    "We decided to launch plan A next week.",
                    decision_object="launch|next|week",
                )
            ],
        )

        self.assertEqual(
            [item.conclusion for item in result.key_conclusions],
            ["We decided to launch plan A next week."],
        )

    def test_legacy_conclusion_has_priority_over_semantic_duplicate(self) -> None:
        legacy = KeyConclusion(
            conclusion="The decision is to launch plan A next week.",
            source_text="PM: The decision is to launch plan A next week.",
            confidence=0.95,
        )

        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([legacy]),
            [
                candidate(
                    "We decided to launch plan A next week.",
                    decision_object="launch|next|week",
                    score=0.99,
                )
            ],
        )

        self.assertEqual(len(result.key_conclusions), 1)
        self.assertEqual(result.key_conclusions[0].conclusion, legacy.conclusion)
        self.assertEqual(result.key_conclusions[0].confidence, 0.95)

    def test_duplicate_semantic_decision_keeps_highest_score(self) -> None:
        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([]),
            [
                candidate(
                    "We decided to launch plan A next week.",
                    decision_object="launch|next|week",
                    score=0.7,
                ),
                candidate(
                    "The decision is to launch plan A next week.",
                    decision_object="launch|next|week",
                    score=0.95,
                ),
            ],
        )

        self.assertEqual(len(result.key_conclusions), 1)
        self.assertEqual(
            result.key_conclusions[0].conclusion,
            "The decision is to launch plan A next week.",
        )

    def test_proposal_candidate_is_filtered(self) -> None:
        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([]),
            [
                candidate(
                    "I suggest we launch plan A next week.",
                    decision_object="launch|next|week",
                )
            ],
        )

        self.assertEqual(result.key_conclusions, [])

    def test_rejection_decision_is_added(self) -> None:
        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([]),
            [
                candidate(
                    "We rejected the legacy mode request.",
                    decision_type="rejection",
                    polarity="negative",
                    decision_object="legacy|mode",
                )
            ],
        )

        self.assertEqual(len(result.key_conclusions), 1)
        self.assertEqual(result.key_conclusions[0].conclusion, "We rejected the legacy mode request.")

    def test_semantic_decision_append_count_is_limited(self) -> None:
        candidates = [
            candidate(
                f"We decided to launch plan {index}.",
                decision_object=f"launch|plan|{index}",
                score=1.0 - (index * 0.01),
            )
            for index in range(MAX_SEMANTIC_DECISIONS + 2)
        ]

        result = fuse_key_conclusions_with_decisions(
            analysis_with_conclusions([]),
            candidates,
        )

        self.assertEqual(len(result.key_conclusions), MAX_SEMANTIC_DECISIONS)
        self.assertEqual(
            [item.conclusion for item in result.key_conclusions],
            [f"We decided to launch plan {index}." for index in range(MAX_SEMANTIC_DECISIONS)],
        )


if __name__ == "__main__":
    unittest.main()
