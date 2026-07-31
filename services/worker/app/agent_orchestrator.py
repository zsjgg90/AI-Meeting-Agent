from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agent_contract import AgentContext, MeetingType
from app.agent_runtime import AgentRuntime, ExecutionPlan, create_default_execution_plan
from app.agent_runtime.registry import ToolRegistry, create_default_tool_registry
from app.config import get_settings
from app.database import SessionLocal
from app.meeting_scenarios.base import ContextType, MeetingScenarioPolicy
from app.meeting_scenarios.registry import get_policy
from app.models import Meeting
from app.observability import log_event, safe_error


AGENT_SHADOW_TRACE_ROOT = Path(__file__).resolve().parents[1] / "data" / "debug" / "agent_shadow_trace"
SIX_DIMENSION_FIELDS = (
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
)


class AgentShadowResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_run_id: str
    meeting_id: str
    meeting_type: MeetingType = "unknown"
    status: str
    started_at: str
    finished_at: str | None = None
    duration_ms: float = 0.0
    steps: list[dict[str, Any]] = Field(default_factory=list)
    result_source: str = "unknown"
    shadow_analysis: dict[str, Any] = Field(default_factory=dict)
    validation_audit: list[dict[str, Any]] = Field(default_factory=list)
    comparison_summary: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    fallback_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentShadowAuditStore:
    def __init__(self, *, trace_root: Path | None = None) -> None:
        self.trace_root = trace_root or AGENT_SHADOW_TRACE_ROOT

    def save(self, result: AgentShadowResult) -> Path:
        trace_dir = self.trace_root / result.meeting_id
        trace_dir.mkdir(parents=True, exist_ok=True)
        output_path = trace_dir / f"{result.agent_run_id}.json"
        result.metadata["audit_path"] = str(output_path)
        output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        (trace_dir / "latest.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return output_path


class AgentOrchestrator:
    def __init__(
        self,
        *,
        runtime: AgentRuntime | None = None,
        registry: ToolRegistry | None = None,
        audit_store: AgentShadowAuditStore | None = None,
        policy_provider: Any = get_policy,
    ) -> None:
        self.registry = registry
        self.runtime = runtime
        self.audit_store = audit_store or AgentShadowAuditStore()
        self.policy_provider = policy_provider

    def run_shadow(
        self,
        *,
        context: AgentContext,
        formal_analysis: dict[str, Any],
        db_provider: Any | None = None,
    ) -> AgentShadowResult:
        started_at = time.perf_counter()
        started_at_iso = _utc_now()
        policy = self._policy_for(context.meeting_type)
        plan = self.create_plan(policy=policy)
        run_id = context.run_id or f"agent-shadow-{uuid4()}"
        runtime_context = context.model_copy(update={"run_id": run_id})

        result = AgentShadowResult(
            agent_run_id=run_id,
            meeting_id=context.meeting_id,
            meeting_type=policy.meeting_type,
            status="running",
            started_at=started_at_iso,
            metadata={
                "policy_schema_version": policy.schema_version,
                "policy_needs_review": policy.needs_review,
                "plan_id": plan.plan_id,
                "agent_mode_enabled": bool(context.runtime_metadata.get("agent_mode_enabled", False)),
                "agent_actions_enabled": bool(context.runtime_metadata.get("agent_actions_enabled", False)),
            },
        )

        try:
            runtime = self._runtime(db_provider=db_provider)
            run_state = runtime.run(context=runtime_context, plan=plan)
            shadow_analysis = _extract_shadow_analysis(run_state.tool_results)
            validation_audit = _extract_validation_audit(run_state.tool_results)
            result_source = _extract_result_source(run_state.tool_results)
            fallback_reason = _extract_fallback_reason(run_state.tool_results)
            result.status = run_state.status
            result.finished_at = run_state.completed_at
            result.duration_ms = run_state.duration_ms
            result.steps = [step.model_dump() for step in run_state.steps]
            result.result_source = result_source
            result.shadow_analysis = shadow_analysis
            result.validation_audit = validation_audit
            result.comparison_summary = compare_meeting_analysis(
                formal_analysis=formal_analysis,
                shadow_analysis=shadow_analysis,
                validation_audit=validation_audit,
                formal_result_source=_extract_formal_result_source(formal_analysis),
                shadow_result_source=result_source,
            )
            result.fallback_reason = fallback_reason
        except Exception as exc:
            result.status = "failed"
            result.finished_at = _utc_now()
            result.duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            result.error = {
                "error_type": exc.__class__.__name__,
                "message": safe_error(exc),
            }
            result.comparison_summary = compare_meeting_analysis(
                formal_analysis=formal_analysis,
                shadow_analysis={},
                validation_audit=[],
                formal_result_source=_extract_formal_result_source(formal_analysis),
                shadow_result_source="unknown",
            )

        audit_path = self.audit_store.save(result)
        log_event(
            "agent.shadow.completed" if result.status != "failed" else "agent.shadow.failed",
            meeting_id=context.meeting_id,
            agent_run_id=result.agent_run_id,
            agent_status=result.status,
            audit_path=str(audit_path),
            result_source=result.result_source,
        )
        return result

    def create_plan(self, *, policy: MeetingScenarioPolicy) -> ExecutionPlan:
        if policy.meeting_type == "unknown":
            return create_default_execution_plan(
                include_meeting_history=False,
                include_project_knowledge=False,
                include_open_action_items=False,
                metadata={"meeting_type": "unknown", "needs_review": True},
            )
        contexts = set(policy.required_context) | set(policy.optional_context)
        return create_default_execution_plan(
            include_meeting_history=_has_any_context(contexts, {"previous_meetings", "previous_same_type_meeting"}),
            include_project_knowledge="project_knowledge" in contexts,
            include_open_action_items="open_action_items" in contexts,
            metadata={"meeting_type": policy.meeting_type, "needs_review": policy.needs_review},
        )

    def _runtime(self, *, db_provider: Any | None) -> AgentRuntime:
        if self.runtime is not None:
            return self.runtime
        registry = self.registry or create_default_tool_registry(db_provider=db_provider or SessionLocal)
        return AgentRuntime(registry=registry)

    def _policy_for(self, meeting_type: MeetingType) -> MeetingScenarioPolicy:
        try:
            return self.policy_provider(meeting_type)
        except Exception:
            return self.policy_provider("unknown")


def maybe_run_agent_shadow(
    *,
    db: Session,
    meeting: Meeting,
    formal_analysis: dict[str, Any],
    transcript: list[dict[str, Any]],
    orchestrator: AgentOrchestrator | None = None,
) -> AgentShadowResult | None:
    settings = get_settings()
    if not settings.agent_shadow_mode:
        log_event("agent.shadow.skipped", meeting_id=meeting.id, reason="agent_shadow_mode_disabled")
        return None
    if settings.agent_actions_enabled:
        log_event("agent.shadow.actions_disabled", meeting_id=meeting.id)

    meeting_type = _meeting_type_from_analysis(formal_analysis)
    context = AgentContext(
        run_id=f"agent-shadow-{uuid4()}",
        meeting_id=meeting.id,
        meeting_type=meeting_type,
        objective=meeting.title or "",
        transcript=transcript,
        meeting_analysis=dict(formal_analysis),
        runtime_metadata={
            "agent_mode_enabled": settings.agent_mode_enabled,
            "agent_shadow_mode": settings.agent_shadow_mode,
            "agent_actions_enabled": settings.agent_actions_enabled,
        },
    )

    try:
        runner = orchestrator or AgentOrchestrator()
        result = runner.run_shadow(context=context, formal_analysis=formal_analysis)
        if settings.agent_mode_enabled:
            log_event(
                "agent.shadow.agent_mode_ignored",
                meeting_id=meeting.id,
                reason="phase_4b_never_overwrites_formal_result",
            )
        return result
    except Exception as exc:
        log_event(
            "agent.shadow.failed",
            level="error",
            meeting_id=meeting.id,
            error_type=exc.__class__.__name__,
            error_message=safe_error(exc),
        )
        return None


def compare_meeting_analysis(
    *,
    formal_analysis: dict[str, Any],
    shadow_analysis: dict[str, Any],
    validation_audit: list[dict[str, Any]],
    formal_result_source: str,
    shadow_result_source: str,
) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    for field in SIX_DIMENSION_FIELDS:
        formal_value = formal_analysis.get(field)
        shadow_value = shadow_analysis.get(field)
        fields[field] = {
            "formal_present": _field_present(formal_value),
            "shadow_present": _field_present(shadow_value),
            "formal_count": _field_count(formal_value),
            "shadow_count": _field_count(shadow_value),
            "count_delta": _field_count(shadow_value) - _field_count(formal_value),
        }
    schema_ok = bool(shadow_analysis) and all(field in shadow_analysis for field in SIX_DIMENSION_FIELDS)
    return {
        "fields": fields,
        "schema_ok": schema_ok,
        "validator_warning_count": sum(
            1 for item in validation_audit if str(item.get("action") or "") in {"remove", "modify"}
        ),
        "result_source": {
            "formal": formal_result_source,
            "shadow": shadow_result_source,
            "same": formal_result_source == shadow_result_source,
        },
    }


def _has_any_context(contexts: set[ContextType], targets: set[ContextType]) -> bool:
    return bool(contexts & targets)


def _meeting_type_from_analysis(formal_analysis: dict[str, Any]) -> MeetingType:
    metadata = formal_analysis.get("metadata") if isinstance(formal_analysis.get("metadata"), dict) else {}
    value = metadata.get("meeting_type") or formal_analysis.get("meeting_type") or "unknown"
    return value if value in _meeting_type_values() else "unknown"  # type: ignore[return-value]


def _meeting_type_values() -> set[str]:
    return {
        "requirement_review",
        "project_weekly",
        "technical_review",
        "version_planning",
        "cross_department",
        "project_retrospective",
        "management_decision",
        "customer_requirement",
        "unknown",
    }


def _extract_shadow_analysis(tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    validation = _latest_tool_data(tool_results, "validate_meeting_analysis")
    validated = validation.get("validated_analysis")
    if isinstance(validated, dict):
        return validated
    analysis = _latest_tool_data(tool_results, "analyze_meeting").get("analysis")
    return analysis if isinstance(analysis, dict) else {}


def _extract_validation_audit(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit = _latest_tool_data(tool_results, "validate_meeting_analysis").get("validator_audit")
    return audit if isinstance(audit, list) else []


def _extract_result_source(tool_results: list[dict[str, Any]]) -> str:
    for result in reversed(tool_results):
        source = str(result.get("result_source") or "")
        if source and source != "unknown":
            return source
    return "unknown"


def _extract_fallback_reason(tool_results: list[dict[str, Any]]) -> str | None:
    for result in reversed(tool_results):
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        reason = metadata.get("fallback_reason")
        if reason:
            return str(reason)
    return None


def _extract_formal_result_source(formal_analysis: dict[str, Any]) -> str:
    metadata = formal_analysis.get("metadata") if isinstance(formal_analysis.get("metadata"), dict) else {}
    return str(metadata.get("result_source") or formal_analysis.get("result_source") or "unknown")


def _latest_tool_data(tool_results: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for result in reversed(tool_results):
        if result.get("tool_name") == tool_name and isinstance(result.get("data"), dict):
            return result["data"]
    return {}


def _field_present(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _field_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return 1 if value else 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "AGENT_SHADOW_TRACE_ROOT",
    "AgentOrchestrator",
    "AgentShadowAuditStore",
    "AgentShadowResult",
    "compare_meeting_analysis",
    "maybe_run_agent_shadow",
]
