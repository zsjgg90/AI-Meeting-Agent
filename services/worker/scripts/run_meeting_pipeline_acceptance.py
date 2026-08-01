from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
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


from app.meeting_analysis_pipeline import analyze_meeting_with_fallback  # noqa: E402
from app.meeting_analyst_service import MeetingAnalystService  # noqa: E402
from app.observability import LOGGER_NAME  # noqa: E402
from app.ollama_client import OllamaClient  # noqa: E402
from app.semantic_event_extractor import SemanticEventExtractor  # noqa: E402
from app.transcript_builder import build_transcript_text  # noqa: E402


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "meeting_pipeline_acceptance"
REQUIRED_FIELDS = [
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
]
PROPOSAL_MARKERS = ("建议", "可以考虑", "要不要", "是否可以", "我觉得")
CONFIRM_MARKERS = ("决定", "确认", "确定", "就这么定", "正式")
RESOLVED_MARKERS = ("已解决", "解决", "确认方案", "已经处理", "关闭")


@dataclass
class AcceptanceCase:
    meeting_id: str
    meeting_type: str
    title: str
    transcript: list[dict[str, Any]]


@contextlib.contextmanager
def capture_meeting_log(log_file: Path):
    logger = logging.getLogger(LOGGER_NAME)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    with log_file.open("a", encoding="utf-8", buffering=1) as stream:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                yield
            finally:
                logger.removeHandler(handler)
                handler.close()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", "", text.lower())


def flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(flatten(item) for item in value.values())
    return str(value)


def text_in_sources(text: str, sources: list[str]) -> bool:
    normalized_text = normalize_text(text)
    source_blob = normalize_text(" ".join(sources))
    return bool(normalized_text) and normalized_text in source_blob


def item_source_text(item: dict[str, Any]) -> str:
    return str(item.get("source_text") or item.get("source") or "")


