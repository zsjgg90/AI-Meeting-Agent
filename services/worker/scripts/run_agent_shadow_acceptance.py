from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


from app.agent_contract import AgentContext, MeetingType  # noqa: E402
from app.agent_orchestrator import (  # noqa: E402
    AgentOrchestrator,
    AgentShadowAuditStore,
)
from app.agent_runtime import AgentRunState, AgentStepResult  # noqa: E402
from app.agent_tools.base import ToolError, ToolExecutionContext, ToolResult  # noqa: E402
from app.meeting_scenarios.registry import get_policy  # noqa: E402


DEFAULT_FIXTURE_PATH = PROJECT_ROOT / "data" / "eval" / "agent_v1_baseline" / "phase5_core_scenarios" / "fixtures.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "agent_shadow_acceptance"

CORE_SCENARIOS: tuple[MeetingType, ...] = (
    "project_weekly",
    "requirement_review",
    "cross_department",
)

EXPECTED_ENABLED_TOOLS: dict[MeetingType, tuple[str, ...]] = {
    "project_weekly": (
        "get_meeting_context",
        "search_meeting_history",
        "get_open_action_items",
        "analyze_meeting",
        "validate_meeting_analysis",
    ),
    "requirement_review": (
        "get_meeting_context",
        "search_meeting_history",
        "search_project_knowledge",
        "analyze_meeting",
        "validate_meeting_analysis",
    ),
    "cross_department": (
        "get_meeting_context",
        "search_meeting_history",
        "get_open_action_items",
        "analyze_meeting",
        "validate_meeting_analysis",
    ),
}

SIX_DIMENSION_FIELDS = (
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
)


