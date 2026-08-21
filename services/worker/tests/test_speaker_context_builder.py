import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.meeting_analysis_pipeline import (
    _memory_current_context,
    _reasoning_shadow_payloads,
    analyze_meeting_shadow_mode,
    run_semantic_shadow_trace,
)
from app.speaker_context_builder import SpeakerContextBuilder, collect_speaker_labels
from app.speaker_identity import ManualSpeakerConfirmation, SpeakerResolver
from app.speaker_role import ManualRoleConfirmation, RoleResolver


def transcript_rows() -> list[dict]:
    return [
        {
            "id": f"seg-{index}",
            "speaker_label": "speaker_1" if index % 2 == 0 else "speaker_2",
            "start_time": float(index * 2),
            "end_time": float(index * 2 + 1),
            "text": text,
        }
        for index, text in enumerate(
            [
                "今天我们对齐项目进度和上线风险。",
                "我会同步接口联调结果。",
                "目前登录接口已经完成。",
                "如果验收延期，可能影响上线。",
                "确认本周冻结需求。",
                "需要补充回归测试清单。",
                "没有其他技术难点。",
                "默认配置需要同步给测试。",
                "今天会议到这里结束。",
            ]
        )
    ]


class SpeakerContextBuilderTest(unittest.TestCase):
    def test_collect_speaker_labels_preserves_first_seen_order(self) -> None:
        self.assertEqual(collect_speaker_labels(transcript_rows()), ["speaker_1", "speaker_2"])

    def test_unknown_speaker_contexts_are_built_without_evidence(self) -> None:
        result = SpeakerContextBuilder().build(meeting_id="meeting-1", transcript=transcript_rows())

        self.assertEqual(set(result.speaker_contexts), {"meeting:meeting-1:speaker_1", "meeting:meeting-1:speaker_2"})
        context = result.speaker_contexts["meeting:meeting-1:speaker_1"]
        self.assertEqual(context.display_name, "speaker_1")
        self.assertEqual(context.identity_source, "unknown")
        self.assertEqual(context.identity_status, "anonymous")
        self.assertEqual(context.evidence, [])
        role_context = result.speaker_role_context["meeting:meeting-1:speaker_1"]
        self.assertIsNone(role_context.confirmed_role)
        self.assertIsNone(role_context.suggested_role)
        self.assertEqual(role_context.role_status, "unknown")

    def test_manual_confirmation_maps_to_speaker_context(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_2",
                    display_name="Confirmed Speaker",
                    role="Project Manager",
                    confidence=0.98,
                )
            ]
        )

        result = SpeakerContextBuilder(resolver).build(meeting_id="meeting-1", transcript=transcript_rows())

        confirmed = result.speaker_contexts["meeting:meeting-1:speaker_2"]
        self.assertEqual(confirmed.display_name, "Confirmed Speaker")
        self.assertEqual(confirmed.role, "Project Manager")
        self.assertEqual(confirmed.identity_source, "manual_confirmation")
        self.assertEqual(confirmed.identity_status, "confirmed")
        self.assertEqual(confirmed.confidence, 0.98)
        self.assertEqual(confirmed.evidence[0].type, "manual_confirmation")

    def test_manual_role_confirmation_maps_to_role_context(self) -> None:
        role_resolver = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_2",
                    role="Project Manager",
                    confidence=0.99,
                )
            ]
        )

        result = SpeakerContextBuilder(role_resolver=role_resolver).build(
            meeting_id="meeting-1",
            transcript=transcript_rows(),
        )

        confirmed = result.speaker_role_context["meeting:meeting-1:speaker_2"]
        self.assertEqual(confirmed.confirmed_role, "Project Manager")
        self.assertIsNone(confirmed.suggested_role)
        self.assertEqual(confirmed.role_source, "manual_confirmation")
        self.assertEqual(confirmed.role_status, "confirmed")
        self.assertEqual(confirmed.confidence, 0.99)

    def test_shadow_trace_writes_speaker_context_without_changing_analysis(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Confirmed Speaker",
                )
            ]
        )
        role_resolver = RoleResolver(
            manual_confirmations=[
                ManualRoleConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    role="Product Manager",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            trace_dir = run_semantic_shadow_trace(
                "meeting-1",
                transcript_rows(),
                trace_root=Path(temp_dir),
                speaker_resolver=resolver,
                role_resolver=role_resolver,
            )

            speaker_context_path = trace_dir / "00_speaker_contexts.json"
            responsibility_path = trace_dir / "08_responsibility_evidence_matrix.json"
            memory_snapshot_path = trace_dir / "memory_snapshot.json"
            retrieved_memory_path = trace_dir / "retrieved_memory_context.json"
            memory_audit_path = trace_dir / "memory_retrieval_audit.json"
            reasoning_contexts_path = trace_dir / "reasoning_contexts.json"
            reasoning_audit_path = trace_dir / "reasoning_audit.json"
            action_candidates_path = trace_dir / "action_candidates.json"
            tool_contracts_path = trace_dir / "tool_action_contracts.json"
            action_audit_path = trace_dir / "action_audit.json"
            final_path = trace_dir / "07_final_meeting_analysis.json"
            self.assertTrue(speaker_context_path.exists())
            self.assertTrue(responsibility_path.exists())
            self.assertTrue(memory_snapshot_path.exists())
            self.assertTrue(retrieved_memory_path.exists())
            self.assertTrue(memory_audit_path.exists())
            self.assertTrue(reasoning_contexts_path.exists())
            self.assertTrue(reasoning_audit_path.exists())
            self.assertTrue(action_candidates_path.exists())
            self.assertTrue(tool_contracts_path.exists())
            self.assertTrue(action_audit_path.exists())
            speaker_context_payload = json.loads(speaker_context_path.read_text(encoding="utf-8"))
            responsibility_payload = json.loads(responsibility_path.read_text(encoding="utf-8"))
            memory_snapshot_payload = json.loads(memory_snapshot_path.read_text(encoding="utf-8"))
            retrieved_memory_payload = json.loads(retrieved_memory_path.read_text(encoding="utf-8"))
            memory_audit_payload = json.loads(memory_audit_path.read_text(encoding="utf-8"))
            reasoning_contexts_payload = json.loads(reasoning_contexts_path.read_text(encoding="utf-8"))
            reasoning_audit_payload = json.loads(reasoning_audit_path.read_text(encoding="utf-8"))
            action_candidates_payload = json.loads(action_candidates_path.read_text(encoding="utf-8"))
            tool_contracts_payload = json.loads(tool_contracts_path.read_text(encoding="utf-8"))
            action_audit_payload = json.loads(action_audit_path.read_text(encoding="utf-8"))
            final_payload = json.loads(final_path.read_text(encoding="utf-8"))

        self.assertIn("meeting:meeting-1:speaker_1", speaker_context_payload["speaker_contexts"])
        self.assertEqual(
            speaker_context_payload["speaker_contexts"]["meeting:meeting-1:speaker_1"]["display_name"],
            "Confirmed Speaker",
        )
        self.assertIn("speaker_contexts", final_payload)
        self.assertIn("speaker_role_context", speaker_context_payload)
        self.assertIn("speaker_role_context", final_payload)
        self.assertIn("responsibility_evidence_matrix", final_payload)
        self.assertIn("responsibility_contexts", responsibility_payload)
        self.assertIn("responsibility_matrix", responsibility_payload)
        self.assertIn("consistency_status", responsibility_payload)
        self.assertGreater(len(responsibility_payload["responsibility_contexts"]), 0)
        self.assertGreater(len(responsibility_payload["responsibility_matrix"]["rows"]), 0)
        self.assertGreater(len(memory_snapshot_payload["memories"]), 0)
        first_memory = memory_snapshot_payload["memories"][0]
        self.assertIn("memory_id", first_memory)
        self.assertIn("memory_type", first_memory)
        self.assertIn("content", first_memory)
        self.assertIn("evidence", first_memory)
        self.assertIn("confidence", first_memory)
        self.assertIn("status", first_memory)
        self.assertIn("memories", retrieved_memory_payload)
        self.assertIn("token_cost", retrieved_memory_payload)
        self.assertGreater(len(retrieved_memory_payload["memories"]), 0)
        self.assertIn("relevance_score", retrieved_memory_payload["memories"][0])
        self.assertIn("token_cost", retrieved_memory_payload["memories"][0])
        self.assertIn("evidence", retrieved_memory_payload["memories"][0])
        self.assertLessEqual(retrieved_memory_payload["token_cost"], retrieved_memory_payload["token_budget"])
        self.assertIn("candidate_count", memory_audit_payload)
        self.assertIn("selected_count", memory_audit_payload)
        self.assertIn("filtered_reason", memory_audit_payload)
        self.assertIn("token_budget", memory_audit_payload)
        self.assertEqual(
            memory_audit_payload["selected_count"],
            len(retrieved_memory_payload["memories"]),
        )
        self.assertIn("items", reasoning_contexts_payload)
        self.assertGreater(len(reasoning_contexts_payload["items"]), 0)
        first_reasoning = reasoning_contexts_payload["items"][0]
        self.assertIn("reasoning_type", first_reasoning)
        self.assertIn("claim", first_reasoning)
        self.assertIn("evidence_refs", first_reasoning)
        self.assertIn("confidence", first_reasoning)
        self.assertIn("impact_scope", first_reasoning)
        self.assertIn("requires_confirmation", first_reasoning)
        self.assertIn("suggested_next_step", first_reasoning)
        self.assertIn("candidate_count", reasoning_audit_payload)
        self.assertIn("generated_count", reasoning_audit_payload)
        self.assertIn("filtered_count", reasoning_audit_payload)
        self.assertIn("filtered_reason", reasoning_audit_payload)
        self.assertIn("confirmation_required_count", reasoning_audit_payload)
        self.assertIn("confidence_distribution", reasoning_audit_payload)
        self.assertEqual(
            reasoning_audit_payload["generated_count"],
            len(reasoning_contexts_payload["items"]),
        )
        self.assertIn("items", action_candidates_payload)
        self.assertGreater(len(action_candidates_payload["items"]), 0)
        first_action = action_candidates_payload["items"][0]
        self.assertIn("action_id", first_action)
        self.assertIn("action_type", first_action)
        self.assertIn("reason", first_action)
        self.assertIn("evidence_refs", first_action)
        self.assertIn("confidence", first_action)
        self.assertIn("requires_confirmation", first_action)
        self.assertIn("items", tool_contracts_payload)
        self.assertEqual(len(tool_contracts_payload["items"]), len(action_candidates_payload["items"]))
        first_contract = tool_contracts_payload["items"][0]
        self.assertIn("tool_id", first_contract)
        self.assertIn("action_id", first_contract)
        self.assertIn("required_permissions", first_contract)
        self.assertIn("confirmation_required", first_contract)
        self.assertEqual(first_contract["execution_mode"], "disabled")
        self.assertIn("blocked_reason", first_contract)
        self.assertIn("candidate_count", action_audit_payload)
        self.assertIn("contract_count", action_audit_payload)
        self.assertFalse(action_audit_payload["execution_attempted"])
        self.assertFalse(action_audit_payload["writes_performed"])
        self.assertEqual(action_audit_payload["candidate_count"], len(action_candidates_payload["items"]))
        self.assertEqual(action_audit_payload["contract_count"], len(tool_contracts_payload["items"]))
        self.assertEqual(
            final_payload["speaker_role_context"]["meeting:meeting-1:speaker_1"]["confirmed_role"],
            "Product Manager",
        )
        self.assertNotIn("speaker_contexts", final_payload["analysis"])
        self.assertNotIn("speaker_role_context", final_payload["analysis"])
        self.assertNotIn("responsibility_evidence_matrix", final_payload["analysis"])
        self.assertNotIn("memory_snapshot", final_payload["analysis"])
        self.assertNotIn("retrieved_memory_context", final_payload["analysis"])
        self.assertNotIn("memory_retrieval_audit", final_payload["analysis"])
        self.assertNotIn("reasoning_contexts", final_payload["analysis"])
        self.assertNotIn("reasoning_audit", final_payload["analysis"])
        self.assertNotIn("action_candidates", final_payload["analysis"])
        self.assertNotIn("tool_action_contracts", final_payload["analysis"])
        self.assertNotIn("action_audit", final_payload["analysis"])

    def test_reasoning_shadow_payload_filters_memory_without_evidence(self) -> None:
        current_context = _memory_current_context(
            "meeting-unsupported",
            analysis={
                "meeting_summary": "Login API risk review.",
                "meeting_agenda": [],
                "key_conclusions": [],
                "action_items": [],
                "unresolved_issues": [],
                "risks_and_focus": [{"risk": "Login API stability may block launch."}],
            },
            utterances=[],
        )
        contexts_payload, audit_payload = _reasoning_shadow_payloads(
            "meeting-unsupported",
            retrieved_memory_payload={
                "as_of": "2026-08-03T10:20:00Z",
                "source_snapshot_as_of": "2026-08-03T10:20:00Z",
                "current_meeting_id": "meeting-unsupported",
                "retrieved_at": "2026-08-03T10:20:00Z",
                "token_budget": 1200,
                "token_cost": 10,
                "memories": [
                    {
                        "memory_id": "mem:meeting:unsupported-risk",
                        "memory_type": "meeting",
                        "content": {
                            "meeting_memory_type": "risk",
                            "text": "Login API stability may block launch.",
                            "effective_status": "active",
                        },
                        "relevance_score": 0.8,
                        "evidence": [],
                        "token_cost": 10,
                    }
                ],
            },
            responsibility_shadow_payload={"responsibility_matrix": {"rows": []}},
            current_context=current_context,
        )

        self.assertEqual(contexts_payload["items"], [])
        self.assertEqual(audit_payload["generated_count"], 0)
        self.assertEqual(audit_payload["filtered_reason"]["missing_evidence"], 1)

    def test_reasoning_shadow_payload_marks_conflict_for_confirmation(self) -> None:
        current_context = _memory_current_context(
            "meeting-conflict",
            analysis={
                "meeting_summary": "Action owner review.",
                "meeting_agenda": [],
                "key_conclusions": [],
                "action_items": [{"task": "Investigate login API stability"}],
                "unresolved_issues": [],
                "risks_and_focus": [],
            },
            utterances=[],
        )
        contexts_payload, audit_payload = _reasoning_shadow_payloads(
            "meeting-conflict",
            retrieved_memory_payload={
                "as_of": "2026-08-03T10:20:00Z",
                "source_snapshot_as_of": "2026-08-03T10:20:00Z",
                "current_meeting_id": "meeting-conflict",
                "retrieved_at": "2026-08-03T10:20:00Z",
                "token_budget": 1200,
                "token_cost": 0,
                "memories": [],
            },
            responsibility_shadow_payload={
                "responsibility_matrix": {
                    "rows": [
                        {
                            "task_key": "task:login-api",
                            "action_owner": "Bob",
                            "responsibility_candidates": [
                                {
                                    "responsibility_id": "resp:meeting-conflict:seg-1:alice",
                                    "responsibility_type": "explicit_owner",
                                    "task": "Investigate login API stability",
                                    "owner": "Alice",
                                    "confidence": 0.84,
                                    "requires_confirmation": False,
                                }
                            ],
                            "evidence": [
                                {
                                    "type": "explicit_owner_text",
                                    "source_type": "semantic_event",
                                    "meeting_id": "meeting-conflict",
                                    "segment_id": "seg-1",
                                    "source_text": "Alice owns the login API stability investigation.",
                                    "owner_text": "Alice",
                                    "task_text": "Investigate login API stability",
                                    "supported_fields": ["task", "owner"],
                                    "confidence": 0.84,
                                }
                            ],
                            "confidence": 0.84,
                            "consistency_status": "owner_conflict",
                        }
                    ]
                }
            },
            current_context=current_context,
        )

        self.assertEqual(len(contexts_payload["items"]), 1)
        candidate = contexts_payload["items"][0]
        self.assertEqual(candidate["reasoning_type"], "responsibility_analysis")
        self.assertTrue(candidate["requires_confirmation"])
        self.assertTrue(any(ref["support_level"] == "conflicts" for ref in candidate["evidence_refs"]))
        self.assertEqual(audit_payload["confirmation_required_count"], 1)

    def test_shadow_trace_responsibility_matrix_handles_unknown_without_owner_fill(self) -> None:
        transcript = [
            {
                "id": "seg-1",
                "speaker_label": "speaker_1",
                "text": "Follow-up is needed.",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            trace_dir = run_semantic_shadow_trace(
                "meeting-unknown",
                transcript,
                trace_root=Path(temp_dir),
            )

            responsibility_payload = json.loads(
                (trace_dir / "08_responsibility_evidence_matrix.json").read_text(encoding="utf-8")
            )
            final_payload = json.loads(
                (trace_dir / "07_final_meeting_analysis.json").read_text(encoding="utf-8")
            )

        rows = responsibility_payload["responsibility_matrix"]["rows"]
        self.assertGreater(len(rows), 0)
        self.assertTrue(any(row["consistency_status"] == "unknown" for row in rows))
        self.assertTrue(
            any(candidate["owner"] is None for row in rows for candidate in row["responsibility_candidates"])
        )
        self.assertNotIn("responsibility_evidence_matrix", final_payload["analysis"])

    def test_analyze_shadow_mode_keeps_formal_result_unchanged(self) -> None:
        resolver = SpeakerResolver(
            manual_confirmations=[
                ManualSpeakerConfirmation(
                    meeting_id="meeting-1",
                    speaker_label="speaker_1",
                    display_name="Confirmed Speaker",
                )
            ]
        )
        formal_result = {
            "meeting_summary": "Formal summary remains the source of truth.",
            "meeting_agenda": [],
            "key_conclusions": [],
            "action_items": [],
            "unresolved_issues": [],
            "risks_and_focus": [],
            "_metadata": {"result_source": "legacy_qwen_rag"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = analyze_meeting_shadow_mode(
                "meeting-1",
                transcript_rows(),
                legacy_analyzer=lambda: dict(formal_result),
                trace_root=Path(temp_dir),
                speaker_resolver=resolver,
            )

        self.assertEqual(result["meeting_summary"], "Formal summary remains the source of truth.")
        self.assertEqual(result["meeting_agenda"], [])
        self.assertNotIn("speaker_contexts", result)
        self.assertNotIn("speaker_role_context", result)
        self.assertNotIn("responsibility_evidence_matrix", result)
        self.assertNotIn("memory_snapshot", result)
        self.assertNotIn("retrieved_memory_context", result)
        self.assertNotIn("memory_retrieval_audit", result)
        self.assertTrue(result["_metadata"]["semantic_shadow_mode"])


if __name__ == "__main__":
    unittest.main()
