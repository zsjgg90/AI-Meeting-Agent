from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


from app.analysis_contract import normalize_meeting_analysis_result  # noqa: E402
from app.anti_hallucination_validator import validate_meeting_analysis_with_audit  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.meeting_analysis_postprocessor import MeetingAnalysisPostProcessor  # noqa: E402
from app.meeting_analyst_prompt import RAG_QUERY, build_meeting_analyst_prompt  # noqa: E402
from app.meeting_analyst_service import extract_json  # noqa: E402
from app.ollama_client import build_chat_url, build_ollama_format, build_ollama_options  # noqa: E402
from app.prompt_registry import get_meeting_analyst_prompt_spec  # noqa: E402
from app.rag_retriever import RagContext, RagRetriever  # noqa: E402


DEFAULT_INPUT_PATH = Path(
    "C:\\Users\\Administrator\\Desktop\\20\u5957\u5168\u9886\u57df30\u5206\u949f\u6807\u51c6\u771f\u5b9e\u4f1a\u8bae\u811a\u672c\uff08AI\u667a\u80fd\u4f1a\u8bae\u6d4b\u8bd5\uff5c\u542b\u516d\u7ef4\u5b8c\u6574\u7eaa\u8981\uff09.md"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "prompt_stability_eval"
DEFAULT_MEETING_INDICES = [1, 2, 3, 5, 4]

DIMENSION_KEYS = {
    "meeting_agenda": ("item", "title", "summary"),
    "key_conclusions": ("conclusion",),
    "action_items": ("task",),
    "unresolved_issues": ("issue",),
    "risks_and_focus": ("risk",),
}
EVIDENCE_FIELDS = ["key_conclusions", "action_items", "unresolved_issues", "risks_and_focus"]


@dataclass(frozen=True)
class MeetingCase:
    meeting_id: str
    index: int
    industry: str
    title: str
    scenario: str
    participants: str
    transcript: str


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def normalize_text(text: object) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace(r"\.", ".")
    value = re.sub(r"\s+", "", value)
    return value.lower()


def similarity(a: object, b: object) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned[:48] or "meeting"


def load_meeting_cases(input_path: Path) -> list[MeetingCase]:
    content = input_path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^# 第(\d+)场｜([^｜\n]+)｜([^（\n]+)（30分钟）\s*$")
    matches = list(pattern.finditer(content))
    cases: list[MeetingCase] = []

    for pos, match in enumerate(matches):
        start = match.end()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(content)
        section = content[start:end]
        index = int(match.group(1))
        industry = match.group(2).strip()
        title = match.group(3).strip()
        participants = first_match(section, r"\*\*参会人员\*\*[：:]\s*(.+)")
        scenario = first_match(section, r"\*\*会议场景\*\*[：:]\s*(.+)")
        transcript = extract_transcript(section)
        if not transcript:
            continue
        meeting_id = f"meeting_{index:03d}_{safe_slug(title)}"
        cases.append(
            MeetingCase(
                meeting_id=meeting_id,
                index=index,
                industry=industry,
                title=title,
                scenario=scenario,
                participants=participants,
                transcript=transcript,
            )
        )
    marker_cases = load_marker_meeting_cases(content)
    if len(marker_cases) > len(cases):
        return marker_cases
    return cases


def load_marker_meeting_cases(content: str) -> list[MeetingCase]:
    marker_pattern = re.compile(r"\*\*(?:完整30分钟会议对话|六大维度纪要\+完整对话|瀹屾暣30鍒嗛挓浼氳瀵硅瘽)[^*]*\*\*")
    markers = list(marker_pattern.finditer(content))
    cases: list[MeetingCase] = []
    for pos, marker in enumerate(markers):
        start = marker.end()
        end = markers[pos + 1].start() if pos + 1 < len(markers) else len(content)
        preamble_start = markers[pos - 1].end() if pos > 0 else 0
        preamble = content[preamble_start : marker.start()]
        heading = nearest_heading(preamble)
        index = heading.get("index") or (pos + 1)
        industry = heading.get("industry") or "unknown"
        title = heading.get("title") or f"meeting_{index:03d}"
        participants = first_match(preamble, r"\*\*参会人员\*\*[：:]\s*(.+)") or ""
        scenario = first_match(preamble, r"\*\*会议场景\*\*[：:]\s*(.+)") or ""
        transcript = extract_transcript_from_body(content[start:end])
        if len(transcript) < 500:
            continue
        meeting_id = f"meeting_{index:03d}_{safe_slug(title)}"
        cases.append(
            MeetingCase(
                meeting_id=meeting_id,
                index=index,
                industry=industry,
                title=title,
                scenario=scenario,
                participants=participants,
                transcript=transcript,
            )
        )
    return cases


def nearest_heading(preamble: str) -> dict[str, Any]:
    heading_match = None
    normal_pattern = re.compile(r"(?m)^# 第(\d+)场｜([^｜\n]+)｜([^（\n]+)（30分钟）\s*$")
    for match in normal_pattern.finditer(preamble):
        heading_match = match
    if heading_match:
        return {
            "index": int(heading_match.group(1)),
            "industry": heading_match.group(2).strip(),
            "title": heading_match.group(3).strip(),
        }

    bold_lines = [line.strip("* \t") for line in preamble.splitlines() if "场" in line or "鍦" in line]
    if bold_lines:
        title = re.sub(r"^[#\s>*]+", "", bold_lines[-1]).strip()
        return {"index": None, "industry": "unknown", "title": title[:40]}
    return {"index": None, "industry": "unknown", "title": ""}


def first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def extract_transcript(section: str) -> str:
    marker = re.search(r"\*\*(?:完整30分钟会议对话|六大维度纪要\+完整对话)[^*]*\*\*", section)
    body = section[marker.end() :] if marker else section
    stop = re.search(r"(?m)^\*\*(?:1[\.、]|会议议程|2[\.、]|会议总结)", body)
    if stop:
        body = body[: stop.start()]

    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip().replace(r"\.", ".")
        if not line or line.startswith("**") or line.startswith("#"):
            continue
        if re.match(r"^[^：:\n]{1,24}[：:]\s*.+", line):
            lines.append(line)
    return "\n".join(lines)


def extract_transcript_from_body(body: str) -> str:
    stop = re.search(r"(?m)^\*\*(?:1[\\\.、]|会议议程|2[\\\.、]|会议总结)", body)
    if stop:
        body = body[: stop.start()]
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip().replace(r"\.", ".")
        if not line or line.startswith("**") or line.startswith("#"):
            continue
        if re.match(r"^[^：:\n]{1,28}[：:]\s*.+", line):
            lines.append(line)
    return "\n".join(lines)


def select_meetings(cases: list[MeetingCase], indices: list[int], limit: int) -> list[MeetingCase]:
    by_index = {case.index: case for case in cases}
    selected: list[MeetingCase] = []
    seen: set[int] = set()
    for index in indices:
        case = by_index.get(index)
        if case and index not in seen:
            selected.append(case)
            seen.add(index)
        if len(selected) >= limit:
            return selected
    for case in cases:
        if case.index not in seen:
            selected.append(case)
            seen.add(case.index)
        if len(selected) >= limit:
            break
    return selected


def serialize_rag_context(rag_context: RagContext) -> dict[str, Any]:
    return {
        "rag_chunk_count": len(rag_context.chunk_ids),
        "rag_chunk_ids": rag_context.chunk_ids,
        "rag_context_chars": len(rag_context.text),
        "collection_name": rag_context.collection_name,
        "embedding_model": rag_context.embedding_model,
        "dataset_version": rag_context.dataset_version,
        "chunk_schema_version": rag_context.chunk_schema_version,
        "chunks": rag_context.chunks,
    }


def inference_parameters(timeout: float) -> dict[str, Any]:
    settings = get_settings()
    return {
        "model": settings.ollama_model,
        "base_url": settings.ollama_base_url,
        "timeout": timeout,
        "options": build_ollama_options(),
        "format": build_ollama_format(),
    }


def call_ollama(prompt: str, timeout: float) -> tuple[dict[str, Any], str, float, dict[str, Any]]:
    settings = get_settings()
    request_parameters = inference_parameters(timeout)
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是专业 AI Meeting Analyst。"
                    "你必须严格输出合法 JSON。"
                    "不要输出 Markdown、解释或其他多余文本。"
                    "所有事实必须来自会议原文。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": request_parameters["options"],
    }
    if request_parameters["format"]:
        payload["format"] = request_parameters["format"]
    started_at = time.perf_counter()
    response = requests.post(build_chat_url(settings.ollama_base_url), json=payload, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return payload, str(payload.get("message", {}).get("content") or ""), duration_ms, request_parameters


def claim_text(field: str, item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    for key in DIMENSION_KEYS.get(field, ()):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def source_texts(result: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    entries: list[tuple[str, dict[str, Any], str]] = []
    for field in EVIDENCE_FIELDS:
        for item in result.get(field, []) or []:
            if isinstance(item, dict):
                entries.append((field, item, str(item.get("source_text") or "")))
    return entries


def source_is_continuous(source: str, transcript: str) -> bool:
    if not source or "..." in source or "……" in source:
        return False
    return normalize_text(source) in normalize_text(transcript)


def count_cross_dimension_duplicates(result: dict[str, Any]) -> int:
    entries: list[tuple[str, str]] = []
    for field in ["key_conclusions", "action_items", "unresolved_issues", "risks_and_focus"]:
        for item in result.get(field, []) or []:
            text = claim_text(field, item)
            if text:
                entries.append((field, text))

    duplicate_count = 0
    for idx, (field, text) in enumerate(entries):
        for other_field, other_text in entries[:idx]:
            if field == other_field:
                continue
            if similarity(text, other_text) >= 0.84:
                duplicate_count += 1
                break
    return duplicate_count


def count_unsupported_metadata(result: dict[str, Any]) -> int:
    count = 0
    priority_terms = [
        "高优先级",
        "中优先级",
        "低优先级",
        "优先处理",
        "优先跟进",
        "紧急",
        "high",
        "medium",
        "low",
    ]
    for item in result.get("action_items", []) or []:
        if not isinstance(item, dict):
            continue
        source_norm = normalize_text(item.get("source_text") or "")
        owner = item.get("owner_name") or item.get("owner")
        if owner and normalize_text(owner) not in source_norm:
            count += 1
        deadline = item.get("deadline") or item.get("due_date")
        if deadline and normalize_text(deadline) not in source_norm:
            count += 1
        priority = item.get("priority")
        if priority and not any(normalize_text(term) in source_norm for term in priority_terms):
            count += 1
    return count


def count_proposal_in_conclusions(result: dict[str, Any]) -> int:
    proposal_terms = ["建议", "可以考虑", "是否", "疑问", "问题是", "能不能", "希望"]
    confirm_terms = ["确认", "决定", "同意", "敲定", "达成", "锁定", "不再接收", "必须", "上线标准", "按"]
    count = 0
    for item in result.get("key_conclusions", []) or []:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('conclusion') or ''}{item.get('source_text') or ''}"
        has_proposal = any(term in text for term in proposal_terms)
        has_confirm = any(term in text for term in confirm_terms)
        if has_proposal and not has_confirm:
            count += 1
    return count


def count_resolved_issue_in_unresolved(result: dict[str, Any]) -> int:
    resolved_terms = ["已解决", "已明确", "无问题", "没有问题", "可落地", "已完成", "确认可以", "按这个执行"]
    count = 0
    for item in result.get("unresolved_issues", []) or []:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('issue') or ''}{item.get('reason') or ''}{item.get('source_text') or ''}"
        if any(term in text for term in resolved_terms):
            count += 1
    return count


def summarize_validator_audit(audit: list[dict[str, Any]]) -> dict[str, int]:
    keep_count = sum(1 for item in audit if item.get("action") == "keep")
    remove_count = sum(1 for item in audit if item.get("action") == "remove")
    modify_count = sum(1 for item in audit if item.get("action") == "modify")
    return {
        "validator_event_count": len(audit),
        "validator_keep_count": keep_count,
        "validator_remove_count": remove_count,
        "validator_modify_count": modify_count,
    }


def summarize_layer_audit(prefix: str, audit: list[dict[str, Any]]) -> dict[str, int]:
    keep_count = sum(1 for item in audit if item.get("action") == "keep")
    remove_count = sum(1 for item in audit if item.get("action") == "remove")
    modify_count = sum(1 for item in audit if item.get("action") == "modify")
    return {
        f"{prefix}_event_count": len(audit),
        f"{prefix}_keep_count": keep_count,
        f"{prefix}_remove_count": remove_count,
        f"{prefix}_modify_count": modify_count,
    }


def count_items(result: dict[str, Any]) -> int:
    total = 0
    for field in ["meeting_agenda", "key_conclusions", "action_items", "unresolved_issues", "risks_and_focus"]:
        value = result.get(field, [])
        if isinstance(value, list):
            total += len(value)
    if result.get("meeting_summary"):
        total += 1
    return total


def compute_metrics(
    result: dict[str, Any],
    transcript: str,
    audit: list[dict[str, Any]],
    model_duration_ms: float | None,
    postprocessor_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    agenda = result.get("meeting_agenda", []) or []
    ellipsis_count = 0
    invalid_source_count = 0
    for _field, _item, source in source_texts(result):
        if "..." in source or "……" in source:
            ellipsis_count += 1
        if not source_is_continuous(source, transcript):
            invalid_source_count += 1

    validator_summary = summarize_validator_audit(audit)
    postprocessor_summary = summarize_layer_audit("postprocessor", postprocessor_audit or [])
    metrics = {
        "agenda_count": len(agenda) if isinstance(agenda, list) else 0,
        "ellipsis_source_count": ellipsis_count,
        "invalid_source_text_count": invalid_source_count,
        "cross_dimension_duplicate_count": count_cross_dimension_duplicates(result),
        "unsupported_metadata_count": count_unsupported_metadata(result),
        "proposal_in_conclusion_count": count_proposal_in_conclusions(result),
        "resolved_issue_in_unresolved_count": count_resolved_issue_in_unresolved(result),
        "model_duration_ms": model_duration_ms,
        **postprocessor_summary,
        **validator_summary,
    }
    metrics["overall_score"] = score_metrics(metrics)
    metrics["passed"] = run_passed(metrics)
    return metrics


def score_metrics(metrics: dict[str, Any]) -> int:
    score = 100
    if not 3 <= int(metrics["agenda_count"]) <= 6:
        score -= 12
    score -= min(int(metrics["ellipsis_source_count"]) * 5, 25)
    score -= min(int(metrics["invalid_source_text_count"]) * 4, 20)
    score -= min(int(metrics["cross_dimension_duplicate_count"]) * 6, 18)
    score -= min(int(metrics["unsupported_metadata_count"]) * 4, 20)
    score -= min(int(metrics["proposal_in_conclusion_count"]) * 10, 20)
    score -= min(int(metrics["resolved_issue_in_unresolved_count"]) * 8, 16)
    score -= min(int(metrics["validator_remove_count"]) * 3, 15)
    score -= min(int(metrics["validator_modify_count"]), 10)
    return max(score, 0)


def run_passed(metrics: dict[str, Any]) -> bool:
    total_validator_changes = int(metrics["validator_remove_count"]) + int(metrics["validator_modify_count"])
    return (
        int(metrics["overall_score"]) >= 85
        and 3 <= int(metrics["agenda_count"]) <= 6
        and int(metrics["ellipsis_source_count"]) == 0
        and int(metrics["unsupported_metadata_count"]) == 0
        and int(metrics["proposal_in_conclusion_count"]) == 0
        and total_validator_changes <= 8
    )


def dimension_text_set(result: dict[str, Any], field: str) -> set[str]:
    values: set[str] = set()
    for item in result.get(field, []) or []:
        text = normalize_text(claim_text(field, item))
        if text:
            values.add(text)
    return values


def dimension_text_list(result: dict[str, Any], field: str) -> list[str]:
    values: list[str] = []
    for item in result.get(field, []) or []:
        text = claim_text(field, item)
        if text:
            values.append(text)
    return values


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(len(a | b), 1)


def semantic_consistency(a: list[str], b: list[str], threshold: float = 0.72) -> float:
    if not a and not b:
        return 1.0
    unmatched = set(range(len(b)))
    matched = 0
    for item in a:
        best_index = None
        best_score = 0.0
        for idx in unmatched:
            score = similarity(item, b[idx])
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index is not None and best_score >= threshold:
            unmatched.remove(best_index)
            matched += 1
    return matched / max(len(a), len(b), 1)


def output_order_consistency(a: list[str], b: list[str], threshold: float = 0.72) -> float:
    if len(a) <= 1 and len(b) <= 1:
        return 1.0
    used: set[int] = set()
    matched_indices: list[int] = []
    for item in a:
        best_index = None
        best_score = 0.0
        for idx, other in enumerate(b):
            if idx in used:
                continue
            score = similarity(item, other)
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index is not None and best_score >= threshold:
            used.add(best_index)
            matched_indices.append(best_index)
    if not matched_indices:
        return 0.0
    longest = 1
    dp = [1] * len(matched_indices)
    for idx in range(len(matched_indices)):
        for prev in range(idx):
            if matched_indices[prev] <= matched_indices[idx]:
                dp[idx] = max(dp[idx], dp[prev] + 1)
        longest = max(longest, dp[idx])
    return longest / len(matched_indices)


def inference_parameters_match(run_1: dict[str, Any], run_2: dict[str, Any]) -> bool:
    return run_1.get("inference_parameters") == run_2.get("inference_parameters")


def compare_runs(run_1: dict[str, Any], run_2: dict[str, Any]) -> dict[str, Any]:
    metrics_1 = run_1.get("metrics", {})
    metrics_2 = run_2.get("metrics", {})
    parsed_1 = run_1.get("validated_result") or run_1.get("parsed_result") or {}
    parsed_2 = run_2.get("validated_result") or run_2.get("parsed_result") or {}
    dimensions = ["meeting_agenda", "key_conclusions", "action_items", "unresolved_issues", "risks_and_focus"]
    dimension_comparison = {}
    severe_reasons: list[str] = []

    for field in dimensions:
        set_1 = dimension_text_set(parsed_1, field)
        set_2 = dimension_text_set(parsed_2, field)
        list_1 = dimension_text_list(parsed_1, field)
        list_2 = dimension_text_list(parsed_2, field)
        count_diff = abs(len(set_1) - len(set_2))
        overlap = round(jaccard(set_1, set_2), 3)
        consistency = round(semantic_consistency(list_1, list_2), 3)
        order_consistency = round(output_order_consistency(list_1, list_2), 3)
        dimension_comparison[field] = {
            "run_1_count": len(set_1),
            "run_2_count": len(set_2),
            "count_diff": count_diff,
            "jaccard": overlap,
            "semantic_consistency": consistency,
            "order_consistency": order_consistency,
        }
        if field == "key_conclusions" and consistency < 0.9:
            severe_reasons.append("key_conclusions_consistency_below_90")
        if field == "action_items" and consistency < 0.85:
            severe_reasons.append("action_items_consistency_below_85")
        if field == "meeting_agenda" and consistency < 0.85:
            severe_reasons.append("meeting_agenda_consistency_below_85")
        if field in {"meeting_agenda", "key_conclusions", "action_items"} and order_consistency < 0.85:
            severe_reasons.append(f"{field}_order_consistency_below_85")
        if count_diff >= 3:
            severe_reasons.append(f"{field}_count_diff_{count_diff}")

    score_diff = abs(int(metrics_1.get("overall_score", 0)) - int(metrics_2.get("overall_score", 0)))
    agenda_pass_diff = (3 <= int(metrics_1.get("agenda_count", 0)) <= 6) != (3 <= int(metrics_2.get("agenda_count", 0)) <= 6)
    if score_diff >= 15:
        severe_reasons.append(f"score_diff_{score_diff}")
    if agenda_pass_diff:
        severe_reasons.append("agenda_pass_status_changed")
    if not run_1.get("ok") or not run_2.get("ok"):
        severe_reasons.append("run_failed")
    parameters_match = inference_parameters_match(run_1, run_2)
    if not parameters_match:
        severe_reasons.append("inference_parameters_changed")

    return {
        "score_diff": score_diff,
        "agenda_count_diff": abs(int(metrics_1.get("agenda_count", 0)) - int(metrics_2.get("agenda_count", 0))),
        "key_conclusions_consistency": dimension_comparison["key_conclusions"]["semantic_consistency"],
        "action_items_consistency": dimension_comparison["action_items"]["semantic_consistency"],
        "agenda_topic_consistency": dimension_comparison["meeting_agenda"]["semantic_consistency"],
        "output_order_consistency": round(
            min(
                dimension_comparison["meeting_agenda"]["order_consistency"],
                dimension_comparison["key_conclusions"]["order_consistency"],
                dimension_comparison["action_items"]["order_consistency"],
            ),
            3,
        ),
        "inference_parameters_match": parameters_match,
        "dimension_comparison": dimension_comparison,
        "severe_semantic_conflict": bool(severe_reasons),
        "severe_reasons": severe_reasons,
    }


def run_single_eval(case: MeetingCase, run_index: int, rag_context: RagContext, output_dir: Path, timeout: float) -> dict[str, Any]:
    settings = get_settings()
    prompt_spec = get_meeting_analyst_prompt_spec()
    started_at = time.perf_counter()
    prompt = build_meeting_analyst_prompt(rag_context=rag_context.text, transcript=case.transcript)
    payload: dict[str, Any] = {
        "ok": False,
        "meeting": {
            "meeting_id": case.meeting_id,
            "index": case.index,
            "industry": case.industry,
            "title": case.title,
            "scenario": case.scenario,
            "participants": case.participants,
        },
        "run_index": run_index,
        "prompt_version": prompt_spec.prompt_version,
        "schema_version": prompt_spec.schema_version,
        "model_name": settings.ollama_model,
        "rag_chunk_ids": rag_context.chunk_ids,
        "transcript_chars": len(case.transcript),
        "prompt_chars": len(prompt),
        "result_source": "legacy_qwen_rag",
        "inference_parameters": inference_parameters(timeout),
    }

    try:
        ollama_response, raw_output, model_duration_ms, request_parameters = call_ollama(prompt, timeout)
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
            "result_source": "legacy_qwen_rag",
        }
        normalized_before = normalize_meeting_analysis_result(
            parsed,
            model_name=f"{settings.ollama_model}+rag",
        )
        normalized_before_dump = normalized_before.model_dump()
        postprocessor = MeetingAnalysisPostProcessor()
        postprocessed = postprocessor.process(normalized_before, case.transcript)
        postprocessed_dump = postprocessed.model_dump()
        postprocessor_audit = postprocessor.last_audit
        validated, audit = validate_meeting_analysis_with_audit(deepcopy(postprocessed_dump), case.transcript)
        normalized = normalize_meeting_analysis_result(validated, model_name=f"{settings.ollama_model}+rag").model_dump()
        metrics = compute_metrics(validated, case.transcript, audit, model_duration_ms, postprocessor_audit)
        run_dir = output_dir / f"run_{run_index}"
        write_json(run_dir / "normalized_before_postprocess.json", normalized_before_dump)
        write_json(run_dir / "postprocessed_result.json", postprocessed_dump)
        write_json(run_dir / "validated_result.json", validated)
        write_json(run_dir / "postprocessor_audit.json", postprocessor_audit)
        write_json(run_dir / "validator_audit.json", audit)
        payload.update(
            {
                "ok": True,
                "ollama_response": ollama_response,
                "raw_output": raw_output,
                "inference_parameters": request_parameters,
                "parsed_result": parsed,
                "normalized_before_postprocess": normalized_before_dump,
                "postprocessed_result": postprocessed_dump,
                "validated_result": validated,
                "normalized_result": normalized,
                "postprocessor_audit": postprocessor_audit,
                "postprocessor_audit_summary": summarize_layer_audit("postprocessor", postprocessor_audit),
                "validator_audit": audit,
                "validator_audit_summary": summarize_validator_audit(audit),
                "metrics": metrics,
                "layer_artifacts": {
                    "normalized_before_postprocess": str(run_dir / "normalized_before_postprocess.json"),
                    "postprocessed_result": str(run_dir / "postprocessed_result.json"),
                    "validated_result": str(run_dir / "validated_result.json"),
                },
                "total_duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "failure_reason": None,
            }
        )
    except Exception as exc:
        payload.update(
            {
                "ok": False,
                "metrics": failure_metrics(),
                "total_duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "failure_reason": f"{exc.__class__.__name__}: {exc}",
            }
        )

    write_json(output_dir / f"run_{run_index}_result.json", payload)
    return payload


def failure_metrics() -> dict[str, Any]:
    metrics = {
        "agenda_count": 0,
        "ellipsis_source_count": 0,
        "invalid_source_text_count": 0,
        "cross_dimension_duplicate_count": 0,
        "unsupported_metadata_count": 0,
        "proposal_in_conclusion_count": 0,
        "resolved_issue_in_unresolved_count": 0,
        "postprocessor_event_count": 0,
        "postprocessor_keep_count": 0,
        "postprocessor_remove_count": 0,
        "postprocessor_modify_count": 0,
        "validator_event_count": 0,
        "validator_keep_count": 0,
        "validator_remove_count": 0,
        "validator_modify_count": 0,
        "model_duration_ms": None,
        "overall_score": 0,
        "passed": False,
    }
    return metrics


def aggregate_common_errors(runs: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> dict[str, int]:
    counters = {
        "agenda_out_of_range": 0,
        "ellipsis_source": 0,
        "invalid_source_text": 0,
        "cross_dimension_duplicate": 0,
        "unsupported_metadata": 0,
        "proposal_in_conclusion": 0,
        "resolved_issue_in_unresolved": 0,
        "large_validator_changes": 0,
        "large_postprocessor_changes": 0,
        "severe_semantic_conflict": 0,
        "low_key_conclusion_consistency": 0,
        "low_action_item_consistency": 0,
        "low_agenda_consistency": 0,
        "low_output_order_consistency": 0,
        "inference_parameter_mismatch": 0,
        "run_failed": 0,
    }
    for run in runs:
        metrics = run.get("metrics", {})
        if not run.get("ok"):
            counters["run_failed"] += 1
        if not 3 <= int(metrics.get("agenda_count", 0)) <= 6:
            counters["agenda_out_of_range"] += 1
        counters["ellipsis_source"] += int(metrics.get("ellipsis_source_count", 0))
        counters["invalid_source_text"] += int(metrics.get("invalid_source_text_count", 0))
        counters["cross_dimension_duplicate"] += int(metrics.get("cross_dimension_duplicate_count", 0))
        counters["unsupported_metadata"] += int(metrics.get("unsupported_metadata_count", 0))
        counters["proposal_in_conclusion"] += int(metrics.get("proposal_in_conclusion_count", 0))
        counters["resolved_issue_in_unresolved"] += int(metrics.get("resolved_issue_in_unresolved_count", 0))
        if int(metrics.get("validator_remove_count", 0)) + int(metrics.get("validator_modify_count", 0)) > 8:
            counters["large_validator_changes"] += 1
        if int(metrics.get("postprocessor_remove_count", 0)) + int(metrics.get("postprocessor_modify_count", 0)) > 8:
            counters["large_postprocessor_changes"] += 1
    for comparison in comparisons:
        if comparison.get("severe_semantic_conflict"):
            counters["severe_semantic_conflict"] += 1
        if float(comparison.get("key_conclusions_consistency", 0)) < 0.9:
            counters["low_key_conclusion_consistency"] += 1
        if float(comparison.get("action_items_consistency", 0)) < 0.85:
            counters["low_action_item_consistency"] += 1
        if float(comparison.get("agenda_topic_consistency", 0)) < 0.85:
            counters["low_agenda_consistency"] += 1
        if float(comparison.get("output_order_consistency", 0)) < 0.85:
            counters["low_output_order_consistency"] += 1
        if not comparison.get("inference_parameters_match", False):
            counters["inference_parameter_mismatch"] += 1
    return counters


def build_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Prompt Stability Evaluation",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- model: {report['model_name']}",
        f"- inference_parameters: `{json.dumps(report['inference_parameters'], ensure_ascii=False)}`",
        f"- prompt_version: {report['prompt_version']}",
        f"- meeting_count: {report['meeting_count']}",
        f"- runs_per_meeting: {report['runs_per_meeting']}",
        f"- overall_passed: {report['overall_passed']}",
        "",
        "## Scores",
        "",
        "| Meeting | Run 1 | Run 2 | Agenda | Conclusion Consistency | Action Consistency | Order | Severe Conflict | Passed |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in report["meetings"]:
        run_1 = item["runs"][0]["metrics"]
        run_2 = item["runs"][1]["metrics"]
        comparison = item["comparison"]
        lines.append(
            "| {title} | {s1} | {s2} | {a1}/{a2} | {kc} | {ai} | {order} | {conflict} | {passed} |".format(
                title=item["title"],
                s1=run_1["overall_score"],
                s2=run_2["overall_score"],
                a1=run_1["agenda_count"],
                a2=run_2["agenda_count"],
                kc=comparison.get("key_conclusions_consistency"),
                ai=comparison.get("action_items_consistency"),
                order=comparison.get("output_order_consistency"),
                conflict=comparison["severe_semantic_conflict"],
                passed=item["passed"],
            )
        )
    lines.extend(
        [
            "",
            "## Common Errors",
            "",
        ]
    )
    for key, value in report["common_errors"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Layer Changes",
            "",
            "| Meeting | Run | PostProcessor keep/remove/modify | Validator keep/remove/modify |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for item in report["meetings"]:
        for run in item["runs"]:
            metrics = run.get("metrics", {})
            lines.append(
                "| {title} | {run} | {pk}/{pr}/{pm} | {vk}/{vr}/{vm} |".format(
                    title=item["title"],
                    run=run.get("run_index"),
                    pk=metrics.get("postprocessor_keep_count", 0),
                    pr=metrics.get("postprocessor_remove_count", 0),
                    pm=metrics.get("postprocessor_modify_count", 0),
                    vk=metrics.get("validator_keep_count", 0),
                    vr=metrics.get("validator_remove_count", 0),
                    vm=metrics.get("validator_modify_count", 0),
                )
            )
    lines.extend(
        [
            "",
            "## Production Recommendation",
            "",
            report["production_recommendation"],
            "",
        ]
    )
    return "\n".join(lines)


def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    prompt_spec = get_meeting_analyst_prompt_spec()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    input_path = Path(args.input_path)

    cases = load_meeting_cases(input_path)
    selected = select_meetings(cases, parse_indices(args.meeting_indices), args.meeting_limit)
    if not selected:
        raise ValueError(f"No meeting cases found in {input_path}")

    rag_context = RagRetriever().build_context_payload(query=RAG_QUERY, top_k=settings.rag_top_k)
    write_json(output_root / "rag_context.json", serialize_rag_context(rag_context))

    all_runs: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    meeting_reports: list[dict[str, Any]] = []

    for case in selected:
        case_dir = output_root / case.meeting_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "input_transcript.txt").write_text(case.transcript, encoding="utf-8")
        runs = [
            run_single_eval(case, run_index, rag_context, case_dir, args.ollama_timeout)
            for run_index in range(1, args.runs_per_meeting + 1)
        ]
        all_runs.extend(runs)
        comparison = compare_runs(runs[0], runs[1]) if len(runs) >= 2 else {}
        write_json(case_dir / "comparison.json", comparison)
        if comparison:
            comparisons.append(comparison)
        passed = all(run.get("metrics", {}).get("passed") for run in runs) and not comparison.get("severe_semantic_conflict", False)
        meeting_reports.append(
            {
                "meeting_id": case.meeting_id,
                "index": case.index,
                "industry": case.industry,
                "title": case.title,
                "scenario": case.scenario,
                "passed": passed,
                "runs": summarize_runs(runs),
                "comparison": comparison,
                "output_dir": str(case_dir),
            }
        )

    common_errors = aggregate_common_errors(all_runs, comparisons)
    overall_passed = all(item["passed"] for item in meeting_reports)
    recommendation = (
        "当前 Prompt + PostProcessor + Validator 通过本轮稳定性回归，可进入受控生产灰度。"
        if overall_passed
        else "当前 Prompt + PostProcessor + Validator 未通过本轮稳定性回归，不建议直接进入正式生产。"
    )
    report = {
        "generated_at": datetime.now().isoformat(),
        "input_path": str(input_path),
        "output_root": str(output_root),
        "model_name": settings.ollama_model,
        "ollama_timeout": args.ollama_timeout,
        "inference_parameters": inference_parameters(args.ollama_timeout),
        "prompt_id": prompt_spec.prompt_id,
        "prompt_version": prompt_spec.prompt_version,
        "schema_version": prompt_spec.schema_version,
        "rag_top_k": settings.rag_top_k,
        "rag_chunk_ids": rag_context.chunk_ids,
        "meeting_count": len(selected),
        "runs_per_meeting": args.runs_per_meeting,
        "overall_passed": overall_passed,
        "meetings": meeting_reports,
        "common_errors": common_errors,
        "production_recommendation": recommendation,
    }
    write_json(output_root / "stability_report.json", report)
    (output_root / "stability_report.md").write_text(build_markdown_report(report), encoding="utf-8")
    return report


def summarize_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for run in runs:
        summaries.append(
            {
                "run_index": run.get("run_index"),
                "ok": run.get("ok"),
                "failure_reason": run.get("failure_reason"),
                "transcript_chars": run.get("transcript_chars"),
                "prompt_chars": run.get("prompt_chars"),
                "total_duration_ms": run.get("total_duration_ms"),
                "inference_parameters": run.get("inference_parameters"),
                "metrics": run.get("metrics"),
                "result_path": f"run_{run.get('run_index')}_result.json",
            }
        )
    return summaries


def parse_indices(value: str) -> list[int]:
    if not value:
        return DEFAULT_MEETING_INDICES
    indices = []
    for part in value.split(","):
        part = part.strip()
        if part:
            indices.append(int(part))
    return indices or DEFAULT_MEETING_INDICES


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run repeated legacy Qwen3 + RAG prompt stability evaluation.")
    parser.add_argument("--input-path", default=str(DEFAULT_INPUT_PATH), help="Markdown file containing real meeting scripts.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for prompt stability artifacts.")
    parser.add_argument("--meeting-limit", type=int, default=5, help="Number of meetings to evaluate, from 3 to 5 by default.")
    parser.add_argument("--meeting-indices", default=",".join(str(i) for i in DEFAULT_MEETING_INDICES), help="Comma-separated source meeting indices.")
    parser.add_argument("--runs-per-meeting", type=int, default=2, help="Repeated runs per meeting.")
    parser.add_argument("--ollama-timeout", type=float, default=settings.ollama_timeout_seconds, help="Per Ollama request timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.meeting_limit < 1:
        raise ValueError("--meeting-limit must be positive")
    if args.runs_per_meeting < 2:
        raise ValueError("--runs-per-meeting must be at least 2")
    report = run_eval(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
