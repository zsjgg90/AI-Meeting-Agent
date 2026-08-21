from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]
API_ROOT = PROJECT_ROOT / "services" / "api"
DEFAULT_INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "debug"
    / "batch_meetings"
    / "input"
    / "MeetMind_AI_V2.6_.txt"
)
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "debug"
    / "first_loss_analysis"
)


def configure_worker_import_path() -> None:
    preferred_paths = [str(WORKER_ROOT), str(PROJECT_ROOT)]
    sys.path = preferred_paths + [
        entry for entry in sys.path if entry not in preferred_paths
    ]

    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if module_name == "app" or module_name.startswith("app."):
            if module_file and Path(module_file).resolve().is_relative_to(API_ROOT):
                del sys.modules[module_name]


configure_worker_import_path()

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.action_fusion import fuse_action_items, mark_action_fusion_final_survivors
from app.analysis_contract import (
    canonicalize_meeting_analysis_aliases,
    ensure_non_empty_analysis_result,
    normalize_meeting_analysis_result,
)
from app.anti_hallucination_validator import validate_meeting_analysis_with_audit
from app.config import get_settings
from app.decision_fusion import fuse_key_conclusions_with_decisions
from app.evidence_resolver import resolve_meeting_analysis_evidence
from app.meeting_analysis_pipeline import (
    _semantic_action_candidates_from_trace,
    _semantic_decision_candidates_from_trace,
    _semantic_unresolved_candidates_from_trace,
    run_semantic_shadow_trace,
)
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor
from app.meeting_analyst_prompt import build_meeting_analyst_prompt
from app.meeting_analyst_service import MeetingAnalystService, extract_json
from app.ollama_client import OllamaClient
from app.prompt_registry import get_meeting_analyst_prompt_spec
from app.transcript_builder import build_transcript_text
from app.unresolved_fusion import fuse_unresolved_issues
from services.worker.scripts.batch_import_text_meetings import (
    ParsedMeetingText,
    parse_meeting_text,
    segment_times,
)


DIMENSION_FIELDS = {
    "Action": "action_items",
    "Decision": "key_conclusions",
    "Unresolved": "unresolved_issues",
    "Risk": "risks_and_focus",
}

STAGE_ORDER = [
    "Transcript",
    "Semantic",
    "RAG",
    "Qwen",
    "Fusion",
    "Evidence",
    "PostProcessor",
    "Validator",
    "Final",
]


@dataclass(frozen=True)
class AnalysisTarget:
    key: str
    label: str
    dimension: str
    expectation: str
    keywords: tuple[str, ...]
    semantic_groups: tuple[tuple[str, ...], ...] = ()
    evidence_keywords: tuple[str, ...] = ()
    entity_keywords: tuple[str, ...] = ()
    min_semantic_groups: int = 2
    notes: str = ""


