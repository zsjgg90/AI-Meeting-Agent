from __future__ import annotations

import importlib
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_contract import AgentContext
from app.agent_runtime import (
    AgentRuntime,
    ExecutionPlan,
    ExecutionStep,
    ToolRegistry,
    UnknownToolError,
    create_default_execution_plan,
)
from app.agent_runtime.registry import ToolRegistryError, ToolRegistryPolicyError, create_default_tool_registry
from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class RecordingTool(AgentTool):
    def __init__(
        self,
        name: str,
        *,
        status: str = "success",
        result_source: str = "unit_test",
        delay: float = 0.0,
        fail: Exception | None = None,
        max_calls_per_run: int = 3,
        timeout_seconds: float = 1.0,
        has_side_effects: bool = False,
        requires_confirmation: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            policy=ToolPolicy(
                timeout_seconds=timeout_seconds,
                max_calls_per_run=max_calls_per_run,
                retry_count=0,
                read_only=not has_side_effects,
                has_side_effects=has_side_effects,
                requires_confirmation=requires_confirmation,
            ),
        )
        self.status = status
        self.result_source = result_source
        self.delay = delay
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(dict(payload))
        if self.delay:
            time.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        data: dict[str, Any] = {
            "payload": dict(payload),
            "_result_source": self.result_source,
        }
        if self.name == "get_meeting_context":
            data["transcript_segments"] = [{"speaker": "PM", "text": "Confirmed scope."}]
        if self.name == "analyze_meeting":
            data["analysis"] = {
                "meeting_summary": "Confirmed scope.",
                "_metadata": {"result_source": self.result_source},
            }
        if self.status != "success":
            data["_tool_status"] = self.status
        if self.status == "fallback":
            data["_metadata"] = {"fallback_reason": "semantic_pipeline_failed"}
        return data


