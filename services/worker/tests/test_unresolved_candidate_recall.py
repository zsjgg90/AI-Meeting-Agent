from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_pipeline import _semantic_unresolved_candidates_from_trace
from app.unresolved_candidate_recall import (
    UnresolvedCandidate,
    extract_unresolved_candidates_from_event_trace,
    extract_unresolved_candidates_from_trace,
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
            "normalized_text": text,
            "primary_intent": intent,
            "attributes": {"status": status},
            "confidence": {"overall": confidence},
        },
    }


class UnresolvedCandidateRecallTest(unittest.TestCase):
    def test_payment_callback_signature_reason_unconfirmed_is_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "information",
                    "unknown",
                    "支付成功回调，签名验证不通过，原因还没确认。",
                )
            ]
        }

        candidates = extract_unresolved_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertIsInstance(candidates[0], UnresolvedCandidate)
        self.assertIn("unresolved_marker", candidates[0].recall_reason)

    def test_third_party_sdk_reason_unresolved_is_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "information",
                    "unknown",
                    "第三方 SDK 和他们最新文档有差异，昨天下午回了一次但没有解决。",
                )
            ]
        }

        candidates = extract_unresolved_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertEqual("第三方 SDK 和他们最新文档有差异，昨天下午回了一次但没有解决。", candidates[0].issue)

    def test_action_like_failure_is_not_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "task_assignment",
                    "pending",
                    "AI分析失败，后端明天下午修。",
                )
            ]
        }

        self.assertEqual([], extract_unresolved_candidates_from_event_trace(payload))

    def test_payment_delay_risk_is_not_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "risk_warning",
                    "pending",
                    "支付可能延期，可能影响上线。",
                )
            ]
        }

        self.assertEqual([], extract_unresolved_candidates_from_event_trace(payload))

    def test_meeting_control_question_is_not_recalled(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "open_issue",
                    "blocked",
                    "还有遗漏吗？",
                )
            ]
        }

        self.assertEqual([], extract_unresolved_candidates_from_event_trace(payload))

    def test_open_issue_intent_is_recalled_when_not_control_question(self) -> None:
        payload = {
            "items": [
                _trace_item(
                    "evt-1",
                    "open_issue",
                    "blocked",
                    "支付回调签名验证为什么失败，目前还没确认。",
                )
            ]
        }

        candidates = extract_unresolved_candidates_from_event_trace(payload)

        self.assertEqual(1, len(candidates))
        self.assertIn("open_issue_intent", candidates[0].recall_reason)

    def test_extracts_from_trace_file_and_pipeline_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp)
            (trace_dir / "03_semantic_events_validated.json").write_text(
                json.dumps(
                    {
                        "items": [
                            _trace_item(
                                "evt-1",
                                "information",
                                "unknown",
                                "支付成功回调，签名验证不通过，原因还没确认。",
                            )
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            candidates = extract_unresolved_candidates_from_trace(trace_dir)
            bridged = _semantic_unresolved_candidates_from_trace(trace_dir)

        self.assertEqual(1, len(candidates))
        self.assertEqual(1, len(bridged))
        self.assertEqual("支付成功回调，签名验证不通过，原因还没确认。", bridged[0]["issue"])


if __name__ == "__main__":
    unittest.main()
