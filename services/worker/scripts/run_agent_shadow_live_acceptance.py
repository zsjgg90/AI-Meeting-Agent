from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
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
from app.agent_orchestrator import AgentOrchestrator, AgentShadowAuditStore  # noqa: E402
from app.agent_runtime import AgentRunState, AgentStepResult  # noqa: E402
from app.agent_tools.base import ToolError, ToolExecutionContext, ToolResult  # noqa: E402
from app.analysis_contract import normalize_meeting_analysis_result  # noqa: E402
from app.anti_hallucination_validator import validate_meeting_analysis_with_audit  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor  # noqa: E402
from app.meeting_analyst_prompt import RAG_QUERY, build_meeting_analyst_prompt  # noqa: E402
from app.meeting_analyst_service import extract_json  # noqa: E402
from app.ollama_client import OllamaClient  # noqa: E402
from app.prompt_registry import get_meeting_analyst_prompt_spec  # noqa: E402
from app.rag_retriever import RagContext, RagRetriever  # noqa: E402
from app.transcript_builder import build_transcript_text  # noqa: E402
from scripts.run_agent_shadow_acceptance import (  # noqa: E402
    CORE_SCENARIOS,
    DEFAULT_FIXTURE_PATH,
    EXPECTED_ENABLED_TOOLS,
    load_fixtures,
)


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "agent_shadow_live_acceptance"
SMOKE_MEETING_IDS = (
    "phase5-project_weekly-1",
    "phase5-requirement_review-1",
    "phase5-cross_department-1",
)
REQUIRED_MEETING_ARTIFACTS = (
    "input_transcript.txt",
    "rag_context.json",
    "prompt.txt",
    "model_raw_output.json",
    "parsed_result.json",
    "normalized_before_postprocess.json",
    "postprocessed_result.json",
    "validated_result.json",
    "validator_audit.json",
    "shadow_audit.json",
    "quality_score.json",
    "quality_score.md",
    "gpu_samples.csv",
    "gpu_summary.json",
    "pipeline.log",
)
EVIDENCE_FIELDS = ("key_conclusions", "action_items", "unresolved_issues", "risks_and_focus")


def select_meetings(
    fixtures: list[dict[str, Any]],
    *,
    mode: str,
    meeting_id: str | None = None,
    scenario: str | None = None,
) -> list[dict[str, Any]]:
    if meeting_id:
        selected = [meeting for meeting in fixtures if meeting["meeting_id"] == meeting_id]
        if not selected:
            raise ValueError(f"Unknown meeting id: {meeting_id}")
        if scenario and selected[0]["meeting_type"] != scenario:
            raise ValueError(f"Meeting {meeting_id} does not belong to scenario {scenario}")
        return selected
    if scenario:
        if scenario not in CORE_SCENARIOS:
            raise ValueError(f"Unsupported scenario: {scenario}")
        return [meeting for meeting in fixtures if meeting["meeting_type"] == scenario]
    if mode == "smoke":
        by_id = {meeting["meeting_id"]: meeting for meeting in fixtures}
        return [by_id[meeting_id] for meeting_id in SMOKE_MEETING_IDS]
    if mode == "full":
        return list(fixtures)
    raise ValueError(f"Unsupported mode: {mode}")


class GpuMonitor:
    query_fields = "timestamp,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw"

    def __init__(self, *, output_path: Path, interval_seconds: float = 1.0, enabled: bool = False) -> None:
        self.output_path = output_path
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.process: subprocess.Popen[str] | None = None
        self.warning: str | None = None
        self._stream: Any | None = None

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.enabled:
            self.output_path.write_text("", encoding="utf-8")
            return
        command = [
            "nvidia-smi",
            f"--query-gpu={self.query_fields}",
            "--format=csv",
            "-l",
            str(max(int(self.interval_seconds), 1)),
        ]
        try:
            self._stream = self.output_path.open("w", encoding="utf-8", newline="")
            self.process = subprocess.Popen(command, stdout=self._stream, stderr=subprocess.PIPE, text=True)
        except Exception as exc:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self.warning = f"{exc.__class__.__name__}: {exc}"
            self.output_path.write_text("", encoding="utf-8")

    def stop(self) -> dict[str, Any]:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.process.stderr is not None:
                stderr = self.process.stderr.read().strip()
                if stderr and not self.warning:
                    self.warning = stderr
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        return summarize_gpu_samples(self.output_path, warning=self.warning)


def summarize_gpu_samples(path: Path, *, warning: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "available": False,
        "sample_count": 0,
        "peak_memory_used_mb": None,
        "memory_total_mb": None,
        "avg_gpu_utilization_pct": None,
        "peak_temperature_c": None,
        "peak_power_draw_w": None,
        "oom_detected": False,
        "sustained_memory_growth_detected": False,
        "warning": warning,
    }
    if not path.exists() or path.stat().st_size == 0:
        return summary

    rows = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, skipinitialspace=True)
        for row in reader:
            rows.append({(key or "").strip(): value for key, value in row.items()})
    if not rows:
        return summary

    memory_used = [_number(row.get("memory.used [MiB]")) for row in rows]
    memory_total = [_number(row.get("memory.total [MiB]")) for row in rows]
    gpu_util = [_number(row.get("utilization.gpu [%]")) for row in rows]
    temp = [_number(row.get("temperature.gpu")) for row in rows]
    power = [_number(row.get("power.draw [W]")) for row in rows]
    memory_used_values = [value for value in memory_used if value is not None]
    summary.update(
        {
            "available": True,
            "sample_count": len(rows),
            "peak_memory_used_mb": _max_or_none(memory_used),
            "memory_total_mb": _max_or_none(memory_total),
            "avg_gpu_utilization_pct": _avg_or_none(gpu_util),
            "peak_temperature_c": _max_or_none(temp),
            "peak_power_draw_w": _max_or_none(power),
            "oom_detected": any(
                used is not None and total is not None and total > 0 and used >= total * 0.98
                for used, total in zip(memory_used, memory_total, strict=False)
            ),
            "sustained_memory_growth_detected": _sustained_growth(memory_used_values),
            "warning": warning,
        }
    )
    return summary