def list_items(result: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = result.get(field)
    return value if isinstance(value, list) else []


def check_schema(result: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in result]
    return {
        "passed": not missing,
        "missing_fields": missing,
        "dimension_counts": {
            field: len(result.get(field, [])) if isinstance(result.get(field), list) else int(bool(result.get(field)))
            for field in REQUIRED_FIELDS
        },
    }


def has_any_dimension_output(result: dict[str, Any]) -> bool:
    if not result:
        return False
    for field in REQUIRED_FIELDS:
        value = result.get(field)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def count_owner_deadline_hallucinations(result: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, item in enumerate(list_items(result, "action_items")):
        source = item_source_text(item)
        for field in ("owner", "owner_name", "deadline", "due_date"):
            value = str(item.get(field) or "").strip()
            if value and normalize_text(value) not in normalize_text(source):
                issues.append(
                    {
                        "field": field,
                        "index": index,
                        "value": value,
                        "source_text": source,
                    }
                )
    return issues


def count_no_evidence_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in ("key_conclusions", "action_items", "unresolved_issues", "risks_and_focus"):
        for index, item in enumerate(list_items(result, field)):
            if not item_source_text(item).strip():
                issues.append({"field": field, "index": index, "item": item})
    return issues


def count_duplicate_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    for field in REQUIRED_FIELDS:
        seen: dict[str, int] = {}
        value = result.get(field)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            key = normalize_text(item)
            if not key:
                continue
            if key in seen:
                duplicates.append(
                    {
                        "field": field,
                        "first_index": seen[key],
                        "duplicate_index": index,
                    }
                )
            else:
                seen[key] = index
    return duplicates


def count_proposal_as_decision(result: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for index, item in enumerate(list_items(result, "key_conclusions")):
        text = flatten(item)
        has_proposal = any(marker in text for marker in PROPOSAL_MARKERS)
        has_confirmation = any(marker in text for marker in CONFIRM_MARKERS)
        if has_proposal and not has_confirmation:
            hits.append({"index": index, "item": item})
    return hits


def count_resolved_issue_errors(result: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for index, item in enumerate(list_items(result, "unresolved_issues")):
        text = flatten(item)
        if any(marker in text for marker in RESOLVED_MARKERS):
            hits.append({"index": index, "item": item})
    return hits


def quality_metrics(result: dict[str, Any]) -> dict[str, Any]:
    schema = check_schema(result)
    owner_deadline = count_owner_deadline_hallucinations(result)
    no_evidence = count_no_evidence_items(result)
    duplicates = count_duplicate_items(result)
    proposal_as_decision = count_proposal_as_decision(result)
    resolved_issue_errors = count_resolved_issue_errors(result)
    return {
        "schema": schema,
        "owner_deadline_hallucinations": owner_deadline,
        "owner_deadline_hallucination_count": len(owner_deadline),
        "no_evidence_items": no_evidence,
        "no_evidence_count": len(no_evidence),
        "duplicate_items": duplicates,
        "duplicate_count": len(duplicates),
        "proposal_as_decision": proposal_as_decision,
        "proposal_as_decision_count": len(proposal_as_decision),
        "resolved_issue_errors": resolved_issue_errors,
        "resolved_issue_error_count": len(resolved_issue_errors),
        "needs_manual_review": True,
        "manual_review_reason": "Semantic accuracy and completeness require human review.",
    }


def run_new_pipeline(case: AcceptanceCase, ollama_timeout: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.perf_counter()
    transcript_text = build_transcript_text(case.transcript)
    try:
        semantic_extractor = SemanticEventExtractor(
            llm_client=OllamaClient(timeout=ollama_timeout)
        )

        def legacy_analyzer() -> dict[str, Any]:
            legacy_service = MeetingAnalystService(
                llm_client=OllamaClient(timeout=ollama_timeout)
            )
            return legacy_service.analyze(transcript_text)

        result = analyze_meeting_with_fallback(
            case.meeting_id,
            case.transcript,
            legacy_analyzer=legacy_analyzer,
            extractor=semantic_extractor,
        )
        metadata = result.get("_metadata") if isinstance(result.get("_metadata"), dict) else {}
        has_output = has_any_dimension_output(result)
        return result, {
            "ok": has_output,
            "status": "fallback_success" if metadata.get("fallback_reason") else "success",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "fallback_used": bool(metadata.get("fallback_reason")),
            "fallback_reason": metadata.get("fallback_reason"),
            "failed_utterance_count": metadata.get("failed_utterance_count", 0),
            "semantic_event_count": metadata.get("semantic_event_count"),
            "topic_count": metadata.get("topic_count"),
            "empty_output": not has_output,
            "error_message": None if has_output else "new_pipeline_empty_six_dimension_output",
        }
    except Exception as exc:
        semantic_fallback_reason = getattr(exc, "semantic_fallback_reason", None)
        return None, {
            "ok": False,
            "status": "fallback_failed" if semantic_fallback_reason else "failed",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "fallback_used": bool(semantic_fallback_reason),
            "fallback_reason": semantic_fallback_reason,
            "failed_utterance_count": getattr(exc, "failed_utterance_count", 0),
            "semantic_event_count": getattr(exc, "semantic_event_count", None),
            "topic_count": getattr(exc, "topic_count", None),
        }


def run_legacy_pipeline(case: AcceptanceCase, ollama_timeout: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.perf_counter()
    transcript_text = build_transcript_text(case.transcript)
    try:
        legacy_service = MeetingAnalystService(
            llm_client=OllamaClient(timeout=ollama_timeout)
        )
        result = legacy_service.analyze(transcript_text)
        has_output = has_any_dimension_output(result)
        return result, {
            "ok": has_output,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "empty_output": not has_output,
            "error_message": None if has_output else "legacy_pipeline_empty_six_dimension_output",
        }
    except Exception as exc:
        return None, {
            "ok": False,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }


def compare_results(
    case: AcceptanceCase,
    new_result: dict[str, Any] | None,
    new_run: dict[str, Any],
    legacy_result: dict[str, Any] | None,
    legacy_run: dict[str, Any],
) -> dict[str, Any]:
    new_metrics = quality_metrics(new_result or {}) if new_result else None
    legacy_metrics = quality_metrics(legacy_result or {}) if legacy_result else None
    return {
        "meeting_id": case.meeting_id,
        "meeting_type": case.meeting_type,
        "title": case.title,
        "new_pipeline": {
            "run": new_run,
            "metrics": new_metrics,
        },
        "legacy_pipeline": {
            "run": legacy_run,
            "metrics": legacy_metrics,
        },
        "needs_manual_review": True,
        "manual_review_dimensions": {
            "agenda_completeness": "needs_manual_review",
            "summary_accuracy": "needs_manual_review",
            "decision_accuracy": "needs_manual_review",
            "action_completeness": "needs_manual_review",
            "issue_accuracy": "needs_manual_review",
            "risk_accuracy": "needs_manual_review",
        },
    }


def build_summary(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(comparisons)
    new_success = sum(1 for item in comparisons if item["new_pipeline"]["run"].get("ok"))
    new_direct_success = sum(
        1 for item in comparisons if item["new_pipeline"]["run"].get("status") == "success"
    )
    new_fallback_success = sum(
        1 for item in comparisons if item["new_pipeline"]["run"].get("status") == "fallback_success"
    )
    new_fallback_failed = sum(
        1 for item in comparisons if item["new_pipeline"]["run"].get("status") == "fallback_failed"
    )
    fallback_cases = [
        {
            "meeting_id": item["meeting_id"],
            "reason": item["new_pipeline"]["run"].get("fallback_reason"),
        }
        for item in comparisons
        if item["new_pipeline"]["run"].get("fallback_used")
    ]

    aggregate = {
        "meeting_count": total,
        "new_pipeline_success_count": new_success,
        "new_pipeline_success_rate": round(new_success / total, 4) if total else 0.0,
        "new_pipeline_direct_success_count": new_direct_success,
        "new_pipeline_fallback_success_count": new_fallback_success,
        "new_pipeline_fallback_failed_count": new_fallback_failed,
        "fallback_count": len(fallback_cases),
        "fallback_cases": fallback_cases,
        "new_pipeline_duration_ms_total": round(
            sum(item["new_pipeline"]["run"].get("duration_ms", 0.0) for item in comparisons),
            2,
        ),
        "legacy_pipeline_duration_ms_total": round(
            sum(item["legacy_pipeline"]["run"].get("duration_ms", 0.0) for item in comparisons),
            2,
        ),
    }

    new_metric_totals = {
        "owner_deadline_hallucination_count": 0,
        "resolved_issue_error_count": 0,
        "proposal_as_decision_count": 0,
        "duplicate_count": 0,
        "no_evidence_count": 0,
    }
    failure_cases: list[dict[str, Any]] = []

    for item in comparisons:
        metrics = item["new_pipeline"].get("metrics") or {}
        for key in new_metric_totals:
            new_metric_totals[key] += int(metrics.get(key, 0))
        if not item["new_pipeline"]["run"].get("ok"):
            failure_cases.append(
                {
                    "meeting_id": item["meeting_id"],
                    "stage": "new_pipeline",
                    "reason": item["new_pipeline"]["run"].get("error_message"),
                }
            )
        if not item["legacy_pipeline"]["run"].get("ok"):
            failure_cases.append(
                {
                    "meeting_id": item["meeting_id"],
                    "stage": "legacy_pipeline",
                    "reason": item["legacy_pipeline"]["run"].get("error_message"),
                }
            )

    standards = {
        "new_pipeline_success_rate_gte_0_9": aggregate["new_pipeline_success_rate"] >= 0.9,
        "no_evidence_eq_0": new_metric_totals["no_evidence_count"] == 0,
        "owner_deadline_hallucination_eq_0": new_metric_totals["owner_deadline_hallucination_count"] == 0,
        "proposal_as_decision_eq_0": new_metric_totals["proposal_as_decision_count"] == 0,
        "resolved_issue_error_eq_0": new_metric_totals["resolved_issue_error_count"] == 0,
        "fallback_reason_traceable": all(case.get("reason") for case in fallback_cases),
        "manual_review_required": True,
    }

    passed_auto_gates = all(
        value
        for key, value in standards.items()
        if key != "manual_review_required"
    )

    return {
        "aggregate": aggregate,
        "new_pipeline_metric_totals": new_metric_totals,
        "acceptance_standards": standards,
        "auto_gates_passed": passed_auto_gates,
        "acceptance_passed": passed_auto_gates,
        "acceptance_passed_reason": (
            "Automatic gates passed; semantic quality dimensions still require manual review."
            if passed_auto_gates
            else "One or more automatic acceptance gates failed."
        ),
        "failure_cases": failure_cases,
        "improvement_suggestions": build_improvement_suggestions(new_metric_totals, fallback_cases, failure_cases),
    }


def build_improvement_suggestions(
    metric_totals: dict[str, int],
    fallback_cases: list[dict[str, Any]],
    failure_cases: list[dict[str, Any]],
) -> list[str]:
    suggestions = []
    if fallback_cases:
        suggestions.append("Inspect fallback_reason logs and stabilize the semantic extractor or downstream rule stages.")
    if metric_totals["no_evidence_count"]:
        suggestions.append("Tighten source_text propagation before allowing results into downstream formal workflows.")
    if metric_totals["owner_deadline_hallucination_count"]:
        suggestions.append("Keep owner/deadline only when present in source event attributes or evidence text.")
    if metric_totals["proposal_as_decision_count"]:
        suggestions.append("Strengthen proposal-vs-decision filtering before persistence.")
    if metric_totals["resolved_issue_error_count"]:
        suggestions.append("Strengthen resolved issue filtering in topic aggregation and six-dimension validation.")
    if failure_cases:
        suggestions.append("Re-run failed meetings after local Qwen3/RAG readiness checks pass.")
    if not suggestions:
        suggestions.append("Proceed to manual semantic review of agenda, summary, decision, action, issue, and risk quality.")
    return suggestions


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_markdown_report(path: Path, summary: dict[str, Any], comparisons: list[dict[str, Any]]) -> None:
    lines = [
        "# Meeting Pipeline Acceptance Report",
        "",
        f"- Meeting count: {summary['aggregate']['meeting_count']}",
        f"- New pipeline success rate: {summary['aggregate']['new_pipeline_success_rate']}",
        f"- Fallback count: {summary['aggregate']['fallback_count']}",
        f"- Auto gates passed: {summary['auto_gates_passed']}",
        f"- Acceptance passed: {summary['acceptance_passed']}",
        f"- Acceptance note: {summary['acceptance_passed_reason']}",
        "",
        "## Metric Totals",
        "",
    ]
    for key, value in summary["new_pipeline_metric_totals"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Meetings", ""])
    for item in comparisons:
        lines.extend(
            [
                f"### {item['meeting_id']} - {item['title']}",
                "",
                f"- Type: {item['meeting_type']}",
                f"- New ok: {item['new_pipeline']['run'].get('ok')}",
                f"- New duration ms: {item['new_pipeline']['run'].get('duration_ms')}",
                f"- New fallback used: {item['new_pipeline']['run'].get('fallback_used')}",
                f"- New fallback reason: {item['new_pipeline']['run'].get('fallback_reason')}",
                f"- Legacy ok: {item['legacy_pipeline']['run'].get('ok')}",
                f"- Legacy duration ms: {item['legacy_pipeline']['run'].get('duration_ms')}",
                "- Manual review: required",
                "",
            ]
        )
    lines.extend(["## Failure Cases", ""])
    if summary["failure_cases"]:
        for failure in summary["failure_cases"]:
            lines.append(f"- {failure['meeting_id']} / {failure['stage']}: {failure['reason']}")
    else:
        lines.append("- None recorded by automatic run.")
    lines.extend(["", "## Improvement Suggestions", ""])
    for suggestion in summary["improvement_suggestions"]:
        lines.append(f"- {suggestion}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def acceptance_cases() -> list[AcceptanceCase]:
    return [
        AcceptanceCase(
            meeting_id="project_weekly",
            meeting_type="项目周会",
            title="支付改造项目周会",
            transcript=[
                seg("project_weekly", 0, "项目经理", "今天同步支付改造本周进展，重点看联调、上线计划和遗留风险。"),
                seg("project_weekly", 1, "后端负责人", "支付回调接口已经完成开发，联调环境今天下午可以提供给前端。"),
                seg("project_weekly", 2, "前端负责人", "前端支付页还差异常态提示，明天下午前由我补齐并提交测试。"),
                seg("project_weekly", 3, "测试负责人", "目前还有一个遗留问题，沙箱支付偶发返回超时，原因还没有定位。"),
                seg("project_weekly", 4, "后端负责人", "超时问题我们已经加了重试和日志，今晚验证通过后就可以关闭。"),
                seg("project_weekly", 5, "项目经理", "结论是上线时间保持周五不变，测试明天完成首轮回归。"),
            ],
        ),
        AcceptanceCase(
            meeting_id="requirement_review",
            meeting_type="需求评审",
            title="会员权益需求评审",
            transcript=[
                seg("requirement_review", 0, "产品经理", "本次评审会员权益页改版，议程是确认权益展示、领取流程和上线范围。"),
                seg("requirement_review", 1, "产品经理", "我建议先把积分翻倍权益放到首屏，但这只是方案讨论。"),
                seg("requirement_review", 2, "运营负责人", "正式决定首屏只展示三项核心权益，积分翻倍放在第二屏，避免首屏信息过载。"),
                seg("requirement_review", 3, "设计负责人", "设计稿由我在周三下班前更新，补齐第二屏权益卡片状态。"),
                seg("requirement_review", 4, "研发负责人", "领取流程需要增加失败重试，但不需要新增数据库表。"),
                seg("requirement_review", 5, "产品经理", "遗留问题是老会员历史权益文案是否同步调整，今天还没有结论。"),
            ],
        ),
        AcceptanceCase(
            meeting_id="risk_review",
            meeting_type="风险讨论",
            title="大促库存风险评审",
            transcript=[
                seg("risk_review", 0, "项目经理", "今天只讨论大促库存扣减风险和应对预案。"),
                seg("risk_review", 1, "架构师", "如果秒杀流量超过预估，库存服务可能出现锁等待，导致下单延迟。"),
                seg("risk_review", 2, "后端负责人", "应对方案是增加库存预扣缓存，并保留数据库强一致校验。"),
                seg("risk_review", 3, "运维负责人", "我负责在周四前完成压测环境扩容和监控告警配置。"),
                seg("risk_review", 4, "产品经理", "用户侧如果库存不足，需要明确提示售罄，不再展示可购买按钮。"),
                seg("risk_review", 5, "项目经理", "结论是预扣缓存方案通过，周五压测后再决定是否开启降级开关。"),
            ],
        ),
        AcceptanceCase(
            meeting_id="retrospective",
            meeting_type="复盘会议",
            title="客服工单系统上线复盘",
            transcript=[
                seg("retrospective", 0, "项目经理", "今天复盘客服工单系统上线，重点看故障原因、改进动作和后续安排。"),
                seg("retrospective", 1, "客服负责人", "上线首小时工单通知延迟，影响了客服响应速度。"),
                seg("retrospective", 2, "后端负责人", "根因已经确认，是消息队列消费者数量配置过低，扩容后问题已解决。"),
                seg("retrospective", 3, "运维负责人", "后续由我在周二前补充队列积压监控和短信告警。"),
                seg("retrospective", 4, "测试负责人", "这次遗漏了高并发通知场景，回归用例需要补充压力测试。"),
                seg("retrospective", 5, "项目经理", "遗留问题是预生产环境的队列规模是否要和生产保持一致，还需要架构组确认。"),
            ],
        ),
        AcceptanceCase(
            meeting_id="decision_meeting",
            meeting_type="决策会议",
            title="推荐算法上线决策会",
            transcript=[
                seg("decision_meeting", 0, "负责人", "今天决策推荐算法新版本是否进入灰度。"),
                seg("decision_meeting", 1, "算法负责人", "离线指标提升百分之三，但冷启动用户点击率没有明显改善。"),
                seg("decision_meeting", 2, "产品负责人", "我建议本周先不上全量，先做百分之十灰度观察。"),
                seg("decision_meeting", 3, "负责人", "最终决定本周只开启百分之十灰度，不做全量上线。"),
                seg("decision_meeting", 4, "数据分析师", "我负责每天上午十点输出灰度指标报告，持续三天。"),
                seg("decision_meeting", 5, "负责人", "风险是灰度期间可能影响新用户推荐稳定性，需要保留一键回滚方案。"),
            ],
        ),
    ]


def seg(meeting_id: str, index: int, speaker: str, text: str) -> dict[str, Any]:
    return {
        "id": f"{meeting_id}_seg_{index}",
        "speaker_name": speaker,
        "speaker_label": speaker,
        "start_time": float(index * 10),
        "end_time": float(index * 10 + 8),
        "text": text,
    }


def run_acceptance(cases: list[AcceptanceCase], output_root: Path, ollama_timeout: int) -> dict[str, Any]:
    run_dir = output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    comparisons: list[dict[str, Any]] = []
    for case in cases:
        meeting_dir = run_dir / case.meeting_id
        meeting_dir.mkdir(parents=True, exist_ok=True)
        write_json(meeting_dir / "meeting_input.json", asdict(case))
        log_file = meeting_dir / "pipeline.log"

        with capture_meeting_log(log_file):
            print(f"[ACCEPTANCE] Running {case.meeting_id} ({case.meeting_type})", flush=True)
            new_result, new_run = run_new_pipeline(case, ollama_timeout)
            write_json(meeting_dir / "new_pipeline_result.json", new_result or {"error": new_run})
            write_json(meeting_dir / "new_pipeline_run.json", new_run)
            legacy_result, legacy_run = run_legacy_pipeline(case, ollama_timeout)
            write_json(meeting_dir / "legacy_pipeline_result.json", legacy_result or {"error": legacy_run})
            write_json(meeting_dir / "legacy_pipeline_run.json", legacy_run)

        comparison = compare_results(case, new_result, new_run, legacy_result, legacy_run)
        write_json(meeting_dir / "comparison.json", comparison)
        comparisons.append(comparison)

    summary = build_summary(comparisons)
    report = {
        "generated_at": datetime.now().isoformat(),
        "run_dir": str(run_dir),
        "summary": summary,
        "meetings": comparisons,
    }
    write_json(run_dir / "acceptance_report.json", report)
    write_markdown_report(run_dir / "acceptance_report.md", summary, comparisons)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live acceptance comparison for semantic pipeline vs Qwen3+RAG.")
    parser.add_argument("--limit", type=int, default=3, help="Limit number of built-in meetings. Default runs 3 acceptance meetings.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT), help="Acceptance output root.")
    parser.add_argument("--ollama-timeout", type=int, default=120, help="Per Ollama request timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = acceptance_cases()
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]
    report = run_acceptance(cases, Path(args.output_dir), args.ollama_timeout)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["auto_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
