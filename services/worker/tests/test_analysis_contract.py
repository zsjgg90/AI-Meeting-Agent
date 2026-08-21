import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis_contract import (
    ANALYSIS_SCHEMA_VERSION,
    EmptyAnalysisResultError,
    analysis_to_persistence_payload,
    canonicalize_meeting_analysis_aliases,
    ensure_non_empty_analysis_result,
    normalize_meeting_analysis_result,
    persistence_source_segment_id,
)


class AnalysisContractTest(unittest.TestCase):
    FIRST_SEGMENT_ID = "11111111-1111-4111-8111-111111111111"
    SECOND_SEGMENT_ID = "22222222-2222-4222-8222-222222222222"

    def test_normalizes_qwen_result_to_authoritative_schema(self) -> None:
        raw = {
            "meeting_agenda": ["同步背景", {"title": "评估方案"}],
            "meeting_summary": "本次会议围绕项目上线计划进行对齐，确认了范围、节奏和主要风险。",
            "key_conclusions": [
                {"conclusion": "按当前方案推进", "source_text": "就按这个方案推进", "confidence": 0.86}
            ],
            "action_items": [
                {
                    "owner_name": "产品",
                    "task": "补充验收标准",
                    "deadline": None,
                    "priority": "high",
                    "source_text": "产品补充验收标准",
                    "confidence": 0.82,
                }
            ],
            "unresolved_issues": [
                {"issue": "外部接口交付时间未确认", "source_text": "外部接口时间还没确认", "confidence": 0.74}
            ],
            "risks_and_focus": [
                {"risk": "接口延期可能影响联调", "impact": "联调延期", "source_text": "接口延期会影响联调", "confidence": 0.8}
            ],
            "_metadata": {"result_source": "legacy_qwen_rag"},
        }

        analysis = normalize_meeting_analysis_result(raw, model_name="qwen3:14b+rag")

        self.assertEqual(analysis.metadata.schema_version, ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(analysis.metadata.model_name, "qwen3:14b+rag")
        self.assertEqual(analysis.metadata.result_source, "legacy_qwen_rag")
        self.assertEqual(analysis.meeting_agenda[0].order, 1)
        self.assertEqual(analysis.action_items[0].owner_name, "产品")
        self.assertGreater(analysis.metadata.confidence_score, 0)

    def test_maps_authoritative_schema_to_current_persistence_payload(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "会议完成主要事项对齐。",
                "key_conclusions": [{"conclusion": "冻结范围", "source_text": "范围冻结", "confidence": 0.9}],
                "action_items": [{"task": "完成开发", "owner_name": "研发", "source_text": "研发完成开发"}],
            },
            model_name="qwen3:14b+rag",
        )

        payload = analysis_to_persistence_payload(analysis)

        self.assertEqual(payload["overview"], analysis.meeting_summary)
        self.assertEqual(payload["meeting_summary"], analysis.meeting_summary)
        self.assertEqual(payload["decisions"][0]["decision"], "冻结范围")
        self.assertEqual(payload["action_items"][0]["owner_name"], "研发")
        self.assertEqual(payload["metadata"]["schema_version"], ANALYSIS_SCHEMA_VERSION)
        self.assertIsNone(payload["metadata"]["result_source"])

    def test_persistence_payload_keeps_single_segment_uuid(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Validate payment flow",
                        "source_text": "PM: Validate payment flow by Friday.",
                        "source_segment_id": self.FIRST_SEGMENT_ID,
                    }
                ],
            }
        )

        payload = analysis_to_persistence_payload(analysis)

        self.assertEqual(payload["action_items"][0]["source_segment_id"], self.FIRST_SEGMENT_ID)

    def test_persistence_payload_uses_first_uuid_for_multi_segment_evidence(self) -> None:
        source_text = "PM: Validate payment flow.\nQA: QA will rerun regression."
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Validate payment flow and rerun regression",
                        "source_text": source_text,
                        "source_segment_id": f"{self.FIRST_SEGMENT_ID},{self.SECOND_SEGMENT_ID}",
                    }
                ],
            }
        )

        payload = analysis_to_persistence_payload(analysis)
        item = payload["action_items"][0]

        self.assertEqual(item["source_segment_id"], self.FIRST_SEGMENT_ID)
        self.assertNotIn(",", item["source_segment_id"])
        self.assertEqual(item["source_text"], source_text)

    def test_persistence_payload_does_not_write_comma_separated_source_segment_id(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Publish release notes",
                        "source_text": "PM: Publish release notes.",
                        "source_segment_id": f"{self.FIRST_SEGMENT_ID},not-a-uuid",
                    }
                ],
            }
        )

        source_segment_id = analysis_to_persistence_payload(analysis)["action_items"][0]["source_segment_id"]

        self.assertEqual(source_segment_id, self.FIRST_SEGMENT_ID)
        self.assertLessEqual(len(source_segment_id), 36)

    def test_persistence_payload_does_not_overwrite_existing_single_uuid(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Fix search flicker",
                        "source_text": "FE: Fix search flicker.",
                        "source_segment_id": self.SECOND_SEGMENT_ID,
                    }
                ],
            }
        )

        self.assertEqual(
            analysis_to_persistence_payload(analysis)["action_items"][0]["source_segment_id"],
            self.SECOND_SEGMENT_ID,
        )

    def test_persistence_payload_uses_none_when_no_valid_uuid_exists(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Fix search flicker",
                        "source_text": "FE: Fix search flicker.",
                        "source_segment_id": "seg-a,seg-b",
                    }
                ],
            }
        )

        self.assertIsNone(analysis_to_persistence_payload(analysis)["action_items"][0]["source_segment_id"])

    def test_persistence_source_segment_id_ignores_invalid_ids_before_first_uuid(self) -> None:
        self.assertEqual(
            persistence_source_segment_id(f"seg-a,{self.SECOND_SEGMENT_ID}"),
            self.SECOND_SEGMENT_ID,
        )

    def test_rejects_empty_contract_result(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {"会议纪要": {"主要决定": "非契约结构"}},
            model_name="qwen3:14b+rag",
        )

        with self.assertRaises(EmptyAnalysisResultError) as raised:
            ensure_non_empty_analysis_result(analysis)

        self.assertEqual(raised.exception.error_type, "empty_analysis_result")
        self.assertIn("invalid_model_output_contract", str(raised.exception))

    def test_canonicalizes_safe_model_output_aliases_before_normalize(self) -> None:
        raw = {
            "meeting_type": "project_weekly",
            "meeting_type_confidence": 0.8,
            "title_candidate": "Project weekly sync",
            "agenda": ["Progress sync"],
            "summary": "The meeting aligned project progress and risks.",
            "risks_and_concerns": [
                {
                    "risk": "Integration delay",
                    "impact": "Testing schedule may slip",
                    "focus_area": "Integration",
                    "source_text": "Integration delay may affect testing.",
                }
            ],
        }

        canonical = canonicalize_meeting_analysis_aliases(raw)
        analysis = normalize_meeting_analysis_result(raw)

        self.assertNotIn("title_candidate", canonical)
        self.assertNotIn("agenda", canonical)
        self.assertNotIn("summary", canonical)
        self.assertNotIn("risks_and_concerns", canonical)
        self.assertEqual(canonical["meeting_title_candidate"], raw["title_candidate"])
        self.assertEqual(canonical["meeting_agenda"], raw["agenda"])
        self.assertEqual(canonical["meeting_summary"], raw["summary"])
        self.assertEqual(canonical["risks_and_focus"], raw["risks_and_concerns"])
        self.assertEqual(analysis.meeting_title_candidate, raw["title_candidate"])
        self.assertEqual(analysis.meeting_agenda[0].item, "Progress sync")
        self.assertEqual(analysis.meeting_summary, raw["summary"])
        self.assertEqual(analysis.risks_and_focus[0].risk, "Integration delay")

    def test_canonical_fields_win_over_safe_aliases(self) -> None:
        raw = {
            "title_candidate": "alias title",
            "meeting_title_candidate": "canonical title",
            "agenda": ["alias agenda"],
            "meeting_agenda": ["canonical agenda"],
            "summary": "alias summary",
            "meeting_summary": "canonical summary",
            "risks_and_concerns": [{"risk": "alias risk"}],
            "risks_and_focus": [{"risk": "canonical risk"}],
        }

        canonical = canonicalize_meeting_analysis_aliases(raw)
        analysis = normalize_meeting_analysis_result(raw)

        self.assertEqual(canonical["meeting_title_candidate"], "canonical title")
        self.assertEqual(canonical["meeting_agenda"], ["canonical agenda"])
        self.assertEqual(canonical["meeting_summary"], "canonical summary")
        self.assertEqual(canonical["risks_and_focus"], [{"risk": "canonical risk"}])
        self.assertEqual(analysis.meeting_title_candidate, "canonical title")
        self.assertEqual(analysis.meeting_agenda[0].item, "canonical agenda")
        self.assertEqual(analysis.meeting_summary, "canonical summary")
        self.assertEqual(analysis.risks_and_focus[0].risk, "canonical risk")

    def test_adapts_string_array_items_before_normalize(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "key_conclusions": ["Scope is frozen", ""],
                "unresolved_issues": ["Payment stability remains open"],
            }
        )

        self.assertEqual(len(analysis.key_conclusions), 1)
        self.assertEqual(analysis.key_conclusions[0].conclusion, "Scope is frozen")
        self.assertEqual(analysis.key_conclusions[0].source_text, "Scope is frozen")
        self.assertEqual(len(analysis.unresolved_issues), 1)
        self.assertEqual(analysis.unresolved_issues[0].issue, "Payment stability remains open")
        self.assertEqual(analysis.unresolved_issues[0].source_text, "Payment stability remains open")

    def test_adapts_action_item_strings_before_normalize(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    "Chen Tao investigates AI output fluctuation.",
                    "  ",
                    "Zhao Min prepares real meeting samples.",
                ],
            }
        )

        self.assertEqual(len(analysis.action_items), 2)
        self.assertEqual(
            analysis.action_items[0].task,
            "Chen Tao investigates AI output fluctuation.",
        )
        self.assertEqual(
            analysis.action_items[0].source_text,
            "Chen Tao investigates AI output fluctuation.",
        )
        self.assertEqual(
            analysis.action_items[1].task,
            "Zhao Min prepares real meeting samples.",
        )

    def test_adapts_risk_strings_before_normalize(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "risks_and_focus": [
                    "Server resource pressure risk.",
                    "",
                    "Long meeting generation time risk.",
                ],
            }
        )

        self.assertEqual(len(analysis.risks_and_focus), 2)
        self.assertEqual(
            analysis.risks_and_focus[0].risk,
            "Server resource pressure risk.",
        )
        self.assertEqual(
            analysis.risks_and_focus[0].source_text,
            "Server resource pressure risk.",
        )
        self.assertEqual(
            analysis.risks_and_focus[1].risk,
            "Long meeting generation time risk.",
        )

    def test_adapts_content_items_before_normalize(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "owner": "Frontend",
                        "content": "Fix search result flicker",
                        "deadline": "2026-10-12",
                    }
                ],
                "risks_and_focus": [
                    {
                        "content": "Third-party payment may block release",
                        "impact": "Release schedule",
                    }
                ],
            }
        )

        self.assertEqual(len(analysis.action_items), 1)
        self.assertEqual(analysis.action_items[0].task, "Fix search result flicker")
        self.assertEqual(analysis.action_items[0].owner_name, "Frontend")
        self.assertEqual(analysis.action_items[0].source_text, "Fix search result flicker")
        self.assertEqual(len(analysis.risks_and_focus), 1)
        self.assertEqual(analysis.risks_and_focus[0].risk, "Third-party payment may block release")
        self.assertEqual(analysis.risks_and_focus[0].impact, "Release schedule")
        self.assertEqual(analysis.risks_and_focus[0].source_text, "Third-party payment may block release")

    def test_canonical_item_keys_win_over_content_aliases(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "action_items": [
                    {
                        "task": "Canonical task",
                        "content": "Alias task",
                    }
                ],
                "risks_and_focus": [
                    {
                        "risk": "Canonical risk",
                        "content": "Alias risk",
                    }
                ],
            }
        )

        self.assertEqual(analysis.action_items[0].task, "Canonical task")
        self.assertEqual(analysis.risks_and_focus[0].risk, "Canonical risk")
        self.assertEqual(analysis.action_items[0].source_text, "Canonical task")
        self.assertEqual(analysis.risks_and_focus[0].source_text, "Canonical risk")

    def test_adapts_missing_source_text_from_canonical_item_key(self) -> None:
        analysis = normalize_meeting_analysis_result(
            {
                "meeting_summary": "Summary",
                "key_conclusions": [{"conclusion": "Canonical conclusion"}],
                "action_items": [{"task": "Canonical task"}],
                "unresolved_issues": [{"issue": "Canonical issue"}],
                "risks_and_focus": [{"risk": "Canonical risk"}],
            }
        )

        self.assertEqual(analysis.key_conclusions[0].source_text, "Canonical conclusion")
        self.assertEqual(analysis.action_items[0].source_text, "Canonical task")
        self.assertEqual(analysis.unresolved_issues[0].source_text, "Canonical issue")
        self.assertEqual(analysis.risks_and_focus[0].source_text, "Canonical risk")

    def test_preserves_string_risk_and_action_items_during_normalization(self) -> None:
        raw = {
            "meeting_summary": "Overview keeps the facts.",
            "key_conclusions": [
                "AI stability is the highest priority.",
                "Server pressure needs assessment.",
            ],
            "action_items": [
                "Chen Tao investigates AI output fluctuation.",
                "Zhao Min prepares real meeting samples.",
            ],
            "risks_and_focus": [
                "Server resource pressure risk.",
                "Long meeting generation time risk.",
            ],
        }

        analysis = normalize_meeting_analysis_result(raw)

        self.assertEqual(len(raw["risks_and_focus"]), 2)
        self.assertEqual(len(analysis.risks_and_focus), 2)
        self.assertEqual(
            analysis.risks_and_focus[0].risk,
            "Server resource pressure risk.",
        )
        self.assertEqual(
            analysis.risks_and_focus[0].source_text,
            "Server resource pressure risk.",
        )
        self.assertEqual(len(raw["action_items"]), 2)
        self.assertEqual(len(analysis.action_items), 2)
        self.assertEqual(
            analysis.action_items[0].task,
            "Chen Tao investigates AI output fluctuation.",
        )
        self.assertEqual(
            analysis.action_items[0].source_text,
            "Chen Tao investigates AI output fluctuation.",
        )
        self.assertEqual(len(raw["key_conclusions"]), 2)
        self.assertEqual(len(analysis.key_conclusions), 2)


if __name__ == "__main__":
    unittest.main()