class AcceptanceRuntime:
    def __init__(
        self,
        *,
        meeting_fixture: dict[str, Any],
        allow_live_model: bool = False,
        failure_injection: dict[str, Any] | None = None,
    ) -> None:
        self.meeting_fixture = meeting_fixture
        self.allow_live_model = allow_live_model
        self.failure_injection = failure_injection or {}
        self._latest_analysis: dict[str, Any] = {}
        self.real_model_call_count = 0

    def run(self, *, context: AgentContext, plan: Any) -> AgentRunState:
        started_at = time.perf_counter()
        started_at_iso = _utc_now()
        tool_context = ToolExecutionContext(
            run_id=context.run_id,
            meeting_id=context.meeting_id,
            project_id=context.project_id,
            meeting_type=context.meeting_type,
            deadline_at=plan.deadline_at,
        )
        steps: list[AgentStepResult] = []
        tool_results: list[dict[str, Any]] = []
        stopped = False

        for index, step in enumerate(plan.steps):
            step_started = _utc_now()
            if not step.enabled:
                steps.append(
                    AgentStepResult(
                        step_index=index,
                        tool_name=step.tool_name,
                        status="skipped",
                        optional=step.optional,
                        started_at=step_started,
                        completed_at=step_started,
                        metadata={"skip_reason": "disabled_by_execution_plan"},
                    )
                )
                continue

            result = self._execute_tool(context=context, tool_context=tool_context, tool_name=step.tool_name)
            steps.append(
                AgentStepResult(
                    step_index=index,
                    tool_name=step.tool_name,
                    status=result.status,
                    optional=step.optional,
                    duration_ms=result.duration_ms,
                    result=result,
                    error=result.error,
                    result_source=result.result_source,
                    started_at=step_started,
                    completed_at=_utc_now(),
                    metadata={"continue_on_failure": step.continue_on_failure},
                )
            )
            tool_results.append(result.model_dump())
            if result.status in {"failed", "timeout"} and not step.continue_on_failure:
                stopped = True
                break

        return AgentRunState(
            run_id=context.run_id,
            meeting_id=context.meeting_id,
            project_id=context.project_id,
            plan_id=plan.plan_id,
            status=_resolve_run_status(steps, stopped=stopped),
            started_at=started_at_iso,
            completed_at=_utc_now(),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            steps=steps,
            tool_results=tool_results,
            runtime_metadata={
                "acceptance_mode": "live_model" if self.allow_live_model else "offline_fixture",
                "real_model_call_count": self.real_model_call_count,
                "call_counts": dict(tool_context.call_counts),
            },
        )

    def _execute_tool(
        self,
        *,
        context: AgentContext,
        tool_context: ToolExecutionContext,
        tool_name: str,
    ) -> ToolResult:
        started_at = time.perf_counter()
        injected_status = self._injected_status(tool_name)
        if injected_status in {"failed", "timeout"}:
            return _tool_result(
                tool_name=tool_name,
                status=injected_status,
                started_at=started_at,
                result_source="fixture_injected",
                error=ToolError(
                    error_type="InjectedToolError",
                    error_code=f"injected_{injected_status}",
                    message=f"Injected {injected_status} for {tool_name}.",
                    retryable=False,
                ),
            )

        if tool_name == "get_meeting_context":
            return _tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture",
                data={
                    "meeting": {
                        "id": self.meeting_fixture["meeting_id"],
                        "title": self.meeting_fixture["title"],
                        "meeting_type": self.meeting_fixture["meeting_type"],
                        "metadata": self.meeting_fixture.get("metadata", {}),
                    },
                    "transcript_segments": self.meeting_fixture.get("transcript", []),
                },
            )
        if tool_name == "search_meeting_history":
            return _tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture_empty",
                data={"items": [], "total": 0, "degraded": True, "degrade_reason": "no_fixture_history"},
            )
        if tool_name == "search_project_knowledge":
            return _tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture_empty",
                data={"items": [], "total": 0, "degraded": True, "degrade_reason": "no_fixture_rag_results"},
            )
        if tool_name == "get_open_action_items":
            return _tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture_empty",
                data={"items": [], "total": 0, "degraded": True, "degrade_reason": "no_fixture_open_items"},
            )
        if tool_name == "analyze_meeting":
            return self._analyze_meeting(context=context, tool_context=tool_context, started_at=started_at)
        if tool_name == "validate_meeting_analysis":
            return self._validate_meeting(context=context, tool_context=tool_context, started_at=started_at)

        return _tool_result(
            tool_name=tool_name,
            status="failed",
            started_at=started_at,
            error=ToolError(
                error_type="UnknownAcceptanceTool",
                error_code="unknown_acceptance_tool",
                message=f"Unsupported acceptance tool {tool_name}.",
                retryable=False,
            ),
        )

    def _analyze_meeting(
        self,
        *,
        context: AgentContext,
        tool_context: ToolExecutionContext,
        started_at: float,
    ) -> ToolResult:
        if self.allow_live_model:
            from app.agent_tools.analysis import AnalyzeMeetingTool

            self.real_model_call_count += 1
            result = AnalyzeMeetingTool().execute(
                tool_context,
                {
                    "meeting_id": context.meeting_id,
                    "transcript": self.meeting_fixture.get("transcript", []),
                },
            )
            if isinstance(result.data.get("analysis"), dict):
                self._latest_analysis = result.data["analysis"]
            return result

        analysis = deepcopy(self.meeting_fixture["formal_analysis"])
        metadata = dict(analysis.get("metadata") or {})
        metadata.update(
            {
                "result_source": "fixture_shadow",
                "meeting_type": self.meeting_fixture["meeting_type"],
                "schema_version": metadata.get("schema_version", "phase5-fixture-v1"),
            }
        )
        if self._injected_status("analyze_meeting") == "fallback":
            metadata["fallback_reason"] = "injected_acceptance_fallback"
        analysis["metadata"] = metadata
        self._latest_analysis = analysis
        return _tool_result(
            tool_name="analyze_meeting",
            status="fallback" if metadata.get("fallback_reason") else "success",
            started_at=started_at,
            result_source=str(metadata["result_source"]),
            data={"meeting_id": context.meeting_id, "analysis": analysis},
            metadata={"fallback_reason": metadata.get("fallback_reason")},
        )

    def _validate_meeting(
        self,
        *,
        context: AgentContext,
        tool_context: ToolExecutionContext,
        started_at: float,
    ) -> ToolResult:
        if self.allow_live_model and self._latest_analysis:
            from app.agent_tools.validation import ValidateMeetingAnalysisTool

            return ValidateMeetingAnalysisTool().execute(
                tool_context,
                {
                    "meeting_id": context.meeting_id,
                    "analysis": self._latest_analysis,
                    "transcript": self.meeting_fixture.get("transcript", []),
                },
            )

        return _tool_result(
            tool_name="validate_meeting_analysis",
            status="success",
            started_at=started_at,
            result_source=str((self._latest_analysis.get("metadata") or {}).get("result_source") or "fixture_shadow"),
            data={
                "meeting_id": context.meeting_id,
                "validated_analysis": deepcopy(self._latest_analysis),
                "validator_audit": [],
                "warnings": [],
            },
        )

    def _injected_status(self, tool_name: str) -> str | None:
        status = self.failure_injection.get(tool_name)
        return str(status) if status else None