class AgentRuntimeTests(unittest.TestCase):
    def test_registry_register_get_list_duplicate_and_unknown_tool(self) -> None:
        tool = RecordingTool("first")
        registry = ToolRegistry()
        registry.register(tool)

        self.assertIs(registry.get_tool("first"), tool)
        self.assertEqual(registry.list_tool_names(), ("first",))
        self.assertEqual(registry.list_tools(), (tool,))

        with self.assertRaises(ToolRegistryError):
            registry.register(RecordingTool("first"))
        with self.assertRaises(UnknownToolError):
            registry.get_tool("missing")

    def test_registry_rejects_side_effect_tool_for_phase_4a(self) -> None:
        with self.assertRaises(ToolRegistryPolicyError):
            ToolRegistry((RecordingTool("write_tool", has_side_effects=True, requires_confirmation=True),))

    def test_default_registry_declares_six_tools_without_calling_factories(self) -> None:
        calls: list[str] = []
        registry = create_default_tool_registry(
            db_provider=lambda: calls.append("db"),
            retriever_factory=lambda: calls.append("rag"),
            analysis_service_factory=lambda: calls.append("model"),
            validator=lambda analysis, transcript: (analysis, []),
        )

        self.assertEqual(
            registry.list_tool_names(),
            (
                "get_meeting_context",
                "search_meeting_history",
                "search_project_knowledge",
                "get_open_action_items",
                "analyze_meeting",
                "validate_meeting_analysis",
            ),
        )
        self.assertEqual(calls, [])

    def test_runtime_executes_steps_in_order(self) -> None:
        first = RecordingTool("first")
        second = RecordingTool("second")
        runtime = AgentRuntime(registry=ToolRegistry((first, second)))

        state = runtime.run(
            context=AgentContext(run_id="run-1", meeting_id="m-1"),
            plan=ExecutionPlan(steps=(ExecutionStep(tool_name="first"), ExecutionStep(tool_name="second"))),
        )

        self.assertEqual(state.status, "success")
        self.assertEqual([step.tool_name for step in state.steps], ["first", "second"])
        self.assertEqual(len(first.calls), 1)
        self.assertEqual(len(second.calls), 1)
        self.assertGreaterEqual(state.duration_ms, 0)

    def test_optional_disabled_step_is_skipped(self) -> None:
        optional = RecordingTool("optional")
        required = RecordingTool("required")
        runtime = AgentRuntime(registry=ToolRegistry((optional, required)))

        state = runtime.run(
            context=AgentContext(run_id="run-1"),
            plan=ExecutionPlan(
                steps=(
                    ExecutionStep(tool_name="optional", optional=True, enabled=False),
                    ExecutionStep(tool_name="required"),
                )
            ),
        )

        self.assertEqual([step.status for step in state.steps], ["skipped", "success"])
        self.assertEqual(optional.calls, [])
        self.assertEqual(len(required.calls), 1)
        self.assertEqual(state.status, "partial")

    def test_default_execution_plan_uses_fixed_order_and_explicit_optional_flags(self) -> None:
        plan = create_default_execution_plan(include_meeting_history=True, include_open_action_items=True)

        self.assertEqual(
            [step.tool_name for step in plan.steps],
            [
                "get_meeting_context",
                "search_meeting_history",
                "search_project_knowledge",
                "get_open_action_items",
                "analyze_meeting",
                "validate_meeting_analysis",
            ],
        )
        self.assertTrue(plan.steps[1].enabled)
        self.assertFalse(plan.steps[2].enabled)
        self.assertTrue(plan.steps[3].enabled)
        self.assertTrue(plan.steps[1].continue_on_failure)

    def test_failure_stops_or_continues_by_plan(self) -> None:
        failing = RecordingTool("failing", fail=ValueError("bad input"))
        after = RecordingTool("after")
        runtime = AgentRuntime(registry=ToolRegistry((failing, after)))

        stopped = runtime.run(
            context=AgentContext(run_id="run-1"),
            plan=ExecutionPlan(steps=(ExecutionStep(tool_name="failing"), ExecutionStep(tool_name="after"))),
        )
        self.assertEqual(stopped.status, "failed")
        self.assertEqual(len(stopped.steps), 1)
        self.assertEqual(after.calls, [])

        continued = runtime.run(
            context=AgentContext(run_id="run-2"),
            plan=ExecutionPlan(
                steps=(
                    ExecutionStep(tool_name="failing", continue_on_failure=True),
                    ExecutionStep(tool_name="after"),
                )
            ),
        )
        self.assertEqual(continued.status, "partial")
        self.assertEqual([step.status for step in continued.steps], ["failed", "success"])
        self.assertEqual(len(after.calls), 1)

    def test_timeout_deadline_and_call_limit_are_recorded(self) -> None:
        slow = RecordingTool("slow", delay=0.05, timeout_seconds=0.01, max_calls_per_run=1)
        runtime = AgentRuntime(registry=ToolRegistry((slow,)))

        timed_out = runtime.run(context=AgentContext(run_id="run-1"), plan=ExecutionPlan(steps=(ExecutionStep(tool_name="slow"),)))
        self.assertEqual(timed_out.status, "timeout")
        self.assertEqual(timed_out.steps[0].status, "timeout")
        self.assertEqual(timed_out.steps[0].error.error_code, "tool_timeout")  # type: ignore[union-attr]
        self.assertGreaterEqual(timed_out.steps[0].duration_ms, 0)

        one_call = RecordingTool("one_call", max_calls_per_run=1)
        call_limit = AgentRuntime(registry=ToolRegistry((one_call,))).run(
            context=AgentContext(run_id="run-2"),
            plan=ExecutionPlan(
                steps=(
                    ExecutionStep(tool_name="one_call"),
                    ExecutionStep(tool_name="one_call"),
                )
            ),
        )
        self.assertEqual([step.status for step in call_limit.steps], ["success", "skipped"])
        self.assertEqual(call_limit.steps[1].error.error_code, "max_calls_per_run_exceeded")  # type: ignore[union-attr]

        deadline = AgentRuntime(registry=ToolRegistry((RecordingTool("deadline"),))).run(
            context=AgentContext(run_id="run-3"),
            plan=ExecutionPlan(
                steps=(ExecutionStep(tool_name="deadline"),),
                deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            ),
        )
        self.assertEqual(deadline.status, "timeout")
        self.assertEqual(deadline.steps[0].error.error_code, "run_deadline_exceeded")  # type: ignore[union-attr]

    def test_fallback_status_and_result_source_are_preserved(self) -> None:
        tool = RecordingTool("analyze_meeting", status="fallback", result_source="legacy_qwen_rag")
        state = AgentRuntime(registry=ToolRegistry((tool,))).run(
            context=AgentContext(run_id="run-1", transcript=[{"text": "Confirmed."}]),
            plan=ExecutionPlan(steps=(ExecutionStep(tool_name="analyze_meeting"),)),
        )

        self.assertEqual(state.status, "success")
        self.assertEqual(state.steps[0].status, "fallback")
        self.assertEqual(state.steps[0].result_source, "legacy_qwen_rag")
        self.assertEqual(state.steps[0].result.metadata["fallback_reason"], "semantic_pipeline_failed")  # type: ignore[union-attr]

    def test_runtime_passes_previous_results_to_analysis_and_validation(self) -> None:
        context_tool = RecordingTool("get_meeting_context")
        analyze_tool = RecordingTool("analyze_meeting", result_source="legacy_qwen_rag")
        validate_tool = RecordingTool("validate_meeting_analysis")
        runtime = AgentRuntime(registry=ToolRegistry((context_tool, analyze_tool, validate_tool)))

        state = runtime.run(
            context=AgentContext(run_id="run-1", meeting_id="m-1"),
            plan=ExecutionPlan(
                steps=(
                    ExecutionStep(tool_name="get_meeting_context"),
                    ExecutionStep(tool_name="analyze_meeting"),
                    ExecutionStep(tool_name="validate_meeting_analysis"),
                )
            ),
        )

        self.assertEqual(state.status, "success")
        self.assertEqual(analyze_tool.calls[0]["transcript"], [{"speaker": "PM", "text": "Confirmed scope."}])
        self.assertEqual(validate_tool.calls[0]["analysis"]["meeting_summary"], "Confirmed scope.")
        self.assertEqual(validate_tool.calls[0]["transcript"], [{"speaker": "PM", "text": "Confirmed scope."}])

    def test_runtime_import_does_not_initialize_external_dependencies(self) -> None:
        module = importlib.import_module("app.agent_runtime")

        self.assertIsNotNone(module)

    def test_execution_plan_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ExecutionStep(tool_name="tool", unexpected=True)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