TARGETS = [
    AnalysisTarget(
        key="action_quoted_example",
        label="Action: quoted example -> 负责人跟进这个事情",
        dimension="Action",
        expectation="absent",
        keywords=("负责人跟进这个事情", "用户只是提醒一下", "这个事情后面关注一下"),
        semantic_groups=(
            ("负责人跟进", "跟进这个事情"),
            ("用户只是提醒", "提醒一下", "关注一下"),
        ),
        evidence_keywords=("负责人跟进这个事情", "用户只是提醒一下", "这个事情后面关注一下"),
        notes="应被识别为 quoted example / reminder boundary，而不是正式任务。",
    ),
    AnalysisTarget(
        key="action_progress_update",
        label="Action: progress update -> 录音页面现在基本完成",
        dimension="Action",
        expectation="absent",
        keywords=("录音页面现在基本完成",),
        semantic_groups=(
            ("录音页面", "录音流程"),
            ("基本完成", "二次确认", "生成状态"),
        ),
        evidence_keywords=("录音页面现在基本完成", "结束会议以后增加了二次确认", "生成状态"),
        notes="应被识别为进展同步，不是新增待办。",
    ),
    AnalysisTarget(
        key="action_ai_fluctuation",
        label="Action: 排查 AI 分析结果波动原因",
        dimension="Action",
        expectation="present",
        keywords=("排查AI分析结果波动原因", "排查 AI 分析结果波动原因", "重点看模型输出和后处理链路"),
        semantic_groups=(
            ("排查", "定位", "分析"),
            ("AI分析", "AI 分析"),
            ("波动", "稳定性"),
            ("模型输出", "后处理链路", "每个阶段输出"),
        ),
        evidence_keywords=("陈涛，你负责排查AI分析结果波动原因", "重点看模型输出和后处理链路"),
        entity_keywords=("陈涛", "AI分析", "后处理"),
    ),
    AnalysisTarget(
        key="action_golden_dataset",
        label="Action: 跑 Golden Dataset 看每阶段输出",
        dimension="Action",
        expectation="present",
        keywords=("跑一批Golden Dataset", "跑一批 Golden Dataset", "看每个阶段输出"),
        semantic_groups=(
            ("Golden Dataset",),
            ("跑", "基线报告", "稳定性测试"),
            ("每个阶段输出", "阶段输出"),
        ),
        evidence_keywords=("我今天先跑一批Golden Dataset", "看每个阶段输出"),
        entity_keywords=("陈涛", "Golden Dataset"),
    ),
    AnalysisTarget(
        key="action_real_samples",
        label="Action: 补充真实会议测试样本",
        dimension="Action",
        expectation="present",
        keywords=("补充真实会议测试样本", "整理5个典型场景"),
        semantic_groups=(
            ("补充", "准备", "整理"),
            ("真实会议", "真实会议场景"),
            ("测试样本", "典型场景"),
        ),
        evidence_keywords=("赵敏，你补充真实会议测试样本", "我整理5个典型场景"),
        entity_keywords=("赵敏", "真实会议"),
    ),
    AnalysisTarget(
        key="action_recording_test",
        label="Action: 下午安排录音流程测试",
        dimension="Action",
        expectation="present",
        keywords=("下午安排录音流程测试", "录音流程测试"),
        semantic_groups=(
            ("录音流程", "录音页面"),
            ("测试", "验证"),
            ("下午", "安排"),
        ),
        evidence_keywords=("下午安排录音流程测试", "什么时候可以测试", "下午吧"),
        entity_keywords=("王强", "录音"),
        min_semantic_groups=3,
    ),
    AnalysisTarget(
        key="decision_ai_stability_priority",
        label="Decision: AI 稳定性最高优先级",
        dimension="Decision",
        expectation="present",
        keywords=("稳定性问题最高", "AI分析稳定性优先级最高", "AI 分析稳定性优先级最高"),
        semantic_groups=(
            ("AI分析稳定性", "AI 分析稳定性", "稳定性问题"),
            ("最高", "优先级最高", "优先解决", "当前最高优先级"),
        ),
        evidence_keywords=("稳定性问题最高", "AI分析稳定性优先级最高", "先把六维输出稳定"),
        entity_keywords=("AI分析", "稳定性", "优先级"),
    ),
    AnalysisTarget(
        key="decision_title_optimization_hold",
        label="Decision: 标题优化先放",
        dimension="Decision",
        expectation="present",
        keywords=("标题那些优化先放", "标题优化先放"),
        semantic_groups=(
            ("标题", "标题优化"),
            ("先放", "放一下", "暂缓", "延后"),
        ),
        evidence_keywords=("标题那些优化先放一下", "标题优化先放"),
        entity_keywords=("标题",),
    ),
    AnalysisTarget(
        key="decision_performance_after_stable",
        label="Decision: 性能优化等版本稳定后再看",
        dimension="Decision",
        expectation="present",
        keywords=("性能优化先不要急", "等版本稳定以后再看"),
        semantic_groups=(
            ("性能优化", "性能验证", "长会议详情页性能"),
            ("先不要急", "版本稳定", "以后再看", "暂缓"),
        ),
        evidence_keywords=("性能优化先不要急", "等版本稳定以后再看"),
        entity_keywords=("性能", "版本稳定"),
    ),
    AnalysisTarget(
        key="unresolved_proposal_decision_boundary",
        label="Unresolved: proposal 和 decision 区分问题技术评估",
        dimension="Unresolved",
        expectation="present",
        keywords=("proposal和decision区分问题", "proposal 和 decision 区分问题", "需要技术评估"),
        semantic_groups=(
            ("proposal",),
            ("decision",),
            ("区分", "边界"),
            ("技术评估", "评估"),
        ),
        evidence_keywords=("proposal 和 decision 区分问题，需要技术评估", "这个先记录"),
        entity_keywords=("proposal", "decision"),
        min_semantic_groups=3,
    ),
    AnalysisTarget(
        key="unresolved_recording_test_time",
        label="Unresolved: 录音流程测试时间确认",
        dimension="Unresolved",
        expectation="present",
        keywords=("什么时候可以测试", "下午吧"),
        semantic_groups=(
            ("录音流程", "录音页面"),
            ("什么时候", "测试时间"),
            ("下午",),
        ),
        evidence_keywords=("什么时候可以测试", "下午吧"),
        entity_keywords=("王强", "录音"),
    ),
    AnalysisTarget(
        key="risk_model_resource",
        label="Risk: 生产环境模型资源压力",
        dimension="Risk",
        expectation="present",
        keywords=("服务器压力可能会比较明显", "还没有做压测", "云GPU"),
        semantic_groups=(
            ("服务器压力", "模型资源", "资源风险"),
            ("用户量", "生产环境", "压测", "云GPU"),
            ("风险", "不能完全保证", "提前关注"),
        ),
        evidence_keywords=("服务器压力可能会比较明显", "还没有做压测", "云GPU", "生产环境模型资源风险提前关注"),
        entity_keywords=("服务器", "云GPU", "14B"),
    ),
    AnalysisTarget(
        key="risk_long_meeting_latency",
        label="Risk: 长会议生成时间较久",
        dimension="Risk",
        expectation="present",
        keywords=("长会议现在生成时间可能比较久", "几分钟内看到结果"),
        semantic_groups=(
            ("长会议",),
            ("生成时间", "生成时长", "耗时"),
            ("用户体验", "几分钟内看到结果", "快速看到结果", "客户希望"),
        ),
        evidence_keywords=("长会议现在生成时间可能比较久", "几分钟内看到结果", "用户体验风险"),
        entity_keywords=("长会议", "用户体验"),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a first-loss diagnostic report for the formal six-dimension analysis chain.",
    )
    parser.add_argument(
        "--input-file",
        default=str(DEFAULT_INPUT_FILE),
        help="Text meeting fixture to analyze.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for generated first-loss artifacts.",
    )
    parser.add_argument("--run-id", default=None, help="Override output run id.")
    parser.add_argument("--model", default=None, help="Override OLLAMA_MODEL.")
    parser.add_argument("--top-k", type=int, default=None, help="Override RAG top_k.")
    parser.add_argument(
        "--reuse-run",
        default=None,
        help="Regenerate first-loss report from an existing run directory without rerunning RAG or Qwen.",
    )
    parser.add_argument(
        "--final-meeting-id",
        default=None,
        help="When used with --reuse-run, read persisted DB summary/action rows for this meeting as the Final layer.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def build_transcript_segments(parsed: ParsedMeetingText) -> list[dict[str, Any]]:
    speaker_labels: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for index, utterance in enumerate(parsed.utterances):
        speaker_label = speaker_labels.setdefault(
            utterance.speaker,
            f"Speaker {len(speaker_labels) + 1}",
        )
        start_time, end_time = segment_times(index, utterance.text)
        segment_id = f"seg-{index + 1}"
        rows.append(
            {
                "id": segment_id,
                "segment_id": segment_id,
                "segment_index": index,
                "speaker_name": utterance.speaker,
                "speaker_label": speaker_label,
                "start_time": start_time,
                "end_time": end_time,
                "text": utterance.text,
            }
        )
    return rows


def compact_text(value: object) -> str:
    text = str(value or "").lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def stage_bool_text(value: bool) -> str:
    return "yes" if value else "no"


def item_text(item: Any) -> str:
    if isinstance(item, dict):
        parts = [
            item.get("text"),
            item.get("task"),
            item.get("conclusion"),
            item.get("issue"),
            item.get("risk"),
            item.get("impact"),
            item.get("focus_area"),
            item.get("reason"),
            item.get("blocker"),
            item.get("source_text"),
            item.get("source"),
            item.get("note"),
        ]
        return " ".join(str(part or "") for part in parts)
    return str(item or "")


def item_primary_text(item: Any) -> str:
    if isinstance(item, dict):
        parts = [
            item.get("text"),
            item.get("task"),
            item.get("conclusion"),
            item.get("issue"),
            item.get("risk"),
            item.get("impact"),
            item.get("focus_area"),
            item.get("reason"),
            item.get("blocker"),
        ]
        return " ".join(str(part or "") for part in parts)
    return str(item or "")


def item_source_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("source_text") or item.get("source") or item.get("note") or "")
    return ""


def item_segment_ids(item: Any) -> set[str]:
    if not isinstance(item, dict):
        return set()
    raw_value = item.get("source_segment_id") or item.get("segment_id") or item.get("id")
    return {
        part.strip()
        for part in str(raw_value or "").split(",")
        if part.strip()
    }


def model_items(model: Any, field: str) -> list[dict[str, Any]]:
    if isinstance(model, dict):
        return dict_items(model, field)
    items = getattr(model, field, []) or []
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in items
        if hasattr(item, "model_dump") or isinstance(item, dict)
    ]