class LayerCaptureResult:
    def __init__(
        self,
        *,
        ok: bool,
        artifacts: dict[str, Any],
        metadata: dict[str, Any],
        failure_reason: str | None = None,
    ) -> None:
        self.ok = ok
        self.artifacts = artifacts
        self.metadata = metadata
        self.failure_reason = failure_reason


class LiveAnalysisRuntime:
    def __init__(
        self,
        *,
        meeting_fixture: dict[str, Any],
        meeting_dir: Path,
        allow_live_model: bool,
        ollama_timeout: float,
    ) -> None:
        self.meeting_fixture = meeting_fixture
        self.meeting_dir = meeting_dir
        self.allow_live_model = allow_live_model
        self.ollama_timeout = ollama_timeout
        self.real_model_call_count = 0
        self.latest_analysis: dict[str, Any] = {}
        self.latest_validator_audit: list[dict[str, Any]] = []
        self.layer_result: LayerCaptureResult | None = None

    def run(self, *, context: AgentContext, plan: Any) -> AgentRunState:
        started_at = time.perf_counter()
        started_at_iso = utc_now()
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
            step_started = utc_now()
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
            result = self._execute_tool(context=context, tool_name=step.tool_name)
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
                    completed_at=utc_now(),
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
            status=resolve_run_status(steps, stopped=stopped),
            started_at=started_at_iso,
            completed_at=utc_now(),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            steps=steps,
            tool_results=tool_results,
            runtime_metadata={
                "acceptance_phase": "agent-v1-phase5b",
                "real_model_call_count": self.real_model_call_count,
                "call_counts": dict(tool_context.call_counts),
            },
        )

    def _execute_tool(self, *, context: AgentContext, tool_name: str) -> ToolResult:
        started_at = time.perf_counter()
        if tool_name == "get_meeting_context":
            return tool_result(
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
            return tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture_empty",
                data={"items": [], "total": 0, "degraded": True, "degrade_reason": "no_fixture_history"},
            )
        if tool_name == "search_project_knowledge":
            source = "live_rag" if self.allow_live_model else "unavailable"
            return tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source=source,
                data={
                    "items": [],
                    "total": 0,
                    "degraded": not self.allow_live_model,
                    "degrade_reason": None if self.allow_live_model else "live_model_not_allowed",
                },
            )
        if tool_name == "get_open_action_items":
            return tool_result(
                tool_name=tool_name,
                status="success",
                started_at=started_at,
                result_source="fixture_empty",
                data={"items": [], "total": 0, "degraded": True, "degrade_reason": "no_fixture_open_items"},
            )
        if tool_name == "analyze_meeting":
            return self._analyze_meeting(started_at=started_at)
        if tool_name == "validate_meeting_analysis":
            return self._validate_meeting(started_at=started_at)
        return tool_result(
            tool_name=tool_name,
            status="failed",
            started_at=started_at,
            error=ToolError(
                error_type="UnknownLiveAcceptanceTool",
                error_code="unknown_live_acceptance_tool",
                message=f"Unsupported live acceptance tool {tool_name}.",
                retryable=False,
            ),
        )

    def _analyze_meeting(self, *, started_at: float) -> ToolResult:
        if not self.allow_live_model:
            self.layer_result = write_unavailable_layers(
                meeting_dir=self.meeting_dir,
                reason="--allow-live-model was not provided",
            )
            self.latest_analysis = deepcopy(self.meeting_fixture["formal_analysis"])
            return tool_result(
                tool_name="analyze_meeting",
                status="skipped",
                started_at=started_at,
                result_source="unavailable",
                data={"meeting_id": self.meeting_fixture["meeting_id"], "analysis": self.latest_analysis},
                metadata={"skip_reason": "live_model_not_allowed"},
            )

        self.real_model_call_count += 1
        self.layer_result = run_live_analysis_layers(
            meeting=self.meeting_fixture,
            meeting_dir=self.meeting_dir,
            ollama_timeout=self.ollama_timeout,
        )
        self.latest_analysis = deepcopy(self.layer_result.artifacts.get("validated_result") or {})
        self.latest_validator_audit = list(self.layer_result.artifacts.get("validator_audit") or [])
        if not self.layer_result.ok:
            return tool_result(
                tool_name="analyze_meeting",
                status="failed",
                started_at=started_at,
                result_source="legacy_qwen_rag",
                data={"meeting_id": self.meeting_fixture["meeting_id"]},
                error=ToolError(
                    error_type="LiveAnalysisFailed",
                    error_code=classify_failure(self.layer_result.failure_reason),
                    message=self.layer_result.failure_reason or "Live analysis failed.",
                    retryable=False,
                ),
            )
        metadata = self.latest_analysis.get("_metadata") if isinstance(self.latest_analysis.get("_metadata"), dict) else {}
        return tool_result(
            tool_name="analyze_meeting",
            status="success",
            started_at=started_at,
            result_source=str(metadata.get("result_source") or "legacy_qwen_rag"),
            data={"meeting_id": self.meeting_fixture["meeting_id"], "analysis": self.latest_analysis},
            metadata={
                "model_name": metadata.get("model_name"),
                "prompt_version": metadata.get("prompt_version"),
                "schema_version": metadata.get("schema_version"),
                "rag_chunk_ids": metadata.get("rag_chunk_ids", []),
                "rag_dataset_version": metadata.get("rag_dataset_version"),
                "rag_chunk_schema_version": metadata.get("rag_chunk_schema_version"),
                "rag_collection_name": metadata.get("rag_collection_name"),
                "rag_embedding_model": metadata.get("rag_embedding_model"),
            },
        )

    def _validate_meeting(self, *, started_at: float) -> ToolResult:
        if not self.latest_analysis:
            return tool_result(
                tool_name="validate_meeting_analysis",
                status="failed",
                started_at=started_at,
                error=ToolError(
                    error_type="MissingAnalysis",
                    error_code="analysis_unavailable",
                    message="No analysis result is available for validation.",
                    retryable=False,
                ),
            )
        source = "legacy_qwen_rag" if self.allow_live_model else "unavailable"
        return tool_result(
            tool_name="validate_meeting_analysis",
            status="success" if self.allow_live_model else "skipped",
            started_at=started_at,
            result_source=source,
            data={
                "meeting_id": self.meeting_fixture["meeting_id"],
                "validated_analysis": deepcopy(self.latest_analysis),
                "validator_audit": deepcopy(self.latest_validator_audit),
                "warnings": [
                    item
                    for item in self.latest_validator_audit
                    if str(item.get("action") or "") in {"remove", "modify"}
                ],
            },
        )


