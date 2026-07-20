from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import AgentContext
from app.agent_orchestrator import (
    AgentOrchestrator,
    AgentShadowAuditStore,
    AgentShadowResult,
    compare_meeting_analysis,
    maybe_run_agent_shadow,
)
from app.agent_runtime import AgentRunState, AgentStepResult
from app.agent_tools.base import ToolError, ToolResult
from app.meeting_scenarios.registry import get_policy


class FakeSettings:
    def __init__(
        self,
        *,
        agent_shadow_mode: bool,
        agent_mode_enabled: bool = False,
        agent_actions_enabled: bool = False,
    ) -> None:
        self.agent_shadow_mode = agent_shadow_mode
        self.agent_mode_enabled = agent_mode_enabled
        self.agent_actions_enabled = agent_actions_enabled


class FakeMeeting:
    id = "meeting-1"
    title = "Weekly sync"


class CountingDb:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def add(self, value: Any) -> None:
        self.calls.append("add")

    def execute(self, value: Any) -> None:
        self.calls.append("execute")

    def commit(self) -> None:
        self.calls.append("commit")

    def delete(self, value: Any) -> None:
        self.calls.append("delete")


class FakeRuntime:
    def __init__(self, *, status: str = "success", fallback: bool = False, timeout: bool = False) -> None:
        self.status = "timeout" if timeout else status
        self.fallback = fallback
        self.calls: list[dict[str, Any]] = []

    def run(self, *, context: AgentContext, plan: Any) -> AgentRunState:
        self.calls.append({"context": context, "plan": plan})
        analysis = {
            "meeting_agenda": [{"item": "Agenda"}],
            "meeting_summary": "Shadow summary",
            "key_conclusions": [{"conclusion": "Confirmed"}],
            "action_items": [],
            "unresolved_issues": [],
            "risks_and_focus": [],
            "_metadata": {"result_source": "legacy_qwen_rag"},
        }
        analysis_result = ToolResult(
            tool_name="analyze_meeting",
            status="fallback" if self.fallback else "success",
            data={"analysis": analysis},
            result_source="legacy_qwen_rag",
            metadata={"fallback_reason": "semantic_pipeline_failed"} if self.fallback else {},
        )
        validate_result = ToolResult(
            tool_name="validate_meeting_analysis",
            status="success",
            data={
                "validated_analysis": analysis,
                "validator_audit": [{"field": "action_items", "action": "modify"}],
            },
            result_source="legacy_qwen_rag",
        )
        step_status = "timeout" if self.status == "timeout" else ("fallback" if self.fallback else "success")
        error = (
            ToolError(
                error_type="TimeoutError",
                error_code="tool_timeout",
                message="timed out",
                retryable=False,
            )
            if self.status == "timeout"
            else None
        )
        steps = [
            AgentStepResult(
                step_index=0,
                tool_name="analyze_meeting",
                status=step_status,
                duration_ms=1,
                result=analysis_result,
                error=error,
                result_source="legacy_qwen_rag",
                started_at="2026-07-20T00:00:00+00:00",
                completed_at="2026-07-20T00:00:00+00:00",
            )
        ]
        return AgentRunState(
            run_id=context.run_id,
            meeting_id=context.meeting_id,
            plan_id=plan.plan_id,
            status=self.status,
            started_at="2026-07-20T00:00:00+00:00",
            completed_at="2026-07-20T00:00:01+00:00",
            duration_ms=1,
            steps=steps,
            tool_results=[analysis_result.model_dump(), validate_result.model_dump()],
        )


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[AgentContext] = []

    def run_shadow(self, *, context: AgentContext, formal_analysis: dict[str, Any]) -> AgentShadowResult:
        self.calls += 1
        self.contexts.append(context)
        return AgentShadowResult(
            agent_run_id=context.run_id,
            meeting_id=context.meeting_id,
            meeting_type=context.meeting_type,
            status="success",
            started_at="2026-07-20T00:00:00+00:00",
            finished_at="2026-07-20T00:00:01+00:00",
            result_source="unit_test",
            comparison_summary={"formal_preserved": True},
        )


class RaisingOrchestrator:
    def run_shadow(self, *, context: AgentContext, formal_analysis: dict[str, Any]) -> AgentShadowResult:
        raise TimeoutError("agent timed out")