def dict_items(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    items = payload.get(field)
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(dict(item))
        elif isinstance(item, str):
            normalized.append({"text": item})
    return normalized


def matched_semantic_groups(text: str, target: AnalysisTarget) -> list[list[str]]:
    normalized = compact_text(text)
    groups: list[list[str]] = []
    for group in target.semantic_groups:
        hits = [term for term in group if compact_text(term) and compact_text(term) in normalized]
        if hits:
            groups.append(hits)
    return groups


def match_item(
    item: Any,
    target: AnalysisTarget,
    *,
    evidence_segment_ids: set[str] | None = None,
) -> dict[str, Any]:
    text = item_text(item)
    primary_text = item_primary_text(item)
    source_text = item_source_text(item)
    normalized = compact_text(text)
    primary_normalized = compact_text(primary_text)
    source_normalized = compact_text(source_text)
    exact_keywords = [
        str(keyword)
        for keyword in target.keywords
        if len(compact_text(keyword)) >= 8
    ]
    normalized_keywords = [compact_text(keyword) for keyword in exact_keywords]
    evidence_terms = [
        compact_text(keyword)
        for keyword in (target.evidence_keywords or target.keywords)
        if keyword
    ]
    entity_terms = [compact_text(keyword) for keyword in target.entity_keywords if keyword]

    exact_match = any(keyword and keyword in primary_text for keyword in exact_keywords)
    normalized_match = any(keyword and keyword in primary_normalized for keyword in normalized_keywords)
    evidence_keyword_match = any(
        keyword and (keyword in source_normalized or keyword in normalized)
        for keyword in evidence_terms
    )
    segment_match = bool((evidence_segment_ids or set()) & item_segment_ids(item))
    evidence_match = evidence_keyword_match or segment_match

    group_hits = matched_semantic_groups(text, target)
    entity_hits = [term for term in entity_terms if term and term in normalized]
    semantic_equivalent_match = (
        len(group_hits) >= target.min_semantic_groups
        or (len(group_hits) >= max(1, target.min_semantic_groups - 1) and bool(entity_hits))
    )

    confidence = 0.0
    if exact_match:
        confidence = max(confidence, 1.0)
    if normalized_match:
        confidence = max(confidence, 0.92)
    if evidence_match:
        confidence = max(confidence, 0.86)
    if semantic_equivalent_match:
        confidence = max(confidence, 0.78 + min(0.12, len(group_hits) * 0.03))

    matched = confidence >= 0.74
    return {
        "matched": matched,
        "exact_match": exact_match,
        "normalized_match": normalized_match,
        "evidence_match": evidence_match,
        "semantic_equivalent_match": semantic_equivalent_match,
        "match_confidence": round(confidence, 3),
        "matched_semantic_groups": group_hits,
        "matched_entity_terms": entity_hits,
        "matched_item": item if isinstance(item, dict) else {"text": str(item or "")},
    }


def match_collection(
    items: Iterable[Any],
    target: AnalysisTarget,
    *,
    evidence_segment_ids: set[str] | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for item in items:
        result = match_item(
            item,
            target,
            evidence_segment_ids=evidence_segment_ids,
        )
        if best is None or result["match_confidence"] > best["match_confidence"]:
            best = result
        if result["matched"]:
            matches.append(result)
        if len(matches) >= limit:
            break

    if best is None:
        best = {
            "matched": False,
            "exact_match": False,
            "normalized_match": False,
            "evidence_match": False,
            "semantic_equivalent_match": False,
            "match_confidence": 0.0,
            "matched_semantic_groups": [],
            "matched_entity_terms": [],
            "matched_item": None,
        }

    return {
        "matched": bool(matches),
        "exact_match": any(match["exact_match"] for match in matches),
        "normalized_match": any(match["normalized_match"] for match in matches),
        "evidence_match": any(match["evidence_match"] for match in matches),
        "semantic_equivalent_match": any(match["semantic_equivalent_match"] for match in matches),
        "match_confidence": max((match["match_confidence"] for match in matches), default=best["match_confidence"]),
        "matches": matches,
        "best_candidate": best,
    }


def contains_target(
    items: Iterable[Any],
    target: AnalysisTarget,
    *,
    evidence_segment_ids: set[str] | None = None,
) -> bool:
    return match_collection(
        items,
        target,
        evidence_segment_ids=evidence_segment_ids,
    )["matched"]


def find_matching_items(
    items: Iterable[Any],
    target: AnalysisTarget,
    *,
    evidence_segment_ids: set[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    return [
        match["matched_item"]
        for match in match_collection(
            items,
            target,
            evidence_segment_ids=evidence_segment_ids,
            limit=limit,
        )["matches"]
        if isinstance(match.get("matched_item"), dict)
    ]


def find_transcript_evidence(transcript_rows: list[dict[str, Any]], keywords: Iterable[str]) -> list[dict[str, Any]]:
    normalized_keywords = [compact_text(keyword) for keyword in keywords if keyword]
    evidence: list[dict[str, Any]] = []
    for row in transcript_rows:
        normalized = compact_text(row.get("text"))
        if any(keyword in normalized for keyword in normalized_keywords):
            evidence.append(row)
    return evidence


def load_trace_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else []
    return [dict(item) for item in items if isinstance(item, dict)]


def semantic_stage_items(trace_dir: Path, field: str) -> list[dict[str, Any]]:
    if field == "action_items":
        return _semantic_action_candidates_from_trace(trace_dir)
    if field == "key_conclusions":
        return _semantic_decision_candidates_from_trace(trace_dir)
    if field == "unresolved_issues":
        return _semantic_unresolved_candidates_from_trace(trace_dir)
    if field == "risks_and_focus":
        result_path = trace_dir / "07_final_meeting_analysis.json"
        if not result_path.exists():
            return []
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
        risks = analysis.get("risks_and_focus") if isinstance(analysis, dict) else []
        return [dict(item) for item in risks if isinstance(item, dict)]
    return []


def target_dimension_trace(rag_trace: dict[str, Any], field: str) -> dict[str, Any]:
    dimension_traces = rag_trace.get("dimension_traces")
    if isinstance(dimension_traces, dict):
        value = dimension_traces.get(field)
        return dict(value) if isinstance(value, dict) else {}
    return rag_trace


def summarize_rag_trace(trace: dict[str, Any]) -> dict[str, Any]:
    candidates = trace.get("candidate_chunks")
    selected = trace.get("final_selected_chunks")
    return {
        "query": trace.get("query"),
        "target_dimension": trace.get("target_dimension"),
        "meeting_scenario": trace.get("meeting_scenario"),
        "retrieved_chunk_ids": trace.get("retrieved_chunk_ids")
        or trace.get("final_selected_chunk_ids")
        or [],
        "candidate_chunks": candidates if isinstance(candidates, list) else [],
        "final_selected_chunks": selected if isinstance(selected, list) else [],
        "fallback_reason": trace.get("fallback_reason"),
    }


def audit_matches(audit: list[dict[str, Any]], field: str, keywords: Iterable[str]) -> list[dict[str, Any]]:
    normalized_keywords = [compact_text(keyword) for keyword in keywords if keyword]
    result: list[dict[str, Any]] = []
    for event in audit:
        if str(event.get("field") or "") != field:
            continue
        text = compact_text(
            " ".join(
                [
                    str(event.get("before") or ""),
                    str(event.get("after") or ""),
                    str(event.get("reason") or ""),
                ]
            )
        )
        if any(keyword in text for keyword in normalized_keywords):
            result.append(event)
    return result


def action_fusion_matches(audit: list[dict[str, Any]], keywords: Iterable[str]) -> list[dict[str, Any]]:
    normalized_keywords = [compact_text(keyword) for keyword in keywords if keyword]
    result: list[dict[str, Any]] = []
    for event in audit:
        text = compact_text(json.dumps(event, ensure_ascii=False, default=str))
        if any(keyword in text for keyword in normalized_keywords):
            result.append(event)
    return result


ACTION_FP_TARGETS = [
    AnalysisTarget(
        key="action_fp_quoted_example_followup",
        label="Action FP: quoted example follow-up reminder",
        dimension="Action",
        expectation="absent",
        keywords=("负责人跟进这个事情", "只是提醒一下"),
        semantic_groups=(("负责人", "跟进"), ("提醒", "只是提醒"), ("这个事情",)),
        evidence_keywords=("负责人跟进这个事情", "只是提醒一下"),
        entity_keywords=("负责人",),
        min_semantic_groups=2,
    ),
    AnalysisTarget(
        key="action_fp_frontend_progress_update",
        label="Action FP: frontend progress update",
        dimension="Action",
        expectation="absent",
        keywords=("我同步一下前端", "录音页面现在基本完成", "二次确认", "处理中"),
        semantic_groups=(("前端", "录音页面"), ("基本完成", "同步"), ("二次确认", "处理中")),
        evidence_keywords=("我同步一下前端", "录音页面现在基本完成", "二次确认", "处理中"),
        entity_keywords=("王强", "前端"),
        min_semantic_groups=2,
    ),
]


def qwen_raw_action_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return dict_items(payload, "action_items")
    if isinstance(payload, list):
        return [{"text": str(item)} if not isinstance(item, dict) else dict(item) for item in payload]
    return []


def action_layer_match(
    layer: str,
    items: Iterable[Any],
    target: AnalysisTarget,
    *,
    evidence_segment_ids: set[str] | None = None,
    source_path: str | None = None,
    default_reason: str | None = None,
) -> dict[str, Any]:
    match = match_collection(items, target, evidence_segment_ids=evidence_segment_ids, limit=20)
    matches = match.get("matches") if isinstance(match.get("matches"), list) else []
    enriched_matches: list[dict[str, Any]] = []
    for match_row in matches:
        item = match_row.get("matched_item") if isinstance(match_row, dict) else None
        if not isinstance(item, dict):
            enriched_matches.append({"text": str(item or "")})
            continue
        reason = (
            item.get("suppression_reason")
            or item.get("keep_remove_reason")
            or item.get("reason")
            or item.get("primary_intent")
            or item.get("status")
            or default_reason
        )
        enriched_matches.append(
            {
                "candidate_id": item.get("candidate_id") or item.get("event_id") or item.get("id"),
                "source_path": item.get("source_type") or source_path,
                "task": item.get("task") or item.get("text"),
                "source_text": item.get("source_text") or item.get("source"),
                "source_segment_id": item.get("source_segment_id") or item.get("segment_id") or item.get("id"),
                "keep_remove_reason": reason,
                "raw": item,
            }
        )
    return {
        "layer": layer,
        "exists": bool(match.get("matched")),
        "match": {
            "exact_match": bool(match.get("exact_match")),
            "normalized_match": bool(match.get("normalized_match")),
            "evidence_match": bool(match.get("evidence_match")),
            "semantic_equivalent_match": bool(match.get("semantic_equivalent_match")),
            "match_confidence": match.get("match_confidence", 0.0),
        },
        "matches": enriched_matches,
        "best_candidate": match.get("best_candidate"),
    }


def enrich_action_fusion_audit(
    audit: list[dict[str, Any]],
    *,
    semantic_candidates: list[dict[str, Any]],
    legacy_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(semantic_candidates):
        by_id[f"semantic:{index}"] = item
    for index, item in enumerate(legacy_items):
        by_id[f"legacy:{index}"] = item

    enriched: list[dict[str, Any]] = []
    for event in audit:
        row = dict(event)
        source = by_id.get(str(row.get("candidate_id") or ""))
        if source:
            row.setdefault("source_text", source.get("source_text") or source.get("source"))
            row.setdefault("source_segment_id", source.get("source_segment_id"))
            row.setdefault("confidence", source.get("confidence"))
        row["keep_remove_reason"] = row.get("suppression_reason") or (
            "ranked_survivor" if row.get("final_survivor") else "not_final_survivor"
        )
        enriched.append(row)
    return enriched


def matching_audit_reasons(
    audit: list[dict[str, Any]],
    target: AnalysisTarget,
    field: str,
) -> list[dict[str, Any]]:
    return audit_matches(audit, field, target.evidence_keywords or target.keywords)


def resolve_action_source(
    item: dict[str, Any],
    *,
    action_fusion_audit: list[dict[str, Any]],
    semantic_candidates: list[dict[str, Any]],
    qwen_items: list[dict[str, Any]],
    legacy_items: list[dict[str, Any]],
) -> dict[str, Any]:
    text = str(item.get("task") or item.get("text") or "")
    item_target = AnalysisTarget(
        key="final_action",
        label="Final action",
        dimension="Action",
        expectation="present",
        keywords=(text,),
        semantic_groups=((text,),),
        evidence_keywords=(str(item.get("source_text") or ""),),
        min_semantic_groups=1,
    )
    for event in action_fusion_audit:
        if match_item(event, item_target).get("matched"):
            return {
                "source_path": event.get("source_type"),
                "candidate_id": event.get("candidate_id"),
                "duplicate_group": event.get("duplicate_group"),
                "fusion_reason": event.get("keep_remove_reason") or event.get("suppression_reason"),
            }
    for source_path, candidates in [
        ("semantic", semantic_candidates),
        ("qwen", qwen_items),
        ("legacy", legacy_items),
    ]:
        if match_collection(candidates, item_target, limit=1).get("matched"):
            return {
                "source_path": source_path,
                "candidate_id": None,
                "duplicate_group": None,
                "fusion_reason": "matched_without_fusion_audit_event",
            }
    return {
        "source_path": "unknown",
        "candidate_id": None,
        "duplicate_group": None,
        "fusion_reason": "no_matching_source_trace",
    }


def build_action_fp_production_trace(
    *,
    transcript_rows: list[dict[str, Any]],
    semantic_trace_dir: Path,
    rag_trace: dict[str, Any],
    qwen_raw_parsed: Any,
    normalized_before_fusion: Any,
    action_fused: Any,
    evidence_resolved: Any,
    postprocessed: Any,
    validated_result: dict[str, Any],
    final_result: dict[str, Any] | None,
    action_fusion_audit: list[dict[str, Any]],
    postprocessor_audit: list[dict[str, Any]],
    validator_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    semantic_raw_events = load_trace_items(semantic_trace_dir / "02_semantic_events_raw.json")
    semantic_action_candidates = _semantic_action_candidates_from_trace(semantic_trace_dir)
    qwen_items = qwen_raw_action_items(qwen_raw_parsed)
    legacy_items = model_items(normalized_before_fusion, "action_items")
    fusion_items = model_items(action_fused, "action_items")
    evidence_items = model_items(evidence_resolved, "action_items")
    postprocessor_items = model_items(postprocessed, "action_items")
    validator_items = model_items(validated_result, "action_items")
    final_items = model_items(final_result or validated_result, "action_items")
    enriched_fusion_audit = enrich_action_fusion_audit(
        action_fusion_audit,
        semantic_candidates=semantic_action_candidates,
        legacy_items=legacy_items,
    )
    rag_action_trace = summarize_rag_trace(target_dimension_trace(rag_trace, "action_items"))

    target_traces: list[dict[str, Any]] = []
    output_layers = [
        "Semantic raw events",
        "Semantic action candidates",
        "Qwen raw action_items",
        "legacy action_items",
        "ranking/dedup",
        "fusion",
        "evidence",
        "postprocessor",
        "validator",
        "final",
    ]
    for target in ACTION_FP_TARGETS:
        transcript_evidence = find_transcript_evidence(transcript_rows, target.evidence_keywords or target.keywords)
        evidence_segment_ids = {str(row.get("id")) for row in transcript_evidence if row.get("id")}
        layer_entries = [
            action_layer_match("Transcript", transcript_evidence, target, source_path="transcript", default_reason="evidence_only"),
            action_layer_match("Semantic raw events", semantic_raw_events, target, evidence_segment_ids=evidence_segment_ids, source_path="semantic", default_reason="semantic_raw_event"),
            action_layer_match("Semantic action candidates", semantic_action_candidates, target, evidence_segment_ids=evidence_segment_ids, source_path="semantic", default_reason="semantic_action_candidate"),
            action_layer_match("RAG context", rag_action_trace.get("final_selected_chunks") or rag_action_trace.get("candidate_chunks") or [], target, source_path="rag", default_reason="retrieved_context"),
            action_layer_match("Qwen raw action_items", qwen_items, target, evidence_segment_ids=evidence_segment_ids, source_path="qwen", default_reason="qwen_raw"),
            action_layer_match("legacy action_items", legacy_items, target, evidence_segment_ids=evidence_segment_ids, source_path="legacy", default_reason="legacy_normalized"),
            action_layer_match("ranking/dedup", enriched_fusion_audit, target, evidence_segment_ids=evidence_segment_ids, default_reason="ranking_dedup"),
            action_layer_match("fusion", fusion_items, target, evidence_segment_ids=evidence_segment_ids, source_path="fusion", default_reason="fusion_output"),
            action_layer_match("evidence", evidence_items, target, evidence_segment_ids=evidence_segment_ids, source_path="evidence", default_reason="evidence_output"),
            action_layer_match("postprocessor", postprocessor_items, target, evidence_segment_ids=evidence_segment_ids, source_path="postprocessor", default_reason="postprocessor_output"),
            action_layer_match("validator", validator_items, target, evidence_segment_ids=evidence_segment_ids, source_path="validator", default_reason="validator_output"),
            action_layer_match("final", final_items, target, evidence_segment_ids=evidence_segment_ids, source_path="final", default_reason="persisted_final"),
        ]
        layer_by_name = {entry["layer"]: entry for entry in layer_entries}
        first_output_layer = next(
            (name for name in output_layers if layer_by_name.get(name, {}).get("exists")),
            "none",
        )
        fusion_removed = [
            match
            for match in layer_by_name["ranking/dedup"].get("matches", [])
            if isinstance(match, dict)
            and match.get("keep_remove_reason") not in {None, "ranked_survivor"}
        ]
        postprocessor_removed = [
            event
            for event in matching_audit_reasons(postprocessor_audit, target, "action_items")
            if event.get("action") == "remove"
        ]
        validator_removed = [
            event
            for event in matching_audit_reasons(validator_audit, target, "action_items")
            if event.get("action") == "remove"
        ]
        removal_layer = None
        if fusion_removed:
            removal_layer = "ranking/dedup"
        elif postprocessor_removed:
            removal_layer = "postprocessor"
        elif validator_removed:
            removal_layer = "validator"
        reappeared_after_removal = bool(removal_layer and layer_by_name["final"]["exists"])
        reappeared_layer = "final" if reappeared_after_removal else None
        absent_parallel_layers = [
            name
            for name in ["RAG context", "Qwen raw action_items", "legacy action_items"]
            if not layer_by_name.get(name, {}).get("exists")
        ]

        target_traces.append(
            {
                "target": target.key,
                "label": target.label,
                "transcript_evidence": transcript_evidence,
                "first_output_layer": first_output_layer,
                "semantic_raw_exists": bool(layer_by_name["Semantic raw events"]["exists"]),
                "semantic_action_candidate_exists": bool(layer_by_name["Semantic action candidates"]["exists"]),
                "reappeared_after_removal": reappeared_after_removal,
                "removal_layer": removal_layer,
                "reappeared_layer": reappeared_layer,
                "absent_parallel_layers": absent_parallel_layers,
                "postprocessor_audit": matching_audit_reasons(postprocessor_audit, target, "action_items"),
                "validator_audit": matching_audit_reasons(validator_audit, target, "action_items"),
                "layers": layer_entries,
            }
        )

    final_action_sources = []
    for index, item in enumerate(final_items, start=1):
        source = resolve_action_source(
            item,
            action_fusion_audit=enriched_fusion_audit,
            semantic_candidates=semantic_action_candidates,
            qwen_items=qwen_items,
            legacy_items=legacy_items,
        )
        final_action_sources.append(
            {
                "index": index,
                "task": item.get("task") or item.get("text"),
                "source_text": item.get("source_text"),
                **source,
            }
        )

    return {
        "rag_action_trace": rag_action_trace,
        "targets": target_traces,
        "final_action_sources": final_action_sources,
        "answers": {
            "semantic_candidate_presence": {
                target["target"]: target["semantic_action_candidate_exists"]
                for target in target_traces
            },
            "reintroduced_by": {
                target["target"]: (
                    target["first_output_layer"]
                    if not target["semantic_action_candidate_exists"]
                    and target["first_output_layer"] not in {"none", "Semantic raw events"}
                    else None
                )
                for target in target_traces
            },
            "semantic_fix_coverage": {
                target["target"]: (
                    "still_present_in_semantic_candidate"
                    if target["semantic_action_candidate_exists"]
                    else "not_present_in_semantic_candidate"
                )
                for target in target_traces
            },
        },
    }


def determine_first_loss(
    expectation: str,
    presence: dict[str, bool],
    stage_matches: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, str]:
    if expectation == "absent":
        for stage in [
            "Semantic",
            "Qwen",
            "Fusion",
            "Evidence",
            "PostProcessor",
            "Validator",
            "Final",
        ]:
            if presence.get(stage):
                return stage, f"false_positive_introduced_at_{stage}"
        return "none", "absent_across_pipeline"

    if presence.get("Final"):
        final_match = (stage_matches or {}).get("Final") or {}
        if (
            final_match.get("semantic_equivalent_match")
            or final_match.get("evidence_match")
        ) and not final_match.get("exact_match"):
            return "none", "survived_to_final/paraphrased"
        return "none", "survived_to_final"

    previous_present = False
    for stage in STAGE_ORDER:
        current_present = bool(presence.get(stage))
        if current_present:
            previous_present = True
            continue
        if previous_present:
            return stage, f"present_before_{stage}_then_missing"
    return "Transcript", "expected_evidence_not_found_or_not_recalled"


def build_target_diagnosis(
    target: AnalysisTarget,
    *,
    transcript_rows: list[dict[str, Any]],
    semantic_trace_dir: Path,
    rag_trace: dict[str, Any],
    qwen_raw_parsed: dict[str, Any],
    normalized_before_fusion: Any,
    action_fused: Any,
    decision_fused: Any,
    unresolved_fused: Any,
    evidence_resolved: Any,
    postprocessed: Any,
    validated_result: dict[str, Any],
    action_fusion_audit: list[dict[str, Any]],
    postprocessor_audit: list[dict[str, Any]],
    validator_audit: list[dict[str, Any]],
    final_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field = DIMENSION_FIELDS[target.dimension]
    semantic_items = semantic_stage_items(semantic_trace_dir, field)
    qwen_items = dict_items(qwen_raw_parsed, field)

    if field == "action_items":
        fusion_items = model_items(action_fused, field)
    elif field == "key_conclusions":
        fusion_items = model_items(decision_fused, field)
    elif field == "unresolved_issues":
        fusion_items = model_items(unresolved_fused, field)
    else:
        fusion_items = model_items(normalized_before_fusion, field)

    evidence_items = model_items(evidence_resolved, field)
    postprocessor_items = model_items(postprocessed, field)
    validator_items = dict_items(validated_result, field)
    resolved_final_result = final_result or validated_result
    final_items = dict_items(resolved_final_result, field)
    transcript_evidence = find_transcript_evidence(
        transcript_rows,
        target.evidence_keywords or target.keywords,
    )
    evidence_segment_ids = {
        str(row.get("segment_id") or row.get("id"))
        for row in transcript_evidence
        if row.get("segment_id") or row.get("id")
    }
    stage_matches = {
        "Transcript": match_collection(transcript_evidence, target),
        "Semantic": match_collection(
            semantic_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "Qwen": match_collection(
            qwen_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "Fusion": match_collection(
            fusion_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "Evidence": match_collection(
            evidence_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "PostProcessor": match_collection(
            postprocessor_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "Validator": match_collection(
            validator_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "Final": match_collection(
            final_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
    }

    presence = {
        "Transcript": bool(transcript_evidence),
        "Semantic": stage_matches["Semantic"]["matched"],
        "RAG": bool(summarize_rag_trace(target_dimension_trace(rag_trace, field)).get("final_selected_chunks")),
        "Qwen": stage_matches["Qwen"]["matched"],
        "Fusion": stage_matches["Fusion"]["matched"],
        "Evidence": stage_matches["Evidence"]["matched"],
        "PostProcessor": stage_matches["PostProcessor"]["matched"],
        "Validator": stage_matches["Validator"]["matched"],
        "Final": stage_matches["Final"]["matched"],
    }
    first_layer, first_reason = determine_first_loss(
        target.expectation,
        presence,
        stage_matches,
    )
    display_match = (
        stage_matches["Final"]
        if stage_matches["Final"]["matched"]
        else max(
            stage_matches.values(),
            key=lambda match: float(match.get("match_confidence") or 0.0),
        )
    )

    return {
        "target": target.key,
        "label": target.label,
        "dimension": target.dimension,
        "expectation": target.expectation,
        "notes": target.notes,
        "presence": presence,
        "match": {
            "exact_match": display_match["exact_match"],
            "normalized_match": display_match["normalized_match"],
            "evidence_match": display_match["evidence_match"],
            "semantic_equivalent_match": display_match["semantic_equivalent_match"],
            "match_confidence": display_match["match_confidence"],
        },
        "stage_matches": {
            stage: {
                "matched": match["matched"],
                "exact_match": match["exact_match"],
                "normalized_match": match["normalized_match"],
                "evidence_match": match["evidence_match"],
                "semantic_equivalent_match": match["semantic_equivalent_match"],
                "match_confidence": match["match_confidence"],
            }
            for stage, match in stage_matches.items()
        },
        "transcript_evidence": transcript_evidence,
        "semantic_candidates": find_matching_items(
            semantic_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "rag": summarize_rag_trace(target_dimension_trace(rag_trace, field)),
        "qwen_raw_candidates": find_matching_items(
            qwen_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "fusion_result": find_matching_items(
            fusion_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "evidence_result": find_matching_items(
            evidence_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "postprocessor_result": find_matching_items(
            postprocessor_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "postprocessor_audit": audit_matches(
            postprocessor_audit,
            field,
            target.evidence_keywords or target.keywords,
        ),
        "validator_result": find_matching_items(
            validator_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "validator_audit": audit_matches(
            validator_audit,
            field,
            target.evidence_keywords or target.keywords,
        ),
        "action_fusion_audit": action_fusion_matches(
            action_fusion_audit,
            target.evidence_keywords or target.keywords,
        )
        if field == "action_items"
        else [],
        "final_result": find_matching_items(
            final_items,
            target,
            evidence_segment_ids=evidence_segment_ids,
        ),
        "first_loss_layer": first_layer,
        "first_loss_reason": first_reason,
    }


def run_formal_pipeline(
    *,
    transcript_text: str,
    transcript_segments: list[dict[str, Any]],
    semantic_action_candidates: list[dict[str, Any]],
    semantic_decision_candidates: list[dict[str, Any]],
    semantic_unresolved_candidates: list[dict[str, Any]],
    output_dir: Path,
    top_k: int | None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    settings = get_settings()
    resolved_top_k = top_k if top_k is not None else settings.rag_top_k
    prompt_spec = get_meeting_analyst_prompt_spec()
    service = MeetingAnalystService(llm_client=OllamaClient())

    rag_context = service._build_formal_rag_context(
        transcript=transcript_text,
        top_k=resolved_top_k,
    )
    write_json(output_dir / "rag_context.json", rag_context.__dict__)

    prompt = build_meeting_analyst_prompt(
        rag_context=rag_context.text,
        transcript=transcript_text,
    )
    (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    raw_output = service.llm_client.chat(prompt=prompt)
    (output_dir / "qwen_raw_output.txt").write_text(raw_output, encoding="utf-8")

    parsed_result = canonicalize_meeting_analysis_aliases(extract_json(raw_output))
    write_json(output_dir / "qwen_raw_parsed.json", parsed_result)

    title_fields = {
        "meeting_title": str(parsed_result.get("meeting_title") or "").strip(),
        "meeting_type": str(parsed_result.get("meeting_type") or "").strip(),
        "meeting_type_confidence": parsed_result.get("meeting_type_confidence"),
        "meeting_title_candidate": str(parsed_result.get("meeting_title_candidate") or "").strip(),
        "title_basis": parsed_result.get("title_basis")
        if isinstance(parsed_result.get("title_basis"), list)
        else [],
    }
    parsed_result["_metadata"] = {
        "prompt_id": prompt_spec.prompt_id,
        "prompt_version": prompt_spec.prompt_version,
        "schema_version": prompt_spec.schema_version,
        "rag_chunk_ids": rag_context.chunk_ids,
        "rag_dataset_version": rag_context.dataset_version,
        "rag_chunk_schema_version": rag_context.chunk_schema_version,
        "rag_collection_name": rag_context.collection_name,
        "rag_embedding_model": rag_context.embedding_model,
        "retrieved_chunk_ids": rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
        "retrieval_version": rag_context.retrieval_version,
        "scenario_taxonomy_version": rag_context.scenario_taxonomy_version,
        "rag_retrieval_strategy": rag_context.retrieval_strategy,
        "rag_retrieval_buckets": rag_context.retrieval_buckets,
        "rag_dimension_traces": rag_context.retrieval_trace.get("dimension_traces", {})
        if isinstance(rag_context.retrieval_trace, dict)
        else {},
        "rag_routed_meeting_type": rag_context.routed_meeting_type,
        "rag_routed_scenario": rag_context.routed_scenario,
        "rag_fallback_reason": rag_context.fallback_reason,
        "result_source": "legacy_qwen_rag",
    }

    normalized_before_fusion = normalize_meeting_analysis_result(
        parsed_result,
        model_name=f"{settings.ollama_model}+rag",
    )
    write_json(
        output_dir / "normalized_before_fusion.json",
        normalized_before_fusion.model_dump(mode="json"),
    )

    action_fusion_audit: list[dict[str, Any]] = []
    action_fused = fuse_action_items(
        normalized_before_fusion,
        semantic_action_candidates,
        audit=action_fusion_audit,
    )
    write_json(output_dir / "action_fused.json", action_fused.model_dump(mode="json"))
    write_json(output_dir / "action_fusion_audit.json", action_fusion_audit)

    decision_fused = fuse_key_conclusions_with_decisions(
        action_fused,
        semantic_decision_candidates,
    )
    write_json(output_dir / "decision_fused.json", decision_fused.model_dump(mode="json"))

    unresolved_fused = fuse_unresolved_issues(
        decision_fused,
        semantic_unresolved_candidates,
    )
    write_json(output_dir / "unresolved_fused.json", unresolved_fused.model_dump(mode="json"))

    evidence_resolved = resolve_meeting_analysis_evidence(
        unresolved_fused,
        transcript_text,
        transcript_segments=transcript_segments,
    )
    write_json(output_dir / "evidence_resolved.json", evidence_resolved.model_dump(mode="json"))

    postprocessor = MeetingAnalysisPostProcessor()
    postprocessed = postprocessor.process(evidence_resolved, transcript_text)
    write_json(output_dir / "postprocessed_result.json", postprocessed.model_dump(mode="json"))
    write_json(output_dir / "postprocessor_audit.json", postprocessor.last_audit)

    validator_input = postprocessed.model_dump(exclude_defaults=True)
    write_json(output_dir / "validator_input.json", validator_input)
    validated_result, validator_audit = validate_meeting_analysis_with_audit(
        validator_input,
        transcript_text,
    )
    mark_action_fusion_final_survivors(
        action_fusion_audit,
        validated_result.get("action_items", []) or [],
    )
    for key, value in title_fields.items():
        if value not in ("", [], None):
            validated_result[key] = value
    ensure_non_empty_analysis_result(validated_result)
    validated_result["_metadata"] = {
        **parsed_result["_metadata"],
        "ollama_temperature": service.llm_client.temperature,
        "ollama_top_p": service.llm_client.top_p,
        "ollama_seed": service.llm_client.seed,
        "ollama_format": service.llm_client.response_format,
        "semantic_action_candidate_count": len(semantic_action_candidates),
        "semantic_decision_candidate_count": len(semantic_decision_candidates),
        "semantic_unresolved_candidate_count": len(semantic_unresolved_candidates),
    }
    write_json(output_dir / "validated_result.json", validated_result)
    write_json(output_dir / "validator_audit.json", validator_audit)

    return {
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        "rag_context": rag_context,
        "qwen_raw_parsed": parsed_result,
        "normalized_before_fusion": normalized_before_fusion,
        "action_fused": action_fused,
        "decision_fused": decision_fused,
        "unresolved_fused": unresolved_fused,
        "evidence_resolved": evidence_resolved,
        "postprocessed": postprocessed,
        "postprocessor_audit": postprocessor.last_audit,
        "validator_audit": validator_audit,
        "validated_result": validated_result,
        "action_fusion_audit": action_fusion_audit,
    }


def render_json_snippet(value: Any, max_chars: int = 900) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def render_target_section(target: dict[str, Any]) -> list[str]:
    rag = target["rag"]
    match = target.get("match") if isinstance(target.get("match"), dict) else {}
    stage_matches = target.get("stage_matches") if isinstance(target.get("stage_matches"), dict) else {}
    selected = rag.get("final_selected_chunks") or []
    candidates = rag.get("candidate_chunks") or []
    selected_ids = [
        chunk.get("chunk_id")
        for chunk in selected
        if isinstance(chunk, dict)
    ]
    lines = [
        f"### {target['label']}",
        "",
        f"- expectation: `{target['expectation']}`",
        f"- first_loss_layer: `{target['first_loss_layer']}`",
        f"- first_loss_reason: `{target['first_loss_reason']}`",
        f"- exact_match: `{bool(match.get('exact_match', False))}`",
        f"- normalized_match: `{bool(match.get('normalized_match', False))}`",
        f"- evidence_match: `{bool(match.get('evidence_match', False))}`",
        f"- semantic_equivalent_match: `{bool(match.get('semantic_equivalent_match', False))}`",
        f"- match_confidence: `{match.get('match_confidence', 0.0)}`",
        f"- stage_presence: "
        + ", ".join(
            f"{stage}={stage_bool_text(bool(target['presence'].get(stage)))}"
            for stage in STAGE_ORDER
        ),
        f"- stage_match_matrix: `{render_json_snippet(stage_matches, 900)}`",
        f"- transcript evidence: `{render_json_snippet(target['transcript_evidence'], 500)}`",
        f"- semantic candidate/result: `{render_json_snippet(target['semantic_candidates'], 500)}`",
        f"- RAG retrieved_chunk_ids: `{selected_ids}`",
        f"- RAG scores/metadata: `{render_json_snippet(selected or candidates[:8], 900)}`",
        f"- RAG fallback_reason: `{rag.get('fallback_reason')}`",
        f"- Qwen raw candidate: `{render_json_snippet(target['qwen_raw_candidates'], 500)}`",
        f"- fusion result: `{render_json_snippet(target['fusion_result'], 500)}`",
        f"- evidence result: `{render_json_snippet(target['evidence_result'], 500)}`",
        f"- postprocessor keep/remove reason: `{render_json_snippet(target['postprocessor_audit'], 500)}`",
        f"- validator keep/remove reason: `{render_json_snippet(target['validator_audit'], 500)}`",
        f"- action fusion audit: `{render_json_snippet(target['action_fusion_audit'], 500)}`",
        f"- final result: `{render_json_snippet(target['final_result'], 500)}`",
        "",
    ]
    return lines


def render_action_fp_section(action_fp: dict[str, Any] | None) -> list[str]:
    if not isinstance(action_fp, dict):
        return []

    lines = [
        "## Action FP Production Path",
        "",
        f"- RAG action query: `{action_fp.get('rag_action_trace', {}).get('query')}`",
        f"- RAG action selected chunks: `{action_fp.get('rag_action_trace', {}).get('retrieved_chunk_ids')}`",
        f"- RAG action fallback_reason: `{action_fp.get('rag_action_trace', {}).get('fallback_reason')}`",
        "",
        "### Key Questions",
        "",
    ]
    answers = action_fp.get("answers") if isinstance(action_fp.get("answers"), dict) else {}
    lines.extend(
        [
            f"- Semantic candidate presence: `{render_json_snippet(answers.get('semantic_candidate_presence'), 700)}`",
            f"- Reintroduced by: `{render_json_snippet(answers.get('reintroduced_by'), 700)}`",
            f"- Semantic fix coverage: `{render_json_snippet(answers.get('semantic_fix_coverage'), 700)}`",
            "",
        ]
    )

    for target in action_fp.get("targets") or []:
        if not isinstance(target, dict):
            continue
        lines.extend(
            [
                f"### {target.get('label')}",
                "",
                f"- first_output_layer: `{target.get('first_output_layer')}`",
                f"- semantic_raw_exists: `{target.get('semantic_raw_exists')}`",
                f"- semantic_action_candidate_exists: `{target.get('semantic_action_candidate_exists')}`",
                f"- reappeared_after_removal: `{target.get('reappeared_after_removal')}`",
                f"- removal_layer: `{target.get('removal_layer')}`",
                f"- reappeared_layer: `{target.get('reappeared_layer')}`",
                f"- transcript evidence: `{render_json_snippet(target.get('transcript_evidence'), 700)}`",
                "",
                "| Layer | Exists | Source Path | Candidate ID | Keep/Remove Reason | Source Text |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for layer in target.get("layers") or []:
            if not isinstance(layer, dict):
                continue
            matches = layer.get("matches") if isinstance(layer.get("matches"), list) else []
            first_match = matches[0] if matches and isinstance(matches[0], dict) else {}
            source_text = str(first_match.get("source_text") or first_match.get("task") or "")
            source_text = source_text.replace("\n", " ")
            if len(source_text) > 160:
                source_text = source_text[:157] + "..."
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(layer.get("layer")),
                        stage_bool_text(bool(layer.get("exists"))),
                        str(first_match.get("source_path") or ""),
                        str(first_match.get("candidate_id") or ""),
                        str(first_match.get("keep_remove_reason") or ""),
                        source_text,
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                f"- postprocessor audit: `{render_json_snippet(target.get('postprocessor_audit'), 700)}`",
                f"- validator audit: `{render_json_snippet(target.get('validator_audit'), 700)}`",
                "",
            ]
        )

    lines.extend(
        [
            "### Final Action Sources",
            "",
            "| # | Task | Source Path | Candidate ID | Fusion Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in action_fp.get("final_action_sources") or []:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").replace("\n", " ")
        if len(task) > 140:
            task = task[:137] + "..."
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("index")),
                    task,
                    str(item.get("source_path") or ""),
                    str(item.get("candidate_id") or ""),
                    str(item.get("fusion_reason") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def render_report(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    lines = [
        "# First-Loss Analysis Report",
        "",
        "## Run Metadata",
        "",
        f"- run_id: `{metadata['run_id']}`",
        f"- generated_at: `{metadata['generated_at']}`",
        f"- input_file: `{metadata['input_file']}`",
        f"- meeting_id: `{metadata['meeting_id']}`",
        f"- rag_collection_name: `{metadata.get('rag_collection_name')}`",
        f"- rag_dataset_version: `{metadata.get('rag_dataset_version')}`",
        f"- retrieval_version: `{metadata.get('retrieval_version')}`",
        f"- scenario_taxonomy_version: `{metadata.get('scenario_taxonomy_version')}`",
        f"- output_dir: `{metadata['output_dir']}`",
        "",
        "## Layer Funnel",
        "",
        "Transcript -> Semantic Candidate -> Dimension RAG Retrieval -> Qwen Raw Output -> Fusion -> Evidence -> PostProcessor -> Validator -> Final",
        "",
        "## Targets",
        "",
    ]
    for target in payload["targets"]:
        lines.extend(render_target_section(target))

    lines.extend(render_action_fp_section(payload.get("action_fp_production_trace")))

    lines.extend(
        [
            "## Summary",
            "",
            "| 目标 | Semantic | RAG | Qwen | Fusion | PostProcessor | Validator | Final | First Loss |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for target in payload["targets"]:
        presence = target["presence"]
        lines.append(
            "| "
            + " | ".join(
                [
                    target["label"],
                    stage_bool_text(presence.get("Semantic", False)),
                    stage_bool_text(presence.get("RAG", False)),
                    stage_bool_text(presence.get("Qwen", False)),
                    stage_bool_text(presence.get("Fusion", False)),
                    stage_bool_text(presence.get("PostProcessor", False)),
                    stage_bool_text(presence.get("Validator", False)),
                    stage_bool_text(presence.get("Final", False)),
                    f"{target['first_loss_layer']}: {target['first_loss_reason']}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This report is diagnostic only. It does not modify RAG chunks, Prompt, Top-K, Semantic, Fusion, Evidence, PostProcessor, Validator, or database schema.",
            "- Decision/Unresolved fusion currently has no native audit stream, so first-loss for those stages is inferred from before/after item presence.",
            "- RAG presence indicates dimension-aware retrieval executed and returned selected chunks for the target dimension; it does not imply a chunk explicitly mentions the target evidence phrase.",
        ]
    )
    return "\n".join(lines)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_semantic_trace_dir(output_dir: Path, metadata: dict[str, Any] | None = None) -> Path:
    if metadata:
        trace_dir = metadata.get("semantic_trace_dir")
        if trace_dir and Path(trace_dir).exists():
            return Path(trace_dir)
    trace_root = output_dir / "semantic_pipeline_trace"
    candidates = [path for path in trace_root.glob("*") if path.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No semantic trace directory found under {trace_root}")
    return sorted(candidates)[-1]


def load_persisted_final_result(meeting_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import ActionItem, MeetingSummary

    db = SessionLocal()
    try:
        summary = db.scalar(
            select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)
        )
        if summary is None:
            raise RuntimeError(f"MeetingSummary not found for meeting_id={meeting_id}")
        actions = list(
            db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id)).all()
        )
        return {
            "meeting_summary": summary.meeting_summary,
            "meeting_agenda": summary.meeting_agenda or [],
            "key_conclusions": summary.key_conclusions or [],
            "action_items": [
                {
                    "task": action.task,
                    "owner_name": action.owner_name,
                    "deadline": action.deadline,
                    "status": action.status,
                    "source_text": action.source_text,
                    "source_segment_id": action.source_segment_id,
                    "confidence": action.confidence,
                }
                for action in actions
            ],
            "unresolved_issues": summary.unresolved_issues or [],
            "risks_and_focus": summary.risks_and_focus or [],
        }
    finally:
        db.close()


def regenerate_report_from_run(
    output_dir: Path,
    *,
    final_meeting_id: str | None = None,
) -> dict[str, Any]:
    existing_trace_path = output_dir / "first_loss_trace.json"
    existing_trace = load_json(existing_trace_path) if existing_trace_path.exists() else {}
    existing_metadata = (
        existing_trace.get("metadata")
        if isinstance(existing_trace, dict) and isinstance(existing_trace.get("metadata"), dict)
        else {}
    )
    semantic_trace_dir = find_semantic_trace_dir(output_dir, existing_metadata)
    transcript_rows = load_json(output_dir / "transcript_segments.json")
    rag_context = load_json(output_dir / "rag_context.json")
    final_result = load_persisted_final_result(final_meeting_id) if final_meeting_id else None

    targets = [
        build_target_diagnosis(
            target,
            transcript_rows=transcript_rows,
            semantic_trace_dir=semantic_trace_dir,
            rag_trace=rag_context.get("retrieval_trace", {}),
            qwen_raw_parsed=load_json(output_dir / "qwen_raw_parsed.json"),
            normalized_before_fusion=load_json(output_dir / "normalized_before_fusion.json"),
            action_fused=load_json(output_dir / "action_fused.json"),
            decision_fused=load_json(output_dir / "decision_fused.json"),
            unresolved_fused=load_json(output_dir / "unresolved_fused.json"),
            evidence_resolved=load_json(output_dir / "evidence_resolved.json"),
            postprocessed=load_json(output_dir / "postprocessed_result.json"),
            validated_result=load_json(output_dir / "validated_result.json"),
            final_result=final_result,
            action_fusion_audit=load_json(output_dir / "action_fusion_audit.json"),
            postprocessor_audit=load_json(output_dir / "postprocessor_audit.json"),
            validator_audit=load_json(output_dir / "validator_audit.json"),
        )
        for target in TARGETS
    ]
    action_fp_production_trace = build_action_fp_production_trace(
        transcript_rows=transcript_rows,
        semantic_trace_dir=semantic_trace_dir,
        rag_trace=rag_context.get("retrieval_trace", {}),
        qwen_raw_parsed=load_json(output_dir / "qwen_raw_parsed.json"),
        normalized_before_fusion=load_json(output_dir / "normalized_before_fusion.json"),
        action_fused=load_json(output_dir / "action_fused.json"),
        evidence_resolved=load_json(output_dir / "evidence_resolved.json"),
        postprocessed=load_json(output_dir / "postprocessed_result.json"),
        validated_result=load_json(output_dir / "validated_result.json"),
        final_result=final_result,
        action_fusion_audit=load_json(output_dir / "action_fusion_audit.json"),
        postprocessor_audit=load_json(output_dir / "postprocessor_audit.json"),
        validator_audit=load_json(output_dir / "validator_audit.json"),
    )

    metadata = {
        **existing_metadata,
        "run_id": existing_metadata.get("run_id") or output_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "semantic_trace_dir": str(semantic_trace_dir),
        "rag_collection_name": rag_context.get("collection_name"),
        "rag_dataset_version": rag_context.get("dataset_version"),
        "rag_chunk_schema_version": rag_context.get("chunk_schema_version"),
        "retrieval_version": rag_context.get("retrieval_version"),
        "scenario_taxonomy_version": rag_context.get("scenario_taxonomy_version"),
        "retrieved_chunk_ids": rag_context.get("retrieved_chunk_ids") or rag_context.get("chunk_ids") or [],
        "regenerated_from_existing_artifacts": True,
        "final_meeting_id": final_meeting_id,
        "final_source": "postgresql" if final_meeting_id else "validated_result_json",
    }
    report_payload = {
        "metadata": metadata,
        "targets": targets,
        "action_fp_production_trace": action_fp_production_trace,
    }
    write_json(output_dir / "first_loss_trace.json", report_payload)
    (output_dir / "first_loss_report.md").write_text(
        render_report(report_payload),
        encoding="utf-8",
    )
    return report_payload


def main() -> int:
    args = parse_args()
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model
        get_settings.cache_clear()

    if args.reuse_run:
        output_dir = Path(args.reuse_run)
        report_payload = regenerate_report_from_run(
            output_dir,
            final_meeting_id=args.final_meeting_id,
        )
        print(
            json.dumps(
                {
                    "status": "completed",
                    "reused_existing_artifacts": True,
                    "output_dir": str(output_dir),
                    "report": str(output_dir / "first_loss_report.md"),
                    "trace": str(output_dir / "first_loss_trace.json"),
                    "target_count": len(report_payload["targets"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    input_file = Path(args.input_file)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_root) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = parse_meeting_text(input_file)
    transcript_rows = build_transcript_segments(parsed)
    transcript_text = build_transcript_text(transcript_rows)
    meeting_id = f"first-loss-{uuid.uuid4()}"
    write_json(output_dir / "transcript_segments.json", transcript_rows)
    (output_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")

    semantic_trace_dir = run_semantic_shadow_trace(
        meeting_id,
        transcript_rows,
        trace_root=output_dir / "semantic_pipeline_trace",
    )
    semantic_action_candidates = _semantic_action_candidates_from_trace(semantic_trace_dir)
    semantic_decision_candidates = _semantic_decision_candidates_from_trace(semantic_trace_dir)
    semantic_unresolved_candidates = _semantic_unresolved_candidates_from_trace(semantic_trace_dir)

    pipeline = run_formal_pipeline(
        transcript_text=transcript_text,
        transcript_segments=transcript_rows,
        semantic_action_candidates=semantic_action_candidates,
        semantic_decision_candidates=semantic_decision_candidates,
        semantic_unresolved_candidates=semantic_unresolved_candidates,
        output_dir=output_dir,
        top_k=args.top_k,
    )
    rag_context = pipeline["rag_context"]

    targets = [
        build_target_diagnosis(
            target,
            transcript_rows=transcript_rows,
            semantic_trace_dir=semantic_trace_dir,
            rag_trace=rag_context.retrieval_trace,
            qwen_raw_parsed=pipeline["qwen_raw_parsed"],
            normalized_before_fusion=pipeline["normalized_before_fusion"],
            action_fused=pipeline["action_fused"],
            decision_fused=pipeline["decision_fused"],
            unresolved_fused=pipeline["unresolved_fused"],
            evidence_resolved=pipeline["evidence_resolved"],
            postprocessed=pipeline["postprocessed"],
            validated_result=pipeline["validated_result"],
            action_fusion_audit=pipeline["action_fusion_audit"],
            postprocessor_audit=pipeline["postprocessor_audit"],
            validator_audit=pipeline["validator_audit"],
        )
        for target in TARGETS
    ]
    final_result = load_persisted_final_result(args.final_meeting_id) if args.final_meeting_id else None
    action_fp_production_trace = build_action_fp_production_trace(
        transcript_rows=transcript_rows,
        semantic_trace_dir=semantic_trace_dir,
        rag_trace=rag_context.retrieval_trace,
        qwen_raw_parsed=pipeline["qwen_raw_parsed"],
        normalized_before_fusion=pipeline["normalized_before_fusion"],
        action_fused=pipeline["action_fused"],
        evidence_resolved=pipeline["evidence_resolved"],
        postprocessed=pipeline["postprocessed"],
        validated_result=pipeline["validated_result"],
        final_result=final_result,
        action_fusion_audit=pipeline["action_fusion_audit"],
        postprocessor_audit=pipeline["postprocessor_audit"],
        validator_audit=pipeline["validator_audit"],
    )

    metadata = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "meeting_id": meeting_id,
        "semantic_trace_dir": str(semantic_trace_dir),
        "duration_ms": pipeline["duration_ms"],
        "rag_collection_name": rag_context.collection_name,
        "rag_dataset_version": rag_context.dataset_version,
        "rag_chunk_schema_version": rag_context.chunk_schema_version,
        "retrieval_version": rag_context.retrieval_version,
        "scenario_taxonomy_version": rag_context.scenario_taxonomy_version,
        "retrieved_chunk_ids": rag_context.retrieved_chunk_ids or rag_context.chunk_ids,
        "final_meeting_id": args.final_meeting_id,
        "final_source": "postgresql" if args.final_meeting_id else "validated_result_json",
    }
    report_payload = {
        "metadata": metadata,
        "targets": targets,
        "action_fp_production_trace": action_fp_production_trace,
    }
    write_json(output_dir / "first_loss_trace.json", report_payload)
    (output_dir / "first_loss_report.md").write_text(
        render_report(report_payload),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "completed",
                "output_dir": str(output_dir),
                "report": str(output_dir / "first_loss_report.md"),
                "trace": str(output_dir / "first_loss_trace.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