def run_live_analysis_layers(
    *,
    meeting: dict[str, Any],
    meeting_dir: Path,
    ollama_timeout: float,
) -> LayerCaptureResult:
    settings = get_settings()
    prompt_spec = get_meeting_analyst_prompt_spec()
    transcript = fixture_transcript_text(meeting)
    metadata: dict[str, Any] = {
        "model_name": settings.ollama_model,
        "ollama_timeout": ollama_timeout,
        "prompt_id": prompt_spec.prompt_id,
        "prompt_version": prompt_spec.prompt_version,
        "schema_version": prompt_spec.schema_version,
        "result_source": "legacy_qwen_rag",
    }
    artifacts: dict[str, Any] = {}
    started_at = time.perf_counter()

    try:
        rag_started_at = time.perf_counter()
        retriever = RagRetriever()
        rag_context = retriever.build_context_payload(query=RAG_QUERY, top_k=settings.rag_top_k)
        rag_payload = serialize_rag_context(rag_context)
        artifacts["rag_context"] = rag_payload
        write_json(meeting_dir / "rag_context.json", rag_payload)
        metadata.update(
            {
                "rag_duration_ms": round((time.perf_counter() - rag_started_at) * 1000, 2),
                "rag_chunk_ids": rag_context.chunk_ids,
                "rag_dataset_version": rag_context.dataset_version,
                "rag_chunk_schema_version": rag_context.chunk_schema_version,
                "rag_collection_name": rag_context.collection_name,
                "rag_embedding_model": rag_context.embedding_model,
            }
        )

        prompt = build_meeting_analyst_prompt(rag_context=rag_context.text, transcript=transcript)
        artifacts["prompt"] = {"available": True, "prompt_chars": len(prompt)}
        (meeting_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        llm = OllamaClient(timeout=ollama_timeout)
        model_started_at = time.perf_counter()
        raw_output = llm.chat(prompt)
        model_raw = {
            "raw_output": raw_output,
            "model_name": llm.model,
            "ollama_timeout": ollama_timeout,
            "ollama_duration_ms": round((time.perf_counter() - model_started_at) * 1000, 2),
            "ollama_temperature": llm.temperature,
            "ollama_top_p": llm.top_p,
            "ollama_seed": llm.seed,
            "ollama_format": llm.response_format,
        }
        artifacts["model_raw_output"] = model_raw
        write_json(meeting_dir / "model_raw_output.json", model_raw)

        parsed = extract_json(raw_output)
        parsed["_metadata"] = {
            "prompt_id": prompt_spec.prompt_id,
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
            "rag_chunk_ids": rag_context.chunk_ids,
            "rag_dataset_version": rag_context.dataset_version,
            "rag_chunk_schema_version": rag_context.chunk_schema_version,
            "rag_collection_name": rag_context.collection_name,
            "rag_embedding_model": rag_context.embedding_model,
            "model_name": f"{settings.ollama_model}+rag",
            "result_source": "legacy_qwen_rag",
        }
        artifacts["parsed_result"] = parsed
        write_json(meeting_dir / "parsed_result.json", parsed)

        normalized_before = normalize_meeting_analysis_result(parsed, model_name=f"{settings.ollama_model}+rag")
        normalized_before_dump = normalized_before.model_dump()
        artifacts["normalized_before_postprocess"] = normalized_before_dump
        write_json(meeting_dir / "normalized_before_postprocess.json", normalized_before_dump)

        postprocessor = MeetingAnalysisPostProcessor()
        postprocessed = postprocessor.process(normalized_before, transcript)
        postprocessed_dump = postprocessed.model_dump()
        artifacts["postprocessed_result"] = postprocessed_dump
        artifacts["postprocessor_audit"] = postprocessor.last_audit
        write_json(meeting_dir / "postprocessed_result.json", postprocessed_dump)

        validated, validator_audit = validate_meeting_analysis_with_audit(deepcopy(postprocessed_dump), transcript)
        validated["_metadata"] = dict(parsed["_metadata"])
        artifacts["validated_result"] = validated
        artifacts["validator_audit"] = validator_audit
        write_json(meeting_dir / "validated_result.json", validated)
        write_json(meeting_dir / "validator_audit.json", validator_audit)

        metadata["total_layer_duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        return LayerCaptureResult(ok=True, artifacts=artifacts, metadata=metadata)
    except Exception as exc:
        reason = f"{exc.__class__.__name__}: {exc}"
        metadata["total_layer_duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        write_missing_layer_artifacts(meeting_dir, reason=reason)
        return LayerCaptureResult(ok=False, artifacts=artifacts, metadata=metadata, failure_reason=reason)


def write_unavailable_layers(*, meeting_dir: Path, reason: str) -> LayerCaptureResult:
    artifacts = {
        "rag_context": unavailable(reason),
        "prompt": unavailable(reason),
        "model_raw_output": unavailable(reason),
        "parsed_result": unavailable(reason),
        "normalized_before_postprocess": unavailable(reason),
        "postprocessed_result": unavailable(reason),
        "validated_result": unavailable(reason),
        "validator_audit": unavailable(reason),
    }
    write_missing_layer_artifacts(meeting_dir, reason=reason)
    return LayerCaptureResult(ok=False, artifacts=artifacts, metadata={"result_source": "unavailable"}, failure_reason=reason)


def write_missing_layer_artifacts(meeting_dir: Path, *, reason: str) -> None:
    for name in (
        "rag_context.json",
        "model_raw_output.json",
        "parsed_result.json",
        "normalized_before_postprocess.json",
        "postprocessed_result.json",
        "validated_result.json",
        "validator_audit.json",
    ):
        path = meeting_dir / name
        if not path.exists():
            write_json(path, unavailable(reason))
    prompt_path = meeting_dir / "prompt.txt"
    if not prompt_path.exists():
        prompt_path.write_text(f"unavailable: {reason}\n", encoding="utf-8")


def run_acceptance(
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    allow_live_model: bool = False,
    mode: str = "smoke",
    meeting_id: str | None = None,
    scenario: str | None = None,
    ollama_timeout: float = 300.0,
    gpu_monitor: bool = False,
    gpu_sample_interval: float = 1.0,
    stop_on_failure: bool = True,
    timestamp: str | None = None,
) -> dict[str, Any]:
    fixtures = load_fixtures(fixture_path)
    selected = select_meetings(fixtures, mode=mode, meeting_id=meeting_id, scenario=scenario)
    run_id = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "schema_version": "agent-v1-phase5b-live-acceptance-config-v1",
        "generated_at": utc_now(),
        "fixture_path": str(fixture_path),
        "output_dir": str(output_dir),
        "allow_live_model": allow_live_model,
        "mode": mode,
        "meeting_id": meeting_id,
        "scenario": scenario,
        "ollama_timeout": ollama_timeout,
        "gpu_monitor": gpu_monitor,
        "gpu_sample_interval": gpu_sample_interval,
        "stop_on_failure": stop_on_failure,
        "selected_meeting_ids": [meeting["meeting_id"] for meeting in selected],
        "serial_execution": True,
    }
    write_json(output_dir / "run_config.json", run_config)

    meeting_reports: list[dict[str, Any]] = []
    stopped_reason = None
    for index, meeting in enumerate(selected, start=1):
        summary = run_meeting_acceptance(
            meeting=meeting,
            output_dir=output_dir,
            allow_live_model=allow_live_model,
            ollama_timeout=ollama_timeout,
            gpu_monitor=gpu_monitor,
            gpu_sample_interval=gpu_sample_interval,
            run_index=index,
        )
        meeting_reports.append(summary)
        if stop_on_failure and should_stop_after_meeting(summary):
            stopped_reason = summary.get("stop_reason") or "stop_on_failure_gate"
            break

    report = build_acceptance_report(
        output_dir=output_dir,
        run_config=run_config,
        meetings=meeting_reports,
        selected_total=len(selected),
        stopped_reason=stopped_reason,
    )
    write_json(output_dir / "acceptance_report.json", report)
    write_json(output_dir / "gpu_summary.json", report["gpu_summary"])
    (output_dir / "acceptance_report.md").write_text(render_acceptance_report(report), encoding="utf-8")
    return report


def run_meeting_acceptance(
    *,
    meeting: dict[str, Any],
    output_dir: Path,
    allow_live_model: bool,
    ollama_timeout: float,
    gpu_monitor: bool,
    gpu_sample_interval: float,
    run_index: int,
) -> dict[str, Any]:
    meeting_id = str(meeting["meeting_id"])
    meeting_dir = output_dir / "meetings" / meeting_id
    meeting_dir.mkdir(parents=True, exist_ok=True)
    pipeline_log = meeting_dir / "pipeline.log"
    log_line(pipeline_log, "meeting.started", meeting_id=meeting_id, run_index=run_index)

    transcript = fixture_transcript_text(meeting)
    (meeting_dir / "input_transcript.txt").write_text(transcript, encoding="utf-8")
    formal_before = formal_result_snapshot(meeting)
    write_json(meeting_dir / "formal_before_snapshot.json", formal_before)

    gpu = GpuMonitor(
        output_path=meeting_dir / "gpu_samples.csv",
        interval_seconds=gpu_sample_interval,
        enabled=gpu_monitor,
    )
    gpu.start()

    started_at = time.perf_counter()
    runtime = LiveAnalysisRuntime(
        meeting_fixture=meeting,
        meeting_dir=meeting_dir,
        allow_live_model=allow_live_model,
        ollama_timeout=ollama_timeout,
    )
    orchestrator = AgentOrchestrator(
        runtime=runtime,
        audit_store=AgentShadowAuditStore(trace_root=meeting_dir / "shadow_trace"),
    )
    shadow = orchestrator.run_shadow(
        context=AgentContext(
            run_id=f"phase5b-{meeting_id}",
            meeting_id=meeting_id,
            project_id=meeting.get("project_id", ""),
            meeting_type=meeting["meeting_type"],
            objective=meeting.get("title", ""),
            transcript=meeting.get("transcript", []),
            meeting_analysis=deepcopy(meeting["formal_analysis"]),
            runtime_metadata={
                "agent_mode_enabled": False,
                "agent_shadow_mode": True,
                "agent_actions_enabled": False,
                "acceptance_phase": "agent-v1-phase5b",
            },
        ),
        formal_analysis=meeting["formal_analysis"],
    )
    total_duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    gpu_summary = gpu.stop()
    write_json(meeting_dir / "gpu_summary.json", gpu_summary)

    formal_after = formal_result_snapshot(meeting)
    write_json(meeting_dir / "formal_after_snapshot.json", formal_after)
    isolation = compare_formal_snapshots(formal_before, formal_after)
    write_json(meeting_dir / "formal_isolation.json", isolation)

    shadow_payload = shadow.model_dump()
    write_json(meeting_dir / "shadow_audit.json", shadow_payload)
    quality = score_quality(
        analysis=shadow.shadow_analysis,
        transcript=transcript,
        validator_audit=shadow.validation_audit,
        allow_live_model=allow_live_model,
    )
    write_json(meeting_dir / "quality_score.json", quality)
    (meeting_dir / "quality_score.md").write_text(render_quality_score(quality), encoding="utf-8")

    ensure_required_artifacts(meeting_dir)
    stop_reason = stop_reason_for_meeting(
        shadow_status=shadow.status,
        total_duration_ms=total_duration_ms,
        gpu_summary=gpu_summary,
        isolation=isolation,
        quality=quality,
        layer_result=runtime.layer_result,
    )
    actual_plan = [step["tool_name"] for step in shadow.steps if step["status"] != "skipped"]
    expected_plan = list(EXPECTED_ENABLED_TOOLS[meeting["meeting_type"]])
    report = {
        "meeting_id": meeting_id,
        "meeting_type": meeting["meeting_type"],
        "title": meeting["title"],
        "run_index": run_index,
        "allow_live_model": allow_live_model,
        "cold_start": run_index == 1,
        "expected_plan": expected_plan,
        "actual_plan": actual_plan,
        "plan_matches_expected": actual_plan == expected_plan,
        "shadow_status": shadow.status,
        "shadow_duration_ms": shadow.duration_ms,
        "total_duration_ms": total_duration_ms,
        "tool_statuses": {step["tool_name"]: step["status"] for step in shadow.steps},
        "tool_duration_ms": {step["tool_name"]: step.get("duration_ms", 0.0) for step in shadow.steps},
        "real_model_call_count": runtime.real_model_call_count,
        "result_source": shadow.result_source,
        "fallback_reason": shadow.fallback_reason,
        "failure_reason": runtime.layer_result.failure_reason if runtime.layer_result else None,
        "quality_score": quality["total_score"],
        "quality_passed": quality["passed"],
        "formal_isolation": isolation,
        "gpu_summary": gpu_summary,
        "output_dir": str(meeting_dir),
        "stop_reason": stop_reason,
    }
    write_json(meeting_dir / "meeting_report.json", report)
    log_line(pipeline_log, "meeting.completed", **report)
    return report


def build_acceptance_report(
    *,
    output_dir: Path,
    run_config: dict[str, Any],
    meetings: list[dict[str, Any]],
    selected_total: int,
    stopped_reason: str | None,
) -> dict[str, Any]:
    success_count = sum(1 for meeting in meetings if meeting_passed(meeting))
    durations = [float(meeting["total_duration_ms"]) for meeting in meetings]
    gpu_summaries = [meeting["gpu_summary"] for meeting in meetings]
    mode = run_config["mode"]
    required_successes = 3 if mode == "smoke" and selected_total == 3 else 8 if mode == "full" and selected_total == 9 else selected_total
    overall_passed = (
        len(meetings) == selected_total
        and success_count >= required_successes
        and not stopped_reason
    )
    return {
        "schema_version": "agent-v1-phase5b-live-acceptance-report-v1",
        "generated_at": utc_now(),
        "output_dir": str(output_dir),
        "run_config": run_config,
        "meetings_selected": selected_total,
        "meetings_completed": len(meetings),
        "success_count": success_count,
        "required_successes": required_successes,
        "overall_passed": overall_passed,
        "stopped_reason": stopped_reason,
        "cold_start_duration_ms": meetings[0]["total_duration_ms"] if meetings else None,
        "warm_start_average_duration_ms": _avg_or_none([meeting["total_duration_ms"] for meeting in meetings[1:]]),
        "max_duration_ms": max(durations) if durations else None,
        "timeout_count": sum(1 for meeting in meetings if "timeout" in meeting["tool_statuses"].values()),
        "fallback_count": sum(1 for meeting in meetings if meeting.get("fallback_reason")),
        "error_count": sum(1 for meeting in meetings if meeting.get("failure_reason")),
        "gpu_summary": aggregate_gpu_summaries(gpu_summaries),
        "meetings": meetings,
    }


def score_quality(
    *,
    analysis: dict[str, Any],
    transcript: str,
    validator_audit: list[dict[str, Any]],
    allow_live_model: bool,
) -> dict[str, Any]:
    if not allow_live_model or not analysis:
        return {
            "available": False,
            "total_score": 0,
            "passed": False,
            "unavailable_reason": "live_model_not_allowed" if not allow_live_model else "analysis_unavailable",
            "rubric": rubric_template(),
            "checks": {},
            "manual_review_required": True,
        }
    checks = quality_checks(analysis, transcript, validator_audit)
    category_scores = {
        "six_dimension_completeness": max(0, 10 - checks["missing_dimension_count"] * 2),
        "factual_accuracy": max(0, 25 - checks["invalid_source_text_count"] * 5 - checks["severe_hallucination_count"] * 25),
        "evidence_coverage": max(0, 20 - checks["missing_source_text_count"] * 4 - checks["invalid_source_text_count"] * 3),
        "boundary_accuracy": max(
            0,
            20
            - checks["proposal_in_conclusion_count"] * 8
            - checks["question_in_conclusion_count"] * 8
            - checks["risk_issue_confusion_count"] * 5,
        ),
        "action_item_accuracy": max(0, 15 - checks["unsupported_owner_count"] * 8 - checks["unsupported_deadline_count"] * 8),
        "dedupe_and_structure": max(0, 10 - checks["cross_dimension_duplicate_count"] * 4),
    }
    total = sum(category_scores.values())
    severe_failure = any(
        checks[key] > 0
        for key in (
            "severe_hallucination_count",
            "unsupported_owner_count",
            "unsupported_deadline_count",
        )
    )
    return {
        "available": True,
        "total_score": total,
        "passed": total >= 80 and not severe_failure,
        "category_scores": category_scores,
        "checks": checks,
        "rubric": rubric_template(),
        "manual_review_required": True,
    }


def quality_checks(analysis: dict[str, Any], transcript: str, validator_audit: list[dict[str, Any]]) -> dict[str, int]:
    missing_dimension_count = sum(
        1
        for field in (
            "meeting_agenda",
            "meeting_summary",
            "key_conclusions",
            "action_items",
            "unresolved_issues",
            "risks_and_focus",
        )
        if not field_present(analysis.get(field))
    )
    missing_source = 0
    invalid_source = 0
    unsupported_owner = 0
    unsupported_deadline = 0
    for field in EVIDENCE_FIELDS:
        for item in analysis.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_text") or "")
            if not source:
                missing_source += 1
            elif not source_in_transcript(source, transcript):
                invalid_source += 1
            if field == "action_items":
                owner = item.get("owner_name") or item.get("owner")
                deadline = item.get("deadline") or item.get("due_date")
                if owner and source and normalize_text(owner) not in normalize_text(source):
                    unsupported_owner += 1
                if deadline and source and normalize_text(deadline) not in normalize_text(source):
                    unsupported_deadline += 1
    validator_removes = sum(1 for item in validator_audit if item.get("action") == "remove")
    return {
        "missing_dimension_count": missing_dimension_count,
        "missing_source_text_count": missing_source,
        "invalid_source_text_count": invalid_source,
        "severe_hallucination_count": invalid_source,
        "proposal_in_conclusion_count": count_terms_in_conclusions(analysis, ("建议", "可以考虑", "是否", "疑问")),
        "question_in_conclusion_count": count_terms_in_conclusions(analysis, ("？", "?")),
        "unsupported_owner_count": unsupported_owner,
        "unsupported_deadline_count": unsupported_deadline,
        "customer_expectation_as_commitment_count": count_customer_expectation_commitments(analysis),
        "risk_issue_confusion_count": count_risk_issue_confusion(analysis),
        "cross_department_dependency_issue_count": 0,
        "cross_dimension_duplicate_count": count_cross_dimension_duplicates(analysis),
        "validator_remove_count": validator_removes,
    }


def formal_result_snapshot(meeting: dict[str, Any]) -> dict[str, Any]:
    formal = deepcopy(meeting.get("formal_analysis", {}))
    return {
        "available": True,
        "source": "fixture_formal_analysis",
        "meeting_summary_hash": stable_hash(formal.get("meeting_summary")),
        "meeting_summary_item_count": len(formal.get("meeting_agenda", []) or []),
        "action_item_hash": stable_hash(formal.get("action_items", [])),
        "action_item_count": len(formal.get("action_items", []) or []),
        "result_source": (formal.get("metadata") or {}).get("result_source"),
        "full_hash": stable_hash(formal),
    }


def compare_formal_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    unchanged = before.get("full_hash") == after.get("full_hash")
    return {
        "available": before.get("available") and after.get("available"),
        "meeting_summary_unchanged": before.get("meeting_summary_hash") == after.get("meeting_summary_hash"),
        "action_items_unchanged": before.get("action_item_hash") == after.get("action_item_hash"),
        "result_source_unchanged": before.get("result_source") == after.get("result_source"),
        "shadow_did_not_modify_formal_result": unchanged,
        "before": before,
        "after": after,
    }


def stop_reason_for_meeting(
    *,
    shadow_status: str,
    total_duration_ms: float,
    gpu_summary: dict[str, Any],
    isolation: dict[str, Any],
    quality: dict[str, Any],
    layer_result: LayerCaptureResult | None,
) -> str | None:
    failure_reason = layer_result.failure_reason if layer_result else None
    if shadow_status in {"failed", "timeout"}:
        return f"shadow_{shadow_status}"
    if failure_reason:
        code = classify_failure(failure_reason)
        if code in {"tool_timeout", "json_parse_failed", "validator_failed", "cuda_oom", "ollama_or_worker_failed"}:
            return code
    if total_duration_ms > 300_000:
        return "duration_over_300_seconds"
    if gpu_summary.get("oom_detected"):
        return "cuda_oom"
    if not isolation.get("shadow_did_not_modify_formal_result"):
        return "formal_result_changed"
    if quality.get("available") and (
        int(quality["checks"].get("severe_hallucination_count", 0)) > 0
        or int(quality["checks"].get("unsupported_owner_count", 0)) > 0
        or int(quality["checks"].get("unsupported_deadline_count", 0)) > 0
    ):
        return "quality_stop_condition"
    return None


def should_stop_after_meeting(summary: dict[str, Any]) -> bool:
    return bool(summary.get("stop_reason"))


def meeting_passed(summary: dict[str, Any]) -> bool:
    return (
        not summary.get("stop_reason")
        and summary.get("shadow_status") in {"success", "partial"}
        and summary.get("formal_isolation", {}).get("shadow_did_not_modify_formal_result")
        and (not summary.get("allow_live_model") or summary.get("quality_passed"))
        and float(summary.get("total_duration_ms") or 0) <= 300_000
        and not summary.get("gpu_summary", {}).get("oom_detected")
    )


def aggregate_gpu_summaries(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "available": any(item.get("available") for item in items),
        "peak_memory_used_mb": _max_or_none([item.get("peak_memory_used_mb") for item in items]),
        "memory_total_mb": _max_or_none([item.get("memory_total_mb") for item in items]),
        "avg_gpu_utilization_pct": _avg_or_none([item.get("avg_gpu_utilization_pct") for item in items]),
        "peak_temperature_c": _max_or_none([item.get("peak_temperature_c") for item in items]),
        "peak_power_draw_w": _max_or_none([item.get("peak_power_draw_w") for item in items]),
        "oom_detected": any(item.get("oom_detected") for item in items),
        "sustained_memory_growth_detected": any(item.get("sustained_memory_growth_detected") for item in items),
        "warnings": [item.get("warning") for item in items if item.get("warning")],
    }


def render_acceptance_report(report: dict[str, Any]) -> str:
    lines = [
        "# Agent v1 Phase 5B Live Shadow Acceptance",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- allow_live_model: {report['run_config']['allow_live_model']}",
        f"- mode: {report['run_config']['mode']}",
        f"- meetings_completed: {report['meetings_completed']}/{report['meetings_selected']}",
        f"- success_count: {report['success_count']}",
        f"- required_successes: {report['required_successes']}",
        f"- overall_passed: {report['overall_passed']}",
        f"- stopped_reason: {report['stopped_reason']}",
        "",
        "## Meetings",
        "",
        "| Meeting | Scenario | Status | Total ms | Quality | Stop reason |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for meeting in report["meetings"]:
        lines.append(
            "| {meeting_id} | {meeting_type} | {status} | {duration} | {quality} | {stop} |".format(
                meeting_id=meeting["meeting_id"],
                meeting_type=meeting["meeting_type"],
                status=meeting["shadow_status"],
                duration=meeting["total_duration_ms"],
                quality=meeting.get("quality_score", ""),
                stop=meeting.get("stop_reason") or "",
            )
        )
    return "\n".join(lines) + "\n"


def render_quality_score(quality: dict[str, Any]) -> str:
    lines = [
        "# Quality Score",
        "",
        f"- available: {quality.get('available')}",
        f"- total_score: {quality.get('total_score')}",
        f"- passed: {quality.get('passed')}",
        f"- manual_review_required: {quality.get('manual_review_required')}",
        "",
        "## Rubric",
    ]
    for item in quality.get("rubric", []):
        lines.append(f"- {item['name']}: {item['points']} points")
    lines.extend(["", "## Rule Checks"])
    for key, value in (quality.get("checks") or {}).items():
        lines.append(f"- {key}: {value}")
    if quality.get("unavailable_reason"):
        lines.extend(["", f"Unavailable reason: {quality['unavailable_reason']}"])
    return "\n".join(lines) + "\n"


def rubric_template() -> list[dict[str, Any]]:
    return [
        {"name": "six_dimension_completeness", "points": 10, "manual_review": True},
        {"name": "factual_accuracy", "points": 25, "manual_review": True},
        {"name": "evidence_coverage", "points": 20, "manual_review": True},
        {"name": "boundary_accuracy", "points": 20, "manual_review": True},
        {"name": "action_item_accuracy", "points": 15, "manual_review": True},
        {"name": "dedupe_and_structure", "points": 10, "manual_review": True},
    ]


def ensure_required_artifacts(meeting_dir: Path) -> None:
    for name in REQUIRED_MEETING_ARTIFACTS:
        path = meeting_dir / name
        if path.exists():
            continue
        if name.endswith(".json"):
            write_json(path, unavailable("artifact_not_generated"))
        else:
            path.write_text("unavailable: artifact_not_generated\n", encoding="utf-8")


def serialize_rag_context(rag_context: RagContext) -> dict[str, Any]:
    return {
        "available": True,
        "rag_chunk_count": len(rag_context.chunk_ids),
        "rag_chunk_ids": rag_context.chunk_ids,
        "rag_context_chars": len(rag_context.text),
        "collection_name": rag_context.collection_name,
        "embedding_model": rag_context.embedding_model,
        "dataset_version": rag_context.dataset_version,
        "chunk_schema_version": rag_context.chunk_schema_version,
        "chunks": rag_context.chunks,
        "text": rag_context.text,
    }


def fixture_transcript_text(meeting: dict[str, Any]) -> str:
    return build_transcript_text(meeting.get("transcript", []))


def tool_result(
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


def resolve_run_status(steps: list[AgentStepResult], *, stopped: bool) -> str:
    statuses = {step.status for step in steps}
    if "timeout" in statuses and stopped:
        return "timeout"
    if "failed" in statuses and stopped:
        return "failed"
    if "failed" in statuses or "timeout" in statuses or "skipped" in statuses:
        return "partial"
    return "success"


def classify_failure(reason: str | None) -> str:
    lowered = (reason or "").lower()
    if "timeout" in lowered:
        return "tool_timeout"
    if "json" in lowered:
        return "json_parse_failed"
    if "validator" in lowered:
        return "validator_failed"
    if "cuda" in lowered or "out of memory" in lowered or "oom" in lowered:
        return "cuda_oom"
    if "ollama" in lowered or "connection" in lowered or "worker" in lowered:
        return "ollama_or_worker_failed"
    return "live_analysis_failed"


def unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def field_present(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def normalize_text(value: object) -> str:
    return "".join(str(value or "").lower().split())


def source_in_transcript(source: str, transcript: str) -> bool:
    return bool(source) and "..." not in source and normalize_text(source) in normalize_text(transcript)


def claim_text(field: str, item: dict[str, Any]) -> str:
    if field == "key_conclusions":
        return str(item.get("conclusion") or "")
    if field == "action_items":
        return str(item.get("task") or "")
    if field == "unresolved_issues":
        return str(item.get("issue") or "")
    if field == "risks_and_focus":
        return str(item.get("risk") or "")
    return str(item)


def count_terms_in_conclusions(analysis: dict[str, Any], terms: tuple[str, ...]) -> int:
    count = 0
    for item in analysis.get("key_conclusions", []) or []:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('conclusion') or ''}{item.get('source_text') or ''}"
        if any(term in text for term in terms):
            count += 1
    return count


def count_customer_expectation_commitments(analysis: dict[str, Any]) -> int:
    terms = ("客户期望", "客户希望", "客户要求")
    commitment_terms = ("承诺", "必须", "确认")
    count = 0
    for field in ("key_conclusions", "action_items"):
        for item in analysis.get(field, []) or []:
            if isinstance(item, dict):
                text = json.dumps(item, ensure_ascii=False)
                if any(term in text for term in terms) and any(term in text for term in commitment_terms):
                    count += 1
    return count


def count_risk_issue_confusion(analysis: dict[str, Any]) -> int:
    risk_text = json.dumps(analysis.get("risks_and_focus", []), ensure_ascii=False)
    issue_text = json.dumps(analysis.get("unresolved_issues", []), ensure_ascii=False)
    return int("阻塞" in risk_text and "风险" in issue_text)


def count_cross_dimension_duplicates(analysis: dict[str, Any]) -> int:
    seen: list[tuple[str, str]] = []
    duplicate_count = 0
    for field in EVIDENCE_FIELDS:
        for item in analysis.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            text = normalize_text(claim_text(field, item))
            if not text:
                continue
            if any(other_field != field and other_text == text for other_field, other_text in seen):
                duplicate_count += 1
            seen.append((field, text))
    return duplicate_count


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "[N/A]":
        return None
    try:
        return float(text.split()[0])
    except ValueError:
        return None


def _max_or_none(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, int | float)]
    return max(numbers) if numbers else None


def _avg_or_none(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, int | float)]
    return round(sum(numbers) / len(numbers), 2) if numbers else None


def _sustained_growth(values: list[float]) -> bool:
    if len(values) < 4:
        return False
    first = values[0]
    last = values[-1]
    return last > first and (last - first >= 1024 or (first > 0 and last / first >= 1.1))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def log_line(path: Path, event: str, **fields: Any) -> None:
    payload = {"timestamp": utc_now(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Agent v1 Phase 5B live Shadow acceptance tooling.")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--allow-live-model", action="store_true")
    parser.add_argument("--scenario", choices=list(CORE_SCENARIOS), default=None)
    parser.add_argument("--meeting-id", default=None)
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--ollama-timeout", type=float, default=300.0)
    parser.add_argument("--gpu-monitor", action="store_true")
    parser.add_argument("--gpu-sample-interval", type=float, default=1.0)
    parser.add_argument("--stop-on-failure", action="store_true", default=True)
    parser.add_argument("--no-stop-on-failure", action="store_false", dest="stop_on_failure")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_acceptance(
        fixture_path=args.fixtures,
        output_root=args.output_root,
        allow_live_model=args.allow_live_model,
        mode=args.mode,
        meeting_id=args.meeting_id,
        scenario=args.scenario,
        ollama_timeout=args.ollama_timeout,
        gpu_monitor=args.gpu_monitor,
        gpu_sample_interval=args.gpu_sample_interval,
        stop_on_failure=args.stop_on_failure,
        timestamp=args.timestamp,
    )
    print(json.dumps({"output_dir": report["output_dir"], "overall_passed": report["overall_passed"]}, ensure_ascii=False))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