def load_fixtures(path: Path = DEFAULT_FIXTURE_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meetings = payload.get("meetings")
    if not isinstance(meetings, list):
        raise ValueError("fixtures.json must contain a meetings list")
    for meeting in meetings:
        if meeting.get("meeting_type") not in CORE_SCENARIOS:
            raise ValueError(f"unsupported fixture meeting_type: {meeting.get('meeting_type')}")
        if not meeting.get("transcript"):
            raise ValueError(f"fixture {meeting.get('meeting_id')} has no transcript")
    return meetings


def run_acceptance(
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    allow_live_model: bool = False,
    timestamp: str | None = None,
    failure_injections: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    fixtures = load_fixtures(fixture_path)
    run_id = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "meetings").mkdir(parents=True, exist_ok=True)

    meeting_summaries: list[dict[str, Any]] = []
    for meeting in fixtures:
        summary = run_meeting_acceptance(
            meeting=meeting,
            output_dir=output_dir,
            allow_live_model=allow_live_model,
            failure_injection=(failure_injections or {}).get(str(meeting["meeting_id"]), {}),
        )
        meeting_summaries.append(summary)
        _write_json(output_dir / "meetings" / f"{meeting['meeting_id']}.json", summary)

    report = build_acceptance_report(
        output_dir=output_dir,
        fixtures=fixtures,
        meeting_summaries=meeting_summaries,
        allow_live_model=allow_live_model,
    )
    _write_json(output_dir / "acceptance_report.json", report)
    (output_dir / "acceptance_report.md").write_text(render_markdown_report(report), encoding="utf-8")
    return report


def run_meeting_acceptance(
    *,
    meeting: dict[str, Any],
    output_dir: Path,
    allow_live_model: bool,
    failure_injection: dict[str, str],
) -> dict[str, Any]:
    meeting_type = meeting["meeting_type"]
    policy = get_policy(meeting_type)
    runtime = AcceptanceRuntime(
        meeting_fixture=meeting,
        allow_live_model=allow_live_model,
        failure_injection=failure_injection,
    )
    orchestrator = AgentOrchestrator(
        runtime=runtime,
        audit_store=AgentShadowAuditStore(trace_root=output_dir / "shadow_trace"),
    )
    plan = orchestrator.create_plan(policy=policy)
    formal_before = deepcopy(meeting["formal_analysis"])
    shadow = orchestrator.run_shadow(
        context=AgentContext(
            run_id=f"phase5-{meeting['meeting_id']}",
            meeting_id=meeting["meeting_id"],
            project_id=meeting.get("project_id", ""),
            meeting_type=meeting_type,
            objective=meeting.get("title", ""),
            transcript=meeting.get("transcript", []),
            meeting_analysis=deepcopy(meeting["formal_analysis"]),
            runtime_metadata={
                "agent_mode_enabled": False,
                "agent_shadow_mode": True,
                "agent_actions_enabled": False,
                "acceptance_phase": "agent-v1-phase5",
            },
        ),
        formal_analysis=meeting["formal_analysis"],
    )

    actual_plan = [step.tool_name for step in plan.steps if step.enabled]
    expected_plan = list(EXPECTED_ENABLED_TOOLS[meeting_type])
    tool_statuses = {step["tool_name"]: step["status"] for step in shadow.steps}
    tool_sources = {step["tool_name"]: step.get("result_source", "unknown") for step in shadow.steps}
    tool_durations = {step["tool_name"]: step.get("duration_ms", 0.0) for step in shadow.steps}
    warnings = shadow.comparison_summary.get("validator_warning_count", 0)
    formal_after_unchanged = formal_before == meeting["formal_analysis"]

    return {
        "meeting_id": meeting["meeting_id"],
        "meeting_type": meeting_type,
        "title": meeting["title"],
        "manual_meeting_type": meeting.get("metadata", {}).get("manual_meeting_type"),
        "expected_plan": expected_plan,
        "actual_plan": actual_plan,
        "plan_matches_expected": actual_plan == expected_plan,
        "tool_statuses": tool_statuses,
        "tool_result_sources": tool_sources,
        "tool_duration_ms": tool_durations,
        "real_model_call_count": runtime.real_model_call_count,
        "shadow_status": shadow.status,
        "shadow_duration_ms": shadow.duration_ms,
        "result_source": shadow.result_source,
        "fallback_reason": shadow.fallback_reason,
        "comparison_summary": shadow.comparison_summary,
        "schema_ok": bool(shadow.comparison_summary.get("schema_ok")),
        "validator_warning_count": warnings,
        "needs_human_review": _needs_human_review(shadow.status, actual_plan, expected_plan, shadow.comparison_summary),
        "formal_result_unchanged": formal_after_unchanged,
        "shadow_audit_path": shadow.metadata.get("audit_path"),
        "error": shadow.error,
    }


def build_acceptance_report(
    *,
    output_dir: Path,
    fixtures: list[dict[str, Any]],
    meeting_summaries: list[dict[str, Any]],
    allow_live_model: bool,
) -> dict[str, Any]:
    scenario_summary: dict[str, dict[str, Any]] = {}
    for scenario in CORE_SCENARIOS:
        items = [item for item in meeting_summaries if item["meeting_type"] == scenario]
        scenario_summary[scenario] = _aggregate_items(items)

    total_steps = sum(len(item["tool_statuses"]) for item in meeting_summaries)
    failed_steps = sum(
        1
        for item in meeting_summaries
        for status in item["tool_statuses"].values()
        if status in {"failed", "timeout"}
    )
    fallback_steps = sum(
        1
        for item in meeting_summaries
        for status in item["tool_statuses"].values()
        if status == "fallback"
    )
    durations = [float(item["shadow_duration_ms"]) for item in meeting_summaries]
    failures = [item for item in meeting_summaries if item["shadow_status"] in {"failed", "timeout"}]

    return {
        "schema_version": "agent-v1-phase5-acceptance-report-v1",
        "generated_at": _utc_now(),
        "output_dir": str(output_dir),
        "fixture_path": str(DEFAULT_FIXTURE_PATH),
        "allow_live_model": allow_live_model,
        "fixture_source": "user_provided_synthetic_9_meeting_scripts",
        "meetings_total": len(meeting_summaries),
        "scenario_counts": dict(Counter(item["meeting_type"] for item in fixtures)),
        "scenario_plan_hit_rate": _rate(sum(1 for item in meeting_summaries if item["plan_matches_expected"]), len(meeting_summaries)),
        "shadow_success_rate": _rate(sum(1 for item in meeting_summaries if item["shadow_status"] in {"success", "partial"}), len(meeting_summaries)),
        "tool_failure_rate": _rate(failed_steps, total_steps),
        "fallback_rate": _rate(fallback_steps, total_steps),
        "performance": {
            "average_shadow_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "max_shadow_duration_ms": max(durations) if durations else 0.0,
            "real_model_call_count": sum(int(item["real_model_call_count"]) for item in meeting_summaries),
        },
        "six_dimension_field_completeness": _field_completeness(meeting_summaries),
        "boundary_issue_count": sum(1 for item in meeting_summaries if item["needs_human_review"]),
        "scenario_summary": scenario_summary,
        "failure_index": [
            {
                "meeting_id": item["meeting_id"],
                "meeting_type": item["meeting_type"],
                "status": item["shadow_status"],
                "error": item["error"],
                "fallback_reason": item["fallback_reason"],
            }
            for item in failures
        ],
        "meetings": meeting_summaries,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Agent v1 Phase 5 Shadow Acceptance Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Fixture source: {report['fixture_source']}",
        f"- Meetings: {report['meetings_total']}",
        f"- Live model enabled: {report['allow_live_model']}",
        f"- Scenario plan hit rate: {report['scenario_plan_hit_rate']}",
        f"- Shadow success rate: {report['shadow_success_rate']}",
        f"- Tool failure rate: {report['tool_failure_rate']}",
        f"- Fallback rate: {report['fallback_rate']}",
        f"- Average shadow duration ms: {report['performance']['average_shadow_duration_ms']}",
        f"- Max shadow duration ms: {report['performance']['max_shadow_duration_ms']}",
        f"- Real model call count: {report['performance']['real_model_call_count']}",
        "",
        "## Scenario Summary",
    ]
    for scenario, summary in report["scenario_summary"].items():
        lines.extend(
            [
                "",
                f"### {scenario}",
                f"- Meetings: {summary['meeting_count']}",
                f"- Plan hit rate: {summary['plan_hit_rate']}",
                f"- Shadow success rate: {summary['shadow_success_rate']}",
                f"- Main differences: {summary['main_differences']}",
            ]
        )
    lines.extend(["", "## Failure Index"])
    if report["failure_index"]:
        for item in report["failure_index"]:
            lines.append(f"- {item['meeting_id']} ({item['meeting_type']}): {item['status']}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _aggregate_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "meeting_count": len(items),
        "plan_hit_rate": _rate(sum(1 for item in items if item["plan_matches_expected"]), len(items)),
        "shadow_success_rate": _rate(sum(1 for item in items if item["shadow_status"] in {"success", "partial"}), len(items)),
        "average_shadow_duration_ms": round(
            sum(float(item["shadow_duration_ms"]) for item in items) / len(items),
            2,
        )
        if items
        else 0.0,
        "main_differences": _main_differences(items),
    }


def _main_differences(items: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, int] = defaultdict(int)
    for item in items:
        fields = item["comparison_summary"].get("fields", {})
        for field in SIX_DIMENSION_FIELDS:
            totals[field] += int(fields.get(field, {}).get("count_delta", 0))
    return dict(totals)


def _field_completeness(items: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for field in SIX_DIMENSION_FIELDS:
        present = 0
        for item in items:
            fields = item["comparison_summary"].get("fields", {})
            if fields.get(field, {}).get("shadow_present"):
                present += 1
        result[field] = _rate(present, len(items))
    return result


def _needs_human_review(
    status: str,
    actual_plan: list[str],
    expected_plan: list[str],
    comparison_summary: dict[str, Any],
) -> bool:
    return (
        status not in {"success", "partial"}
        or actual_plan != expected_plan
        or not comparison_summary.get("schema_ok", False)
        or int(comparison_summary.get("validator_warning_count", 0)) > 0
    )


def _resolve_run_status(steps: list[AgentStepResult], *, stopped: bool) -> str:
    statuses = {step.status for step in steps}
    if "timeout" in statuses and stopped:
        return "timeout"
    if "failed" in statuses and stopped:
        return "failed"
    if "failed" in statuses or "timeout" in statuses or "skipped" in statuses:
        return "partial"
    return "success"


def _tool_result(
    *,
    tool_name: str,
    status: str,
    started_at: float,
    data: dict[str, Any] | None = None,
    error: ToolError | None = None,
    result_source: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        status=status,
        data=data or {},
        error=error,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        result_source=result_source,
        retryable=bool(error.retryable) if error else False,
        metadata={key: value for key, value in (metadata or {}).items() if value is not None},
    )


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Agent v1 Phase 5 shadow acceptance.")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument(
        "--allow-live-model",
        action="store_true",
        help="Explicitly allow existing analyze_meeting Tool to call the real model.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_acceptance(
        fixture_path=args.fixtures,
        output_root=args.output_root,
        allow_live_model=args.allow_live_model,
        timestamp=args.timestamp,
    )
    print(json.dumps({"output_dir": report["output_dir"], "meetings_total": report["meetings_total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
