from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_tools.base import AgentTool, ToolError, ToolExecutionContext, ToolPolicy, ToolResult
from app.meeting_analysis_schema import MeetingAnalysisSchema


class EchoTool(AgentTool):
    def __init__(self, *, policy: ToolPolicy | None = None, fail: Exception | None = None, delay: float = 0.0):
        super().__init__(
            name="echo",
            policy=policy
            or ToolPolicy(
                timeout_seconds=1,
                max_calls_per_run=2,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.fail = fail
        self.delay = delay

    def _execute(self, context: ToolExecutionContext, payload: dict) -> dict:
        if self.delay:
            time.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return {"echo": payload, "_result_source": "unit_test"}


class AgentToolContractTests(unittest.TestCase):
    def test_tool_contracts_round_trip(self) -> None:
        policy = ToolPolicy(
            timeout_seconds=2,
            max_calls_per_run=1,
            retry_count=0,
            read_only=True,
            has_side_effects=False,
            requires_confirmation=False,
        )
        error = ToolError(
            error_type="ValueError",
            error_code="invalid_input",
            message="safe message",
            retryable=False,
        )
        result = ToolResult(
            tool_name="tool",
            status="failed",
            error=error,
            result_source="unit_test",
        )
        context = ToolExecutionContext(run_id="run-1", meeting_id="meeting-1")

        self.assertEqual(ToolPolicy.model_validate(policy.model_dump()), policy)
        self.assertEqual(ToolResult.model_validate(result.model_dump()), result)
        self.assertEqual(ToolExecutionContext.model_validate(context.model_dump()).meeting_id, "meeting-1")

    def test_tool_policy_invalid_configuration(self) -> None:
        with self.assertRaises(ValidationError):
            ToolPolicy(timeout_seconds=0, max_calls_per_run=1, retry_count=0)

        with self.assertRaises(ValidationError):
            ToolPolicy(
                timeout_seconds=1,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=True,
                requires_confirmation=False,
            )

    def test_tool_status_invalid_value(self) -> None:
        with self.assertRaises(ValidationError):
            ToolResult(tool_name="tool", status="done")  # type: ignore[arg-type]

    def test_tool_error_message_is_safe(self) -> None:
        error = ToolError(
            error_type="RuntimeError",
            error_code="tool_failed",
            message="password=*** token=***",
            retryable=False,
            details={"safe": True},
        )

        self.assertNotIn("secret-value", error.model_dump_json())

    def test_duration_is_recorded_by_wrapper(self) -> None:
        result = EchoTool().execute(ToolExecutionContext(), {"value": 1})

        self.assertEqual(result.status, "success")
        self.assertGreaterEqual(result.duration_ms, 0)
        self.assertEqual(result.result_source, "unit_test")

    def test_max_calls_per_run_limit_uses_effective_counts(self) -> None:
        context = ToolExecutionContext()
        tool = EchoTool(
            policy=ToolPolicy(
                timeout_seconds=1,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            )
        )

        self.assertEqual(tool.execute(context).status, "success")
        context.call_counts["echo"] = 0
        second = tool.execute(context)

        self.assertEqual(second.status, "skipped")
        self.assertEqual(second.error.error_code, "max_calls_per_run_exceeded")  # type: ignore[union-attr]

    def test_expired_deadline_returns_timeout(self) -> None:
        context = ToolExecutionContext(deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        result = EchoTool().execute(context)

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error.error_code, "run_deadline_exceeded")  # type: ignore[union-attr]

    def test_tool_timeout_returns_structured_result(self) -> None:
        tool = EchoTool(
            policy=ToolPolicy(
                timeout_seconds=0.01,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
            delay=0.05,
        )
        result = tool.execute(ToolExecutionContext())

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error.error_code, "tool_timeout")  # type: ignore[union-attr]

    def test_regular_exception_returns_failed(self) -> None:
        result = EchoTool(fail=ValueError("bad input")).execute(ToolExecutionContext())

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error.error_code, "invalid_input")  # type: ignore[union-attr]

    def test_retryable_error_is_reported(self) -> None:
        result = EchoTool(fail=ConnectionError("temporary connection issue")).execute(ToolExecutionContext())

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.retryable)
        self.assertTrue(result.error.retryable)  # type: ignore[union-attr]

    def test_mutable_defaults_do_not_leak(self) -> None:
        left = ToolExecutionContext()
        right = ToolExecutionContext()
        left.metadata["trace"] = "left"
        left.call_counts["tool"] = 1

        self.assertEqual(right.metadata, {})
        self.assertEqual(right.call_counts, {})

    def test_import_does_not_change_meeting_analysis_schema(self) -> None:
        before = MeetingAnalysisSchema().model_dump()
        before["metadata"].pop("generated_at", None)
        __import__("app.agent_tools")
        after = MeetingAnalysisSchema().model_dump()
        after["metadata"].pop("generated_at", None)

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
