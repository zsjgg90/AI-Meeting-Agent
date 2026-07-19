from __future__ import annotations

import asyncio
import concurrent.futures
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from app.agent_contract import MeetingType
from app.observability import safe_error


ToolStatus = Literal["success", "failed", "timeout", "skipped", "fallback"]


class ToolError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error_type: str
    error_code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool_name: str
    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    duration_ms: float = 0.0
    result_source: str = "unknown"
    retryable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: float = Field(gt=0)
    max_calls_per_run: int = Field(gt=0)
    retry_count: int = Field(ge=0)
    read_only: bool = True
    has_side_effects: bool = False
    requires_confirmation: bool = False

    @model_validator(mode="after")
    def validate_read_only_side_effects(self) -> "ToolPolicy":
        if self.read_only and self.has_side_effects:
            raise ValueError("read_only tools cannot declare side effects")
        if self.has_side_effects and not self.requires_confirmation:
            raise ValueError("side-effecting tools must require confirmation")
        return self


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = ""
    meeting_id: str = ""
    project_id: str = ""
    user_id: str = ""
    meeting_type: MeetingType = "unknown"
    call_counts: dict[str, int] = Field(default_factory=dict)
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _effective_call_counts: dict[str, int] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self._effective_call_counts = dict(self.call_counts)

    def remaining_seconds(self) -> float | None:
        if self.deadline_at is None:
            return None
        deadline = self.deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return (deadline - datetime.now(timezone.utc)).total_seconds()

    def reserve_call(self, tool_name: str, max_calls: int) -> bool:
        current_count = self._effective_call_counts.get(tool_name, 0)
        if current_count >= max_calls:
            self.call_counts = dict(self._effective_call_counts)
            return False
        self._effective_call_counts[tool_name] = current_count + 1
        self.call_counts = dict(self._effective_call_counts)
        return True


class AgentTool(ABC):
    name: str
    policy: ToolPolicy

    def __init__(self, *, name: str, policy: ToolPolicy) -> None:
        self.name = name
        self.policy = policy

    def execute(self, context: ToolExecutionContext, payload: dict[str, Any] | None = None) -> ToolResult:
        input_payload = dict(payload or {})
        started_at = time.perf_counter()

        if not context.reserve_call(self.name, self.policy.max_calls_per_run):
            return self._result(
                status="skipped",
                started_at=started_at,
                error=ToolError(
                    error_type="ToolCallLimitExceeded",
                    error_code="max_calls_per_run_exceeded",
                    message=f"Tool {self.name} exceeded max_calls_per_run.",
                    retryable=False,
                    details={"max_calls_per_run": self.policy.max_calls_per_run},
                ),
            )

        timeout_seconds = self._resolve_timeout(context)
        if timeout_seconds <= 0:
            return self._result(
                status="timeout",
                started_at=started_at,
                error=ToolError(
                    error_type="ToolDeadlineExceeded",
                    error_code="run_deadline_exceeded",
                    message=f"Run deadline expired before executing {self.name}.",
                    retryable=False,
                ),
            )

        attempts = self.policy.retry_count + 1
        last_result: ToolResult | None = None
        for attempt in range(1, attempts + 1):
            result = self._execute_once(context, input_payload, timeout_seconds, started_at, attempt)
            if result.status == "success" or result.status == "fallback":
                return result
            last_result = result
            if not result.retryable or attempt >= attempts:
                return result

        return last_result or self._result(status="failed", started_at=started_at)

    def _execute_once(
        self,
        context: ToolExecutionContext,
        payload: dict[str, Any],
        timeout_seconds: float,
        started_at: float,
        attempt: int,
    ) -> ToolResult:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._execute, context, payload)
        try:
            data = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return self._result(
                status="timeout",
                started_at=started_at,
                error=ToolError(
                    error_type="TimeoutError",
                    error_code="tool_timeout",
                    message=f"Tool {self.name} timed out.",
                    retryable=False,
                    details={"timeout_seconds": timeout_seconds, "attempt": attempt},
                ),
            )
        except TimeoutError as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            return self._result(
                status="timeout",
                started_at=started_at,
                error=self._error_from_exception(exc, retryable=False),
            )
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        except Exception as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            tool_error = self._error_from_exception(exc)
            return self._result(
                status="failed",
                started_at=started_at,
                error=tool_error,
                retryable=tool_error.retryable,
            )
        else:
            executor.shutdown(wait=False, cancel_futures=True)

        if not isinstance(data, dict):
            data = {"value": data}
        status = data.pop("_tool_status", "success")
        if status not in {"success", "failed", "timeout", "skipped", "fallback"}:
            status = "success"
        error_payload = data.pop("_tool_error", None)
        error = ToolError.model_validate(error_payload) if isinstance(error_payload, dict) else None
        return self._result(
            status=status,  # type: ignore[arg-type]
            started_at=started_at,
            data=data,
            error=error,
            result_source=str(data.pop("_result_source", data.get("result_source", "unknown"))),
            metadata=dict(data.pop("_metadata", {})),
            retryable=bool(error.retryable) if error else False,
        )

    def _resolve_timeout(self, context: ToolExecutionContext) -> float:
        timeout_seconds = self.policy.timeout_seconds
        remaining = context.remaining_seconds()
        if remaining is not None:
            timeout_seconds = min(timeout_seconds, remaining)
        return timeout_seconds

    def _result(
        self,
        *,
        status: ToolStatus,
        started_at: float,
        data: dict[str, Any] | None = None,
        error: ToolError | None = None,
        result_source: str = "unknown",
        retryable: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            status=status,
            data=data or {},
            error=error,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            result_source=result_source,
            retryable=retryable,
            metadata=metadata or {},
        )

    def _error_from_exception(self, exc: Exception, retryable: bool | None = None) -> ToolError:
        error_code = "tool_failed"
        inferred_retryable = False
        message = safe_error(exc)
        lowered = message.lower()
        if isinstance(exc, TimeoutError) or "timeout" in lowered:
            error_code = "tool_timeout"
            inferred_retryable = False
        elif "connection" in lowered or "connect" in lowered or "temporar" in lowered:
            error_code = "external_connection_failed"
            inferred_retryable = True
        elif isinstance(exc, ValueError):
            error_code = "invalid_input"
            inferred_retryable = False
        elif "not found" in lowered:
            error_code = "resource_not_found"
            inferred_retryable = False

        return ToolError(
            error_type=exc.__class__.__name__,
            error_code=error_code,
            message=message,
            retryable=inferred_retryable if retryable is None else retryable,
            details={},
        )

    @abstractmethod
    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


__all__ = [
    "AgentTool",
    "ToolError",
    "ToolExecutionContext",
    "ToolPolicy",
    "ToolResult",
    "ToolStatus",
]
