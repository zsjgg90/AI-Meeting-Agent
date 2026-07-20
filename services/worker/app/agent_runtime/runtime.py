from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.agent_contract import AgentContext
from app.agent_runtime.registry import ToolRegistry, UnknownToolError
from app.agent_tools.base import ToolError, ToolExecutionContext, ToolResult, ToolStatus


StepStatus = Literal["success", "failed", "timeout", "skipped", "fallback"]
RunStatus = Literal["success", "failed", "timeout", "partial", "skipped"]


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False
    enabled: bool = True
    continue_on_failure: bool = False


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = "agent-runtime-static-plan-v1"
    steps: tuple[ExecutionStep, ...] = Field(default_factory=tuple)
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_index: int
    tool_name: str
    status: StepStatus
    optional: bool = False
    duration_ms: float = 0.0
    result: ToolResult | None = None
    error: ToolError | None = None
    result_source: str = "unknown"
    started_at: str
    completed_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    meeting_id: str = ""
    project_id: str = ""
    plan_id: str
    status: RunStatus = "success"
    started_at: str
    completed_at: str | None = None
    duration_ms: float = 0.0
    steps: list[AgentStepResult] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    _tool_context: ToolExecutionContext = PrivateAttr()


class AgentRuntime:
    def __init__(self, *, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(self, *, context: AgentContext, plan: ExecutionPlan) -> AgentRunState:
        started_at = time.perf_counter()
        now = _utc_now()
        run_state = AgentRunState(
            run_id=context.run_id,
            meeting_id=context.meeting_id,
            project_id=context.project_id,
            plan_id=plan.plan_id,
            started_at=now,
            runtime_metadata={
                "schema_version": context.runtime_metadata.get("schema_version"),
                "plan_metadata": dict(plan.metadata),
            },
        )
        tool_context = ToolExecutionContext(
            run_id=context.run_id,
            meeting_id=context.meeting_id,
            project_id=context.project_id,
            user_id=context.user_id,
            meeting_type=context.meeting_type,
            deadline_at=plan.deadline_at,
            metadata={"objective": context.objective},
        )
        run_state._tool_context = tool_context

        stopped = False
        for index, step in enumerate(plan.steps):
            if not step.enabled:
                run_state.steps.append(self._skipped_step(index=index, step=step))
                continue

            step_result = self._execute_step(
                index=index,
                step=step,
                agent_context=context,
                tool_context=tool_context,
                run_state=run_state,
            )
            run_state.steps.append(step_result)
            if step_result.result is not None:
                run_state.tool_results.append(step_result.result.model_dump())

            if step_result.status in {"failed", "timeout"} and not step.continue_on_failure:
                stopped = True
                break

        run_state.status = self._resolve_run_status(run_state.steps, stopped=stopped)
        run_state.completed_at = _utc_now()
        run_state.duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        run_state.runtime_metadata["call_counts"] = dict(tool_context.call_counts)
        return run_state

    def _execute_step(
        self,
        *,
        index: int,
        step: ExecutionStep,
        agent_context: AgentContext,
        tool_context: ToolExecutionContext,
        run_state: AgentRunState,
    ) -> AgentStepResult:
        step_started_at = _utc_now()
        started_at = time.perf_counter()
        try:
            tool = self.registry.get_tool(step.tool_name)
            if tool.policy.has_side_effects:
                raise ValueError(f"Tool {step.tool_name} has side effects and cannot run in Phase 4A.")
            payload = self._resolve_payload(step=step, agent_context=agent_context, run_state=run_state)
            result = tool.execute(tool_context, payload)
            return AgentStepResult(
                step_index=index,
                tool_name=step.tool_name,
                status=result.status,
                optional=step.optional,
                duration_ms=result.duration_ms,
                result=result,
                error=result.error,
                result_source=result.result_source,
                started_at=step_started_at,
                completed_at=_utc_now(),
                metadata={"continue_on_failure": step.continue_on_failure},
            )
        except UnknownToolError as exc:
            error = ToolError(
                error_type=exc.__class__.__name__,
                error_code="unknown_tool",
                message=str(exc),
                retryable=False,
            )
        except Exception as exc:
            error = ToolError(
                error_type=exc.__class__.__name__,
                error_code="runtime_step_failed",
                message=str(exc),
                retryable=False,
            )
        return AgentStepResult(
            step_index=index,
            tool_name=step.tool_name,
            status="failed",
            optional=step.optional,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error=error,
            started_at=step_started_at,
            completed_at=_utc_now(),
            metadata={"continue_on_failure": step.continue_on_failure},
        )

    def _resolve_payload(
        self,
        *,
        step: ExecutionStep,
        agent_context: AgentContext,
        run_state: AgentRunState,
    ) -> dict[str, Any]:
        payload = dict(step.payload)
        if step.tool_name == "get_meeting_context":
            payload.setdefault("meeting_id", agent_context.meeting_id)
        elif step.tool_name == "search_meeting_history":
            payload.setdefault("project_id", agent_context.project_id)
            payload.setdefault("meeting_type", agent_context.meeting_type)
            payload.setdefault("exclude_meeting_id", agent_context.meeting_id)
            if agent_context.objective:
                payload.setdefault("query", agent_context.objective)
        elif step.tool_name == "search_project_knowledge":
            if agent_context.objective:
                payload.setdefault("query", agent_context.objective)
        elif step.tool_name == "get_open_action_items":
            payload.setdefault("meeting_id", agent_context.meeting_id)
        elif step.tool_name == "analyze_meeting":
            payload.setdefault("meeting_id", agent_context.meeting_id)
            payload.setdefault("transcript", agent_context.transcript or self._meeting_context_transcript(run_state))
        elif step.tool_name == "validate_meeting_analysis":
            payload.setdefault("meeting_id", agent_context.meeting_id)
            payload.setdefault("analysis", agent_context.meeting_analysis or self._analysis_result(run_state))
            payload.setdefault("transcript", agent_context.transcript or self._meeting_context_transcript(run_state))
        return payload

    def _latest_data(self, run_state: AgentRunState, tool_name: str) -> dict[str, Any]:
        for step in reversed(run_state.steps):
            if step.tool_name == tool_name and step.result is not None:
                return step.result.data
        return {}

    def _meeting_context_transcript(self, run_state: AgentRunState) -> list[dict[str, Any]]:
        data = self._latest_data(run_state, "get_meeting_context")
        transcript = data.get("transcript_segments")
        return transcript if isinstance(transcript, list) else []

    def _analysis_result(self, run_state: AgentRunState) -> dict[str, Any]:
        data = self._latest_data(run_state, "analyze_meeting")
        analysis = data.get("analysis")
        return analysis if isinstance(analysis, dict) else {}

    def _skipped_step(self, *, index: int, step: ExecutionStep) -> AgentStepResult:
        now = _utc_now()
        return AgentStepResult(
            step_index=index,
            tool_name=step.tool_name,
            status="skipped",
            optional=step.optional,
            duration_ms=0.0,
            started_at=now,
            completed_at=now,
            metadata={"skip_reason": "disabled_by_execution_plan"},
        )

    def _resolve_run_status(self, steps: list[AgentStepResult], *, stopped: bool) -> RunStatus:
        if not steps:
            return "skipped"
        statuses = {step.status for step in steps}
        if "timeout" in statuses and stopped:
            return "timeout"
        if "failed" in statuses and stopped:
            return "failed"
        if "failed" in statuses or "timeout" in statuses or "skipped" in statuses:
            return "partial"
        return "success"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_default_execution_plan(
    *,
    include_meeting_history: bool = False,
    include_project_knowledge: bool = False,
    include_open_action_items: bool = False,
    deadline_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExecutionPlan:
    return ExecutionPlan(
        deadline_at=deadline_at,
        metadata=metadata or {},
        steps=(
            ExecutionStep(tool_name="get_meeting_context"),
            ExecutionStep(
                tool_name="search_meeting_history",
                optional=True,
                enabled=include_meeting_history,
                continue_on_failure=True,
            ),
            ExecutionStep(
                tool_name="search_project_knowledge",
                optional=True,
                enabled=include_project_knowledge,
                continue_on_failure=True,
            ),
            ExecutionStep(
                tool_name="get_open_action_items",
                optional=True,
                enabled=include_open_action_items,
                continue_on_failure=True,
            ),
            ExecutionStep(tool_name="analyze_meeting"),
            ExecutionStep(tool_name="validate_meeting_analysis"),
        ),
    )


__all__ = [
    "AgentRunState",
    "AgentRuntime",
    "AgentStepResult",
    "ExecutionPlan",
    "ExecutionStep",
    "RunStatus",
    "StepStatus",
    "create_default_execution_plan",
]
