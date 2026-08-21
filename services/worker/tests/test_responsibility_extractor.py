import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.responsibility_extractor import ResponsibilityContext, ResponsibilityExtractor
from app.semantic_event_schema import SemanticEvent
from app.speaker_identity import ManualSpeakerConfirmation, SpeakerResolver
from app.speaker_role import ManualRoleConfirmation, RoleResolver


def event(**kwargs) -> SemanticEvent:
    base = {
        "event_id": "event-1",
        "utterance_id": "utt-1",
        "segment_id": "seg-1",
        "speaker": "speaker_1",
        "source_text": "",
        "primary_intent": "task_assignment",
        "event_type": "action",
        "action": "处理",
        "object": "上线清单",
        "confidence": {"overall": 0.86},
    }
    base.update(kwargs)
    return SemanticEvent(**base)


class ResponsibilityExtractorTest(unittest.TestCase):
    def test_explicit_owner_statement_is_recognized(self) -> None:
        semantic_event = event(
            source_text="Alice 负责上线清单整理。",
            attributes={"owner": "Alice", "status": "confirmed", "certainty": "explicit"},
            action="整理",
            object="上线清单",
        )

        context = ResponsibilityExtractor().extract(semantic_event=semantic_event, meeting_id="meeting-1")

        self.assertEqual(context.responsibility_type, "explicit_owner")
        self.assertEqual(context.owner, "Alice")
        self.assertEqual(context.task, "整理上线清单")
        self.assertEqual(context.speaker_id, "speaker_1")
        self.assertEqual(context.source_type, "semantic_event")
        self.assertEqual(context.evidence[0].type, "explicit_owner_text")
        self.assertEqual(context.evidence[0].owner_text, "Alice")
        self.assertEqual(context.evidence[0].supported_fields, ["task", "owner"])
        self.assertGreaterEqual(context.confidence, 0.86)

    def test_first_person_commitment_uses_speaker_context_as_owner_candidate(self) -> None:
        semantic_event = event(
            source_text="我会在周五前整理上线清单。",
            primary_intent="commitment",
            attributes={"status": "confirmed", "certainty": "explicit"},
            action="整理",
            object="上线清单",
        )
        speaker_context = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Zhang San",
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")
        role_context = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Product Manager",
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        context = ResponsibilityExtractor().extract(
            semantic_event=semantic_event,
            meeting_id="meeting-1",
            speaker_context=speaker_context,
            role_context=role_context,
        )

        self.assertEqual(context.responsibility_type, "commitment")
        self.assertEqual(context.owner, "Zhang San")
        self.assertEqual(context.speaker_id, "meeting:meeting-1:speaker_1")
        self.assertEqual(context.identity_context, speaker_context)
        self.assertEqual(context.role_context, role_context)
        self.assertEqual(context.evidence[0].type, "commitment_text")
        self.assertFalse(context.evidence[0].requires_confirmation)

    def test_assignment_statement_is_recognized(self) -> None:
        semantic_event = event(
            source_text="请 Bob 负责同步测试环境配置。",
            attributes={"status": "confirmed", "certainty": "explicit"},
            action="同步",
            object="测试环境配置",
        )

        context = ResponsibilityExtractor().extract(semantic_event=semantic_event, meeting_id="meeting-1")

        self.assertEqual(context.responsibility_type, "assignment")
        self.assertEqual(context.owner, "Bob")
        self.assertEqual(context.task, "同步测试环境配置")
        self.assertEqual(context.evidence[0].type, "assignment_text")

    def test_discussion_does_not_generate_responsibility(self) -> None:
        semantic_event = event(
            source_text="我们讨论一下上线清单是否需要补充。",
            primary_intent="information",
            event_type="information",
            attributes={"status": "discussing", "certainty": "contextual"},
            action="补充",
            object="上线清单",
        )

        context = ResponsibilityExtractor().extract(semantic_event=semantic_event, meeting_id="meeting-1")

        self.assertEqual(context.responsibility_type, "unknown")
        self.assertIsNone(context.owner)
        self.assertEqual(context.evidence[0].type, "unknown_owner")
        self.assertEqual(context.evidence[0].supported_fields, ["task"])

    def test_unknown_returns_null_owner_when_owner_evidence_is_missing(self) -> None:
        semantic_event = event(
            source_text="上线清单需要补充。",
            attributes={"owner": "Alice", "status": "pending", "certainty": "inferred"},
            action="补充",
            object="上线清单",
        )

        context = ResponsibilityExtractor().extract(semantic_event=semantic_event, meeting_id="meeting-1")

        self.assertEqual(context.responsibility_type, "unknown")
        self.assertIsNone(context.owner)
        self.assertEqual(context.task, "补充上线清单")
        self.assertEqual(context.evidence[0].source_text, "上线清单需要补充。")

    def test_role_context_alone_does_not_create_owner(self) -> None:
        semantic_event = event(
            source_text="登录接口风险需要后续跟进。",
            primary_intent="risk_warning",
            event_type="risk",
            attributes={"status": "pending", "certainty": "explicit"},
            action="跟进",
            object="登录接口风险",
        )
        speaker_context = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Li Si",
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")
        role_context = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Engineering Lead",
                )
            ]
        ).resolve(meeting_id="meeting-1", speaker_label="speaker_1")

        context = ResponsibilityExtractor().extract(
            semantic_event=semantic_event,
            meeting_id="meeting-1",
            speaker_context=speaker_context,
            role_context=role_context,
        )

        self.assertEqual(context.responsibility_type, "unknown")
        self.assertIsNone(context.owner)
        self.assertEqual(context.identity_context.display_name, "Li Si")
        self.assertEqual(context.role_context.confirmed_role, "Engineering Lead")

    def test_unknown_context_rejects_owner(self) -> None:
        with self.assertRaises(ValidationError):
            ResponsibilityContext(
                responsibility_id="resp:bad",
                responsibility_type="unknown",
                task="补充上线清单",
                owner="Alice",
                evidence=[
                    {
                        "type": "unknown_owner",
                        "source_text": "上线清单需要补充。",
                        "task_text": "补充上线清单",
                        "supported_fields": ["task"],
                        "confidence": 0.2,
                    }
                ],
                confidence=0.2,
            )


if __name__ == "__main__":
    unittest.main()
