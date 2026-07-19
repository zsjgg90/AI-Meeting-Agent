from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app.analysis_contract import normalize_meeting_analysis_result  # noqa: E402
from app.meeting_analysis_pipeline import (  # noqa: E402
    analyze_meeting_shadow_mode,
    analyze_meeting_with_fallback,
    run_semantic_shadow_trace,
    run_semantic_pipeline_payload,
)
from app.semantic_event_schema import SemanticEvent  # noqa: E402


def make_event(
    event_id: str,
    intent: str,
    text: str,
    *,
    subject: str = "checkout",
    action: str = "discuss",
    object_: str = "payment",
    status: str = "confirmed",
    owner: str | None = None,
    deadline: str | None = None,
    project: str = "commerce",
    feature: str = "payment",
    confidence: float = 0.9,
) -> SemanticEvent:
    return SemanticEvent.model_validate(
        {
            "event_id": event_id,
            "utterance_id": event_id,
            "segment_id": event_id,
            "speaker": "Speaker 1",
            "speaker_role": None,
            "start_time": None,
            "end_time": None,
            "source_text": text,
            "normalized_text": text,
            "primary_intent": intent,
            "secondary_intents": [],
            "event_type": "information",
            "subject": subject,
            "action": action,
            "object": object_,
            "entities": {
                "persons": [owner] if owner else [],
                "teams": [],
                "projects": [project],
                "features": [feature],
                "dates": [deadline] if deadline else [],
                "versions": [],
                "numbers": [],
            },
            "attributes": {
                "owner": owner,
                "deadline": deadline,
                "priority": "high" if intent == "task_assignment" else "unknown",
                "status": status,
                "polarity": "neutral",
                "certainty": "explicit",
            },
            "evidence": {
                "source_text": text,
                "quote": text,
            },
            "confidence": {
                "intent": confidence,
                "entity": confidence,
                "overall": confidence,
            },
            "needs_review": confidence < 0.7,
        }
    )


class FakeExtractor:
    def __init__(
        self,
        events_by_utterance: dict[str, list[SemanticEvent]],
        failing_utterances: set[str] | None = None,
    ):
        self.events_by_utterance = events_by_utterance
        self.failing_utterances = failing_utterances or set()

    def extract(self, utterance: Any) -> tuple[list[SemanticEvent], list[Any]]:
        if utterance.utterance_id in self.failing_utterances:
            raise RuntimeError("forced single event failure")
        return self.events_by_utterance.get(utterance.utterance_id, []), []


class FailingMapper:
    def map_topics(self, meeting_id: str, topics: list[Any]) -> Any:
        raise RuntimeError("forced pipeline failure")


class EmptyMapper:
    def map_topics(self, meeting_id: str, topics: list[Any]) -> Any:
        from app.six_dimension_schema import SixDimensionResult

        return SixDimensionResult(meeting_id=meeting_id)


class FailingAggregator:
    def aggregate(self, events: list[Any]) -> list[Any]:
        raise RuntimeError("forced shadow failure")


def transcript(ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": item_id,
            "speaker_name": "Speaker 1",
            "start_time": float(index),
            "end_time": float(index + 1),
            "text": f"text for {item_id}",
        }
        for index, item_id in enumerate(ids)
    ]


def semantic_meeting_events() -> dict[str, list[SemanticEvent]]:
    return {
        "agenda": [
            make_event(
                "agenda",
                "agenda_statement",
                "review payment release agenda",
                object_="agenda",
            )
        ],
        "summary": [
            make_event(
                "summary",
                "information",
                "payment release is in beta",
                object_="beta status",
            )
        ],
        "decision": [
            make_event(
                "decision",
                "decision",
                "confirm payment release on Friday",
                object_="release date",
            )
        ],
        "action": [
            make_event(
                "action",
                "task_assignment",
                "Alice ships payment release on Friday",
                action="ship",
                object_="release task",
                owner="Alice",
                deadline="Friday",
            )
        ],
        "issue": [
            make_event(
                "issue",
                "open_issue",
                "callback rule is still open",
                object_="callback rule",
                status="blocked",
            )
        ],
        "risk": [
            make_event(
                "risk",
                "risk_warning",
                "payment timeout risk exists",
                object_="timeout risk",
                status="pending",
            )
        ],
    }


