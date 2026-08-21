from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.decision_candidate_recall import (
    DecisionCandidate,
    extract_decision_candidates_from_event_trace,
    extract_decision_candidates_from_trace,
)


def _trace_item(
    event_id: str,
    intent: str,
    status: str,
    text: str,
    *,
    segment_id: str = "seg-1",
    confidence: float = 0.9,
) -> dict:
    return {
        "event_id": event_id,
        "source_text": text,
        "primary_intent": intent,
        "status": status,
        "event": {
            "event_id": event_id,
            "segment_id": segment_id,
            "source_text": text,
            "primary_intent": intent,
            "attributes": {"status": status},
            "confidence": {"overall": confidence},
        },
    }


class DecisionCandidateRecallTests(unittest.TestCase):
    def test_confirmed_decision_can_be_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "decision",
                    "confirmed",
                    "We decided to launch plan A next week.",
                )
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertIsInstance(candidates[0], DecisionCandidate)
        self.assertEqual("confirmed", candidates[0].decision_type)
        self.assertEqual("seg-1", candidates[0].source_segment_id)

    def test_proposal_is_not_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "proposal",
                    "pending",
                    "I suggest we launch plan A next week.",
                )
            ]
        }

        self.assertEqual([], extract_decision_candidates_from_event_trace(payload))

    def test_question_is_not_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "question",
                    "open",
                    "Should we launch plan A next week?",
                )
            ]
        }

        self.assertEqual([], extract_decision_candidates_from_event_trace(payload))

    def test_rejection_decision_can_be_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "rejection",
                    "rejected",
                    "We reject the legacy mode request.",
                )
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("rejection", candidates[0].decision_type)

    def test_action_only_item_does_not_pollute_decisions(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "task_assignment",
                    "confirmed",
                    "Alice will update the rollout document.",
                )
            ]
        }

        self.assertEqual([], extract_decision_candidates_from_event_trace(payload))

    def test_scope_change_decision_can_be_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "decision",
                    "confirmed",
                    "We decided the analytics export is out of scope for v1.",
                )
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("scope_change", candidates[0].decision_type)

    def test_chinese_scope_freeze_recalled_from_information_or_risk_event(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "risk_warning",
                    "pending",
                    "V2.5现在原则上冻结范围，除非严重影响上线，否则新需求都放V2.6。",
                ),
                _trace_item("evt-2", "information", "unknown", "确认。", segment_id="seg-2"),
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("scope_change", candidates[0].decision_type)
        self.assertIn("scope_marker", candidates[0].recall_reason)
        self.assertIn("neighbor_confirmation", candidates[0].recall_reason)

    def test_chinese_negative_scope_decisions_are_recalled_from_information_events(self) -> None:
        payload = {
            "items": [
                _trace_item("evt-1", "information", "unknown", "飞书、邮箱、短信推送这版不上实际能力。"),
                _trace_item("evt-2", "information", "unknown", "完整Agent Memory这版不做新增能力。", segment_id="seg-2"),
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(
            [
                "飞书、邮箱、短信推送这版不上实际能力。",
                "完整Agent Memory这版不做新增能力。",
            ],
            [candidate.conclusion for candidate in candidates],
        )
        self.assertEqual(["scope_change", "scope_change"], [candidate.decision_type for candidate in candidates])

    def test_chinese_defer_decisions_are_recalled_from_information_events(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "information",
                    "unknown",
                    "这个优先级先确定一下。 稳定性问题最高。 标题那些优化先放一下。 先把六维输出稳定。",
                ),
                _trace_item(
                    "evt-2",
                    "information",
                    "unknown",
                    "还有一个性能优化先不要急。 等版本稳定以后再看。",
                    segment_id="seg-2",
                ),
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(2, len(candidates))
        self.assertEqual(
            ["标题优化先放一下", "性能优化等版本稳定以后再看"],
            [candidate.conclusion for candidate in candidates],
        )
        self.assertEqual(["scope_change", "scope_change"], [candidate.decision_type for candidate in candidates])
        self.assertTrue(all("scope_marker" in candidate.recall_reason for candidate in candidates))

    def test_chinese_policy_constraint_decision_is_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "information",
                    "unknown",
                    "声纹低置信度不能强制绑定真人名字。",
                )
            ]
        }

        candidates = extract_decision_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("confirmed", candidates[0].decision_type)
        self.assertIn("policy_constraint_marker", candidates[0].recall_reason)

    def test_chinese_false_positive_surfaces_are_not_recalled_even_if_semantic_decisions(self) -> None:
        payload = {
            "items": [
                _trace_item("evt-1", "decision", "confirmed", "先别争这个。这个是不是这版必须改？"),
                _trace_item("evt-2", "decision", "confirmed", "这个必须修。", segment_id="seg-2"),
                _trace_item("evt-3", "decision", "confirmed", "先说功能问题吧，UI后面统一看。", segment_id="seg-3"),
                _trace_item("evt-4", "decision", "confirmed", "建议下个版本再看看。", segment_id="seg-4"),
            ]
        }

        self.assertEqual([], extract_decision_candidates_from_event_trace(payload))

    def test_go_no_go_checkpoint_is_not_recalled_as_payment_removal_decision(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "information",
                    "unknown",
                    "第二，支付还是 V2.5 目标范围，周一 18:00 做 go/no-go 检查。",
                ),
                _trace_item(
                    "evt-2",
                    "information",
                    "unknown",
                    "如果那个时候还不稳定，周二早会再决定要不要关闭支付入口。",
                    segment_id="seg-2",
                ),
            ]
        }

        self.assertEqual([], extract_decision_candidates_from_event_trace(payload))

    def test_extracts_from_semantic_shadow_trace_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp)
            (trace_dir / "03_semantic_events_validated.json").write_text(
                json.dumps(
                    {
                        "items": [
                            _trace_item(
                                "evt-1",
                                "decision",
                                "confirmed",
                                "We decided to launch plan A next week.",
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )

            candidates = extract_decision_candidates_from_trace(trace_dir)

        self.assertEqual(1, len(candidates))
        self.assertEqual(("evt-1",), candidates[0].source_event_ids)


if __name__ == "__main__":
    unittest.main()