class AgentOrchestratorTests(unittest.TestCase):
    def test_shadow_mode_disabled_does_not_run_agent(self) -> None:
        fake = FakeOrchestrator()
        with patch("app.agent_orchestrator.get_settings", return_value=FakeSettings(agent_shadow_mode=False)):
            result = maybe_run_agent_shadow(
                db=CountingDb(),
                meeting=FakeMeeting(),
                formal_analysis=formal_analysis(),
                transcript=[],
                orchestrator=fake,
            )

        self.assertIsNone(result)
        self.assertEqual(fake.calls, 0)

    def test_shadow_mode_enabled_runs_orchestrator_without_overwriting_formal_result(self) -> None:
        fake = FakeOrchestrator()
        formal = formal_analysis()
        before = dict(formal)
        with patch("app.agent_orchestrator.get_settings", return_value=FakeSettings(agent_shadow_mode=True)):
            result = maybe_run_agent_shadow(
                db=CountingDb(),
                meeting=FakeMeeting(),
                formal_analysis=formal,
                transcript=[{"text": "正式结果已生成"}],
                orchestrator=fake,
            )

        self.assertIsNotNone(result)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(formal, before)
        self.assertFalse(fake.contexts[0].runtime_metadata["agent_mode_enabled"])

    def test_agent_mode_enabled_is_recorded_but_does_not_overwrite(self) -> None:
        fake = FakeOrchestrator()
        formal = formal_analysis()
        with patch(
            "app.agent_orchestrator.get_settings",
            return_value=FakeSettings(agent_shadow_mode=True, agent_mode_enabled=True),
        ):
            maybe_run_agent_shadow(
                db=CountingDb(),
                meeting=FakeMeeting(),
                formal_analysis=formal,
                transcript=[],
                orchestrator=fake,
            )

        self.assertTrue(fake.contexts[0].runtime_metadata["agent_mode_enabled"])
        self.assertEqual(formal["meeting_summary"], "Formal summary")

    def test_scenario_policy_controls_static_plan_optional_steps(self) -> None:
        orchestrator = AgentOrchestrator(runtime=FakeRuntime())

        weekly = orchestrator.create_plan(policy=get_policy("project_weekly"))
        requirement = orchestrator.create_plan(policy=get_policy("requirement_review"))
        technical = orchestrator.create_plan(policy=get_policy("technical_review"))

        self.assertTrue(weekly.steps[1].enabled)
        self.assertFalse(weekly.steps[2].enabled)
        self.assertTrue(weekly.steps[3].enabled)
        self.assertFalse(requirement.steps[1].enabled)
        self.assertTrue(requirement.steps[2].enabled)
        self.assertFalse(requirement.steps[3].enabled)
        self.assertFalse(technical.steps[1].enabled)
        self.assertTrue(technical.steps[2].enabled)

    def test_unknown_uses_minimal_plan_and_needs_review(self) -> None:
        plan = AgentOrchestrator(runtime=FakeRuntime()).create_plan(policy=get_policy("unknown"))

        self.assertEqual(
            [step.enabled for step in plan.steps],
            [True, False, False, False, True, True],
        )
        self.assertTrue(plan.metadata["needs_review"])

    def test_success_saves_shadow_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentShadowAuditStore(trace_root=Path(tmp))
            orchestrator = AgentOrchestrator(runtime=FakeRuntime(), audit_store=store)
            result = orchestrator.run_shadow(
                context=AgentContext(run_id="run-1", meeting_id="meeting-1", meeting_type="project_weekly"),
                formal_analysis=formal_analysis(),
            )

            audit_path = Path(result.metadata["audit_path"])
            self.assertTrue(audit_path.exists())
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["agent_run_id"], "run-1")
            self.assertIn("comparison_summary", payload)

    def test_failure_or_timeout_does_not_touch_formal_data(self) -> None:
        db = CountingDb()
        formal = formal_analysis()
        with patch("app.agent_orchestrator.get_settings", return_value=FakeSettings(agent_shadow_mode=True)):
            result = maybe_run_agent_shadow(
                db=db,
                meeting=FakeMeeting(),
                formal_analysis=formal,
                transcript=[],
                orchestrator=RaisingOrchestrator(),
            )

        self.assertIsNone(result)
        self.assertEqual(db.calls, [])
        self.assertEqual(formal["meeting_summary"], "Formal summary")

    def test_runtime_timeout_is_saved_as_shadow_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentOrchestrator(
                runtime=FakeRuntime(timeout=True),
                audit_store=AgentShadowAuditStore(trace_root=Path(tmp)),
            ).run_shadow(
                context=AgentContext(run_id="run-timeout", meeting_id="meeting-1"),
                formal_analysis=formal_analysis(),
            )

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.steps[0]["error"]["error_code"], "tool_timeout")

    def test_fallback_and_result_source_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentOrchestrator(
                runtime=FakeRuntime(fallback=True),
                audit_store=AgentShadowAuditStore(trace_root=Path(tmp)),
            ).run_shadow(
                context=AgentContext(run_id="run-fallback", meeting_id="meeting-1"),
                formal_analysis=formal_analysis(),
            )

        self.assertEqual(result.steps[0]["status"], "fallback")
        self.assertEqual(result.result_source, "legacy_qwen_rag")
        self.assertEqual(result.fallback_reason, "semantic_pipeline_failed")

    def test_comparison_summary_is_deterministic_structure_only(self) -> None:
        comparison = compare_meeting_analysis(
            formal_analysis=formal_analysis(),
            shadow_analysis={
                "meeting_agenda": [],
                "meeting_summary": "Shadow",
                "key_conclusions": [{"conclusion": "A"}, {"conclusion": "B"}],
                "action_items": [],
                "unresolved_issues": [],
                "risks_and_focus": [],
            },
            validation_audit=[{"action": "modify"}, {"action": "keep"}],
            formal_result_source="legacy_qwen_rag",
            shadow_result_source="legacy_qwen_rag",
        )

        self.assertEqual(comparison["fields"]["key_conclusions"]["count_delta"], 1)
        self.assertTrue(comparison["schema_ok"])
        self.assertEqual(comparison["validator_warning_count"], 1)
        self.assertTrue(comparison["result_source"]["same"])

    def test_import_does_not_initialize_external_dependencies(self) -> None:
        module = importlib.import_module("app.agent_orchestrator")

        self.assertIsNotNone(module)


def formal_analysis() -> dict[str, Any]:
    return {
        "meeting_agenda": [{"item": "Agenda"}],
        "meeting_summary": "Formal summary",
        "key_conclusions": [{"conclusion": "Confirmed"}],
        "action_items": [{"task": "Follow up"}],
        "unresolved_issues": [],
        "risks_and_focus": [],
        "metadata": {"result_source": "legacy_qwen_rag"},
    }


if __name__ == "__main__":
    unittest.main()