def legacy_payload(summary: str = "legacy summary") -> dict[str, Any]:
    return {
        "meeting_agenda": [{"item": "legacy agenda", "order": 1}],
        "meeting_summary": summary,
        "key_conclusions": [],
        "action_items": [],
        "unresolved_issues": [],
        "risks_and_focus": [],
        "topics": [],
        "_metadata": {},
    }


class MeetingAnalysisPipelineTest(unittest.TestCase):
    def test_full_pipeline_success_and_six_dimensions(self) -> None:
        events = semantic_meeting_events()
        payload = run_semantic_pipeline_payload(
            "meeting-1",
            transcript(list(events.keys())),
            extractor=FakeExtractor(events),
        )

        self.assertEqual(1, len(payload["meeting_agenda"]))
        self.assertIn("payment release is in beta", payload["meeting_summary"])
        self.assertEqual(1, len(payload["key_conclusions"]))
        self.assertEqual(1, len(payload["action_items"]))
        self.assertEqual(1, len(payload["unresolved_issues"]))
        self.assertEqual(1, len(payload["risks_and_focus"]))

    def test_empty_transcript_input(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            [],
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor({}),
        )

        self.assertEqual("legacy summary", payload["meeting_summary"])
        self.assertEqual("empty_semantic_events", payload["_metadata"]["fallback_reason"])
        self.assertEqual(0, payload["_metadata"]["semantic_event_count"])

    def test_non_event_filtered(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["flow"]),
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor(
                {
                    "flow": [
                        make_event(
                            "flow",
                            "non_event",
                            "thanks everyone",
                            status="unknown",
                        )
                    ]
                }
            ),
        )

        self.assertEqual("legacy summary", payload["meeting_summary"])
        self.assertEqual("empty_topic_groups", payload["_metadata"]["fallback_reason"])
        self.assertEqual(1, payload["_metadata"]["semantic_event_count"])
        self.assertEqual(0, payload["_metadata"]["topic_count"])

    def test_resolved_issue_not_unresolved(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["issue", "answer"]),
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor(
                {
                    "issue": [
                        make_event(
                            "issue",
                            "open_issue",
                            "callback rule is open",
                            object_="callback rule",
                            status="blocked",
                        )
                    ],
                    "answer": [
                        make_event(
                            "answer",
                            "decision",
                            "callback rule is resolved",
                            object_="callback rule",
                            status="confirmed",
                        )
                    ],
                }
            ),
        )

        self.assertEqual("empty_six_dimension_output", payload["_metadata"]["fallback_reason"])

    def test_mitigated_risk_status_and_evidence(self) -> None:
        payload = run_semantic_pipeline_payload(
            "meeting-1",
            transcript(["risk", "mitigation"]),
            extractor=FakeExtractor(
                {
                    "risk": [
                        make_event(
                            "risk",
                            "risk_warning",
                            "payment timeout risk exists",
                            object_="timeout risk",
                            status="pending",
                        )
                    ],
                    "mitigation": [
                        make_event(
                            "mitigation",
                            "task_assignment",
                            "add fallback mitigation for payment timeout risk",
                            action="add fallback",
                            object_="timeout risk",
                            status="confirmed",
                        )
                    ],
                }
            ),
        )

        self.assertEqual(1, len(payload["risks_and_focus"]))
        self.assertIn("payment timeout risk exists", payload["risks_and_focus"][0]["source_text"])

    def test_single_event_failure_continues(self) -> None:
        fallback_called = {"value": False}

        def legacy() -> dict[str, Any]:
            fallback_called["value"] = True
            return legacy_payload()

        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["bad", "decision"]),
            legacy_analyzer=legacy,
            extractor=FakeExtractor(
                {
                    "decision": [
                        make_event(
                            "decision",
                            "decision",
                            "confirm fallback-safe release",
                            object_="release date",
                        )
                    ]
                },
                failing_utterances={"bad"},
            ),
        )

        self.assertFalse(fallback_called["value"])
        self.assertEqual(1, len(payload["key_conclusions"]))

    def test_large_meeting_uses_rule_based_fast_path(self) -> None:
        rows = [
            {
                "id": f"long-{index}",
                "speaker_name": "Speaker 1",
                "start_time": float(index),
                "end_time": float(index + 1),
                "text": text,
            }
            for index, text in enumerate(
                [
                    "今天我们对齐版本目标和交付标准。",
                    "本期周期四周，目前需求和原型已经完成。",
                    "后台看板设计存在返工风险。",
                    "我同意砍掉两个非核心功能。",
                    "产品经理今天更新需求文档。",
                    "第三方接口超时方案没有明确，需要补充。",
                    "测试明日启动异常场景用例编写。",
                    "最后统一四周迭代节奏。",
                    "全员无问题。",
                ]
            )
        ]

        payload = run_semantic_pipeline_payload("meeting-1", rows)

        self.assertTrue(payload["meeting_summary"])
        self.assertTrue(payload["meeting_agenda"])
        self.assertTrue(
            payload["key_conclusions"]
            or payload["action_items"]
            or payload["unresolved_issues"]
            or payload["risks_and_focus"]
        )

    def test_shadow_mode_does_not_overwrite_formal_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_meeting_shadow_mode(
                "meeting-1",
                transcript(["agenda", "decision"]),
                legacy_analyzer=lambda: legacy_payload("formal legacy summary"),
                trace_root=Path(tmp),
                extractor=FakeExtractor(semantic_meeting_events()),
            )

            self.assertEqual("formal legacy summary", result["meeting_summary"])
            self.assertEqual("legacy agenda", result["meeting_agenda"][0]["item"])
            self.assertTrue(result["_metadata"]["semantic_shadow_mode"])
            self.assertTrue(Path(result["_metadata"]["semantic_shadow_trace_dir"]).exists())

    def test_shadow_failure_does_not_affect_formal_result(self) -> None:
        result = analyze_meeting_shadow_mode(
            "meeting-1",
            transcript(["agenda"]),
            legacy_analyzer=lambda: legacy_payload("formal survives"),
            extractor=FakeExtractor(semantic_meeting_events()),
            aggregator=FailingAggregator(),
        )

        self.assertEqual("formal survives", result["meeting_summary"])
        self.assertIn("semantic_shadow_error", result["_metadata"])

    def test_shadow_trace_writes_all_intermediate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = run_semantic_shadow_trace(
                "meeting-1",
                transcript(["agenda", "decision", "action", "risk"]),
                trace_root=Path(tmp),
                extractor=FakeExtractor(semantic_meeting_events()),
            )

            expected = {
                "01_utterances.json",
                "02_semantic_events_raw.json",
                "03_semantic_events_validated.json",
                "04_topic_groups.json",
                "05_six_dimension_mapped.json",
                "06_six_dimension_validated.json",
                "07_final_meeting_analysis.json",
                "comparison.md",
            }
            self.assertTrue(expected.issubset({path.name for path in trace_dir.iterdir()}))

            raw = json.loads((trace_dir / "02_semantic_events_raw.json").read_text(encoding="utf-8"))
            self.assertEqual("meeting-1", raw["meeting_id"])
            self.assertTrue(raw["items"][0]["event_id"])
            self.assertTrue(raw["items"][0]["source_text"])

            final = json.loads((trace_dir / "07_final_meeting_analysis.json").read_text(encoding="utf-8"))
            self.assertIn("items", final)
            self.assertIn("analysis", final)

    def test_greeting_does_not_become_formal_agenda_in_shadow_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_meeting_shadow_mode(
                "meeting-1",
                [
                    {
                        "id": "hello",
                        "speaker_name": "PM",
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "text": "各位大家下午好，今天我们开项目周会。",
                    }
                ],
                legacy_analyzer=lambda: legacy_payload("formal only"),
                trace_root=Path(tmp),
            )

            self.assertEqual("legacy agenda", result["meeting_agenda"][0]["item"])
            self.assertNotIn("大家下午好", result["meeting_agenda"][0]["item"])

    def test_empty_shadow_result_does_not_affect_formal_result(self) -> None:
        result = analyze_meeting_shadow_mode(
            "meeting-1",
            transcript(["empty"]),
            legacy_analyzer=lambda: legacy_payload("formal kept"),
            extractor=FakeExtractor({"empty": []}),
        )

        self.assertEqual("formal kept", result["meeting_summary"])

    def test_pipeline_failure_falls_back_to_legacy(self) -> None:
        fallback_called = {"value": False}

        def legacy() -> dict[str, Any]:
            fallback_called["value"] = True
            return legacy_payload()

        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["decision"]),
            legacy_analyzer=legacy,
            extractor=FakeExtractor(
                {
                    "decision": [
                        make_event("decision", "decision", "confirm release")
                    ]
                }
            ),
            mapper=FailingMapper(),
        )

        self.assertTrue(fallback_called["value"])
        self.assertEqual("legacy summary", payload["meeting_summary"])
        self.assertEqual("pipeline_exception", payload["_metadata"]["fallback_reason"])
        self.assertEqual(0, payload["_metadata"]["failed_utterance_count"])

    def test_all_utterances_failed_falls_back(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["bad-1", "bad-2"]),
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor({}, failing_utterances={"bad-1", "bad-2"}),
        )

        self.assertEqual("all_utterances_failed", payload["_metadata"]["fallback_reason"])
        self.assertEqual(2, payload["_metadata"]["failed_utterance_count"])
        self.assertEqual(0, payload["_metadata"]["semantic_event_count"])
        self.assertEqual(0, payload["_metadata"]["topic_count"])

    def test_semantic_events_empty_falls_back(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["empty"]),
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor({"empty": []}),
        )

        self.assertEqual("empty_semantic_events", payload["_metadata"]["fallback_reason"])

    def test_six_dimension_empty_falls_back(self) -> None:
        payload = analyze_meeting_with_fallback(
            "meeting-1",
            transcript(["decision"]),
            legacy_analyzer=lambda: legacy_payload(),
            extractor=FakeExtractor(
                {
                    "decision": [
                        make_event("decision", "decision", "confirm release")
                    ]
                }
            ),
            mapper=EmptyMapper(),
        )

        self.assertEqual("empty_six_dimension_output", payload["_metadata"]["fallback_reason"])
        self.assertEqual(1, payload["_metadata"]["semantic_event_count"])
        self.assertEqual(1, payload["_metadata"]["topic_count"])

    def test_output_compatible_with_existing_schema(self) -> None:
        events = semantic_meeting_events()
        payload = run_semantic_pipeline_payload(
            "meeting-1",
            transcript(list(events.keys())),
            extractor=FakeExtractor(events),
        )

        analysis = normalize_meeting_analysis_result(
            payload,
            model_name="semantic-events+rules",
        )

        self.assertTrue(analysis.meeting_agenda)
        self.assertTrue(analysis.key_conclusions)
        self.assertTrue(analysis.action_items)

    def test_simulated_meeting_keeps_traceable_evidence(self) -> None:
        events = semantic_meeting_events()
        payload = run_semantic_pipeline_payload(
            "meeting-1",
            transcript(list(events.keys())),
            extractor=FakeExtractor(events),
        )

        self.assertTrue(payload["topics"])
        self.assertIn(
            "confirm payment release on Friday",
            payload["key_conclusions"][0]["source_text"],
        )
        self.assertIn(
            "Alice ships payment release on Friday",
            payload["action_items"][0]["source_text"],
        )


if __name__ == "__main__":
    unittest.main()
