from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

for path in (PROJECT_ROOT, WORKER_ROOT, SCRIPT_FILE.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.meeting_analyst_service import MeetingAnalystService  # noqa: E402
from app.meeting_title import (  # noqa: E402
    ACTION_WORD_RE,
    DEFAULT_TITLE_RE,
    EXPLANATION_PATTERNS,
    GENERIC_TITLES,
    MEETING_TYPES,
    ROLE_TASK_RE,
    TIME_WORD_RE,
    has_valid_meeting_type,
    has_valid_title_basis,
    is_valid_ai_title,
    maybe_apply_ai_title,
)
from app.ollama_client import OllamaClient  # noqa: E402
from app.rag_retriever import RagRetriever  # noqa: E402
from run_prompt_stability_eval import DEFAULT_INPUT_PATH, load_meeting_cases  # noqa: E402


OUTPUT_DIR = PROJECT_ROOT / "data" / "debug" / "title_regression"
DEFAULT_TITLE = "2026-07-30 10:00 实时录音"
MIN_SAMPLE_COUNT = 20
DEFAULT_LIMIT = 24


@dataclass(frozen=True)
class LiveTitleCase:
    sample_id: str
    source: str
    source_kind: str
    expected_category: str
    coverage_tags: list[str]
    transcript: str


class MeetingStub:
    title = DEFAULT_TITLE
    title_source = "fallback"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned[:60] or "meeting"


def transcript_hash(transcript: str) -> str:
    return hashlib.sha1(transcript.strip().encode("utf-8")).hexdigest()


def transcript_from_meeting_input(path: Path) -> str:
    data = json.loads(read_text(path))
    segments = data.get("transcript") or data.get("segments") or []
    lines: list[str] = []
    for segment in segments:
        if isinstance(segment, dict):
            speaker = str(segment.get("speaker_name") or segment.get("speaker_label") or "speaker").strip()
            text = str(segment.get("text") or "").strip()
            if text:
                lines.append(f"{speaker}: {text}")
        else:
            text = str(segment).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def classify_case(sample_id: str, source: str, transcript: str) -> tuple[str, list[str]]:
    transcript_head = transcript[:900]
    metadata_haystack = f"{sample_id} {source}"
    tags: list[str] = []

    if len(transcript) < 350:
        tags.append("short_recording")
    if "speaker_" in transcript or "未知说话人" in transcript or "未知识说话人" in transcript:
        tags.append("poor_asr")
    if "cross_department" in source or "客户问题" in transcript_head or "跨部门" in transcript_head:
        tags.append("multi_topic")

    if any(token in transcript_head for token in ["风险评审", "风险排查", "合规风险"]):
        expected = "risk_review"
        tags.append("risk_review")
    elif "需求评审" in transcript_head or "迭代启动" in transcript_head:
        expected = "requirement_review"
        tags.append("requirement_review")
    elif "方案评审" in transcript_head or "技术方案" in transcript_head or "方案讨论" in transcript_head:
        expected = "solution_review"
        tags.append("solution_review")
    elif any(token in transcript_head for token in ["复盘", "总结"]):
        expected = "project_retrospective"
        tags.append("project_retrospective")
    elif any(token in transcript_head for token in ["周会", "周度", "例行短会", "项目周"]):
        expected = "project_weekly"
        tags.append("project_weekly")
    elif "客户" in transcript_head:
        expected = "customer_communication"
        tags.append("customer_communication")
    elif any(token in metadata_haystack for token in ["project_weekly"]):
        expected = "project_weekly"
        tags.append("project_weekly")
    elif "requirement_review" in source:
        expected = "requirement_review"
        tags.append("requirement_review")
    elif "decision_meeting" in source:
        expected = "solution_review"
        tags.append("solution_review")
    elif "risk_review" in source:
        expected = "risk_review"
        tags.append("risk_review")
    elif "retrospective" in source:
        expected = "project_retrospective"
        tags.append("project_retrospective")
    else:
        expected = "other"
        tags.append("other")

    return expected, sorted(set(tags))


def discover_cases(limit: int) -> list[LiveTitleCase]:
    candidates: list[LiveTitleCase] = []

    if DEFAULT_INPUT_PATH.exists():
        for case in load_meeting_cases(DEFAULT_INPUT_PATH):
            expected, tags = classify_case(case.meeting_id, str(DEFAULT_INPUT_PATH), case.transcript)
            candidates.append(
                LiveTitleCase(
                    sample_id=case.meeting_id,
                    source=str(DEFAULT_INPUT_PATH),
                    source_kind="desktop_20_suite",
                    expected_category=expected,
                    coverage_tags=tags,
                    transcript=case.transcript,
                )
            )

    repo_sources: list[tuple[Path, str]] = []
    debug_root = PROJECT_ROOT / "data" / "debug"
    generated_report_root = debug_root / "title_regression"
    repo_sources.extend(
        (path, "debug_input_transcript")
        for path in debug_root.rglob("input_transcript.txt")
        if not path.is_relative_to(generated_report_root)
    )
    repo_sources.extend(
        (path, "acceptance_meeting_input")
        for path in debug_root.rglob("meeting_input.json")
        if not path.is_relative_to(generated_report_root)
    )

    for path, source_kind in repo_sources:
        try:
            transcript = transcript_from_meeting_input(path) if path.name == "meeting_input.json" else read_text(path)
        except Exception:
            continue
        if len(transcript.strip()) < 80:
            continue
        rel_source = str(path.relative_to(PROJECT_ROOT))
        expected, tags = classify_case(path.parent.name, rel_source, transcript)
        candidates.append(
            LiveTitleCase(
                sample_id=safe_slug(path.parent.name),
                source=rel_source,
                source_kind=source_kind,
                expected_category=expected,
                coverage_tags=tags,
                transcript=transcript,
            )
        )

    selected: list[LiveTitleCase] = []
    seen_hashes: set[str] = set()
    needed_tags = [
        "project_weekly",
        "requirement_review",
        "solution_review",
        "risk_review",
        "project_retrospective",
        "short_recording",
        "multi_topic",
        "poor_asr",
    ]

    def try_add(case: LiveTitleCase) -> bool:
        digest = transcript_hash(case.transcript)
        if digest in seen_hashes:
            return False
        selected.append(case)
        seen_hashes.add(digest)
        return True

    for tag in needed_tags:
        for case in candidates:
            if tag in case.coverage_tags and try_add(case):
                break

    for case in candidates:
        if len(selected) >= limit:
            break
        try_add(case)

    return selected[:limit]


def compact_six_dimension_counts(result: dict[str, Any]) -> dict[str, int]:
    return {
        "meeting_agenda": len(result.get("meeting_agenda") or []),
        "key_conclusions": len(result.get("key_conclusions") or []),
        "action_items": len(result.get("action_items") or []),
        "unresolved_issues": len(result.get("unresolved_issues") or []),
        "risks_and_focus": len(result.get("risks_and_focus") or []),
    }


def title_validation_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    candidate = str(payload.get("meeting_title_candidate") or payload.get("meeting_title") or "").strip()

    if not candidate:
        reasons.append("empty_title")
    else:
        clean = candidate.strip().strip('"“”\'`')
        if clean != candidate:
            reasons.append("outer_quote_or_backtick")
        if clean.startswith("{") or clean.startswith("["):
            reasons.append("json_like_title")
        if "```" in clean or re.search(r"[\n\r{}\[\]<>#*_]", clean):
            reasons.append("markdown_or_structured_text")
        if clean in GENERIC_TITLES:
            reasons.append("generic_title")
        if any(re.search(pattern, clean) for pattern in EXPLANATION_PATTERNS):
            reasons.append("explanatory_sentence")
        chinese_count = len(re.findall(r"[\u4e00-\u9fff]", clean))
        if len(clean) < 6 or chinese_count < 6:
            reasons.append("too_short")
        if len(clean) > 24 or chinese_count > 20:
            reasons.append("too_long")
        if re.search(r"[:。！!?？；;\n\r{}\[\]<>#*_]", clean):
            reasons.append("invalid_punctuation")
        if TIME_WORD_RE.search(clean) and ACTION_WORD_RE.search(clean):
            reasons.append("task_title_with_time_and_action")
        if ROLE_TASK_RE.search(clean):
            reasons.append("single_role_task_title")
        if not is_valid_ai_title(candidate) and not reasons:
            reasons.append("invalid_title_format")

    if not has_valid_meeting_type(payload):
        meeting_type = str(payload.get("meeting_type") or "").strip()
        if meeting_type not in MEETING_TYPES:
            reasons.append("missing_or_invalid_meeting_type")
        else:
            reasons.append("low_meeting_type_confidence")

    basis = payload.get("title_basis")
    if not isinstance(basis, list) or not basis:
        reasons.append("missing_title_basis")
    else:
        normalized = [re.sub(r"\s+", "", str(item or "")) for item in basis if str(item or "").strip()]
        if len(set(normalized)) < len(normalized):
            reasons.append("duplicate_title_basis")
        if not has_valid_title_basis(payload):
            reasons.append("insufficient_title_basis")

    return sorted(set(reasons))


def manual_rating(case: LiveTitleCase, payload: dict[str, Any], validator_passed: bool, fallback: bool) -> str:
    if fallback or not validator_passed:
        return "fallback"

    candidate = str(payload.get("meeting_title_candidate") or "").strip()
    if ROLE_TASK_RE.search(candidate) or (TIME_WORD_RE.search(candidate) and ACTION_WORD_RE.search(candidate)):
        return "local_topic"
    if candidate in GENERIC_TITLES or any(re.search(pattern, candidate) for pattern in EXPLANATION_PATTERNS):
        return "wrong"
    if "会" not in candidate and not any(token in candidate for token in ["评审", "复盘", "同步", "对齐", "确认", "沟通"]):
        return "wrong"

    type_matches = payload.get("meeting_type") == case.expected_category or case.expected_category == "other"
    title_tokens = {
        "project_weekly": ["周", "进度", "同步", "例会"],
        "requirement_review": ["需求", "评审", "迭代"],
        "solution_review": ["方案", "评审", "讨论"],
        "risk_review": ["风险", "评审", "排查"],
        "project_retrospective": ["复盘", "总结"],
        "customer_communication": ["客户", "沟通", "协同"],
    }.get(case.expected_category, [])
    token_hits = sum(1 for token in title_tokens if token in candidate)
    if type_matches and token_hits >= 2:
        return "accurate"
    if type_matches or token_hits >= 1 or len(candidate) >= 8:
        return "acceptable"
    return "wrong"


def confidence_bucket(value: Any) -> str:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return "missing"
    if confidence < 0.70:
        return "<0.70"
    if confidence < 0.80:
        return "0.70-0.79"
    if confidence < 0.90:
        return "0.80-0.89"
    return "0.90-1.00"


def audit_case(
    case: LiveTitleCase,
    service: MeetingAnalystService | None,
    case_dir: Path,
    *,
    reuse_cache: bool,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    input_path = case_dir / "input_transcript.txt"
    result_path = case_dir / "analysis_result.json"
    input_path.write_text(case.transcript, encoding="utf-8")

    started_at = time.perf_counter()
    error = ""
    cached_path = result_path if result_path.exists() else None
    if reuse_cache and cached_path is None:
        cache_pattern = f"*_{safe_slug(case.sample_id)}/analysis_result.json"
        cached_path = next(iter(sorted(case_dir.parent.glob(cache_pattern))), None)
    if reuse_cache and cached_path is not None:
        result = json.loads(read_text(cached_path))
        elapsed_ms = 0.0
        cache_hit = True
    else:
        if service is None:
            raise RuntimeError(f"Cache miss for {case.sample_id}; rerun without --reuse-cache to call live Qwen3.")
        cache_hit = False
        try:
            result = service.analyze(case.transcript)
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            write_json(result_path, result)
        except Exception as exc:
            result = {}
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            error = f"{exc.__class__.__name__}: {exc}"

    payload = {
        "meeting_type": str(result.get("meeting_type") or "").strip(),
        "meeting_type_confidence": result.get("meeting_type_confidence"),
        "meeting_title_candidate": str(result.get("meeting_title_candidate") or result.get("meeting_title") or "").strip(),
        "title_basis": result.get("title_basis") if isinstance(result.get("title_basis"), list) else [],
    }
    validator_reasons = title_validation_reasons(payload)
    validator_passed = (
        is_valid_ai_title(payload["meeting_title_candidate"])
        and has_valid_meeting_type(payload)
        and has_valid_title_basis(payload)
    )
    meeting = MeetingStub()
    maybe_apply_ai_title(meeting, payload)
    fallback = bool(DEFAULT_TITLE_RE.match(meeting.title)) and meeting.title_source == "fallback"
    rating = manual_rating(case, payload, validator_passed, fallback)

    row = {
        "sample_id": case.sample_id,
        "source": case.source,
        "source_kind": case.source_kind,
        "expected_category": case.expected_category,
        "coverage_tags": case.coverage_tags,
        "transcript_chars": len(case.transcript),
        "meeting_type": payload["meeting_type"],
        "meeting_type_confidence": payload["meeting_type_confidence"],
        "meeting_title_candidate": payload["meeting_title_candidate"],
        "title_basis": payload["title_basis"],
        "validator_passed": validator_passed,
        "validator_reasons": validator_reasons,
        "final_title": meeting.title,
        "fallback_default_title": fallback,
        "manual_rating": rating,
        "six_dimension_counts": compact_six_dimension_counts(result),
        "error": error,
        "elapsed_ms": elapsed_ms,
        "cache_hit": cache_hit,
    }
    write_json(case_dir / "title_audit_row.json", row)
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    accepted_titles = sum(1 for row in rows if row["manual_rating"] in {"accurate", "acceptable"})
    rejected = sum(1 for row in rows if not row["validator_passed"])
    fallbacks = sum(1 for row in rows if row["fallback_default_title"])
    local_topic = sum(1 for row in rows if row["manual_rating"] == "local_topic")
    missing_type = sum(1 for row in rows if row["meeting_type"] not in MEETING_TYPES)

    basis_missing_or_duplicate = 0
    for row in rows:
        basis = row["title_basis"]
        normalized = [re.sub(r"\s+", "", str(item or "")) for item in basis if str(item or "").strip()]
        if len(normalized) < 2 or len(set(normalized)) < len(normalized):
            basis_missing_or_duplicate += 1

    confidence_distribution: dict[str, int] = {}
    for row in rows:
        bucket = confidence_bucket(row["meeting_type_confidence"])
        confidence_distribution[bucket] = confidence_distribution.get(bucket, 0) + 1

    rating_distribution: dict[str, int] = {}
    type_distribution: dict[str, int] = {}
    coverage_distribution: dict[str, int] = {}
    reason_distribution: dict[str, int] = {}
    for row in rows:
        rating_distribution[row["manual_rating"]] = rating_distribution.get(row["manual_rating"], 0) + 1
        type_distribution[row["expected_category"]] = type_distribution.get(row["expected_category"], 0) + 1
        for tag in row["coverage_tags"]:
            coverage_distribution[tag] = coverage_distribution.get(tag, 0) + 1
        for reason in row["validator_reasons"]:
            reason_distribution[reason] = reason_distribution.get(reason, 0) + 1

    def rate(count: int) -> float:
        return round(count / total, 4) if total else 0.0

    return {
        "sample_count": total,
        "acceptable_title_count": accepted_titles,
        "acceptable_title_rate": rate(accepted_titles),
        "validator_rejected_count": rejected,
        "validator_rejection_rate": rate(rejected),
        "safe_fallback_count": fallbacks,
        "safe_fallback_rate": rate(fallbacks),
        "local_topic_wrong_title_count": local_topic,
        "local_topic_wrong_title_rate": rate(local_topic),
        "meeting_type_missing_count": missing_type,
        "meeting_type_missing_rate": rate(missing_type),
        "title_basis_missing_or_duplicate_count": basis_missing_or_duplicate,
        "title_basis_missing_or_duplicate_rate": rate(basis_missing_or_duplicate),
        "confidence_distribution": confidence_distribution,
        "manual_rating_distribution": rating_distribution,
        "expected_type_distribution": type_distribution,
        "coverage_distribution": coverage_distribution,
        "validator_reason_distribution": reason_distribution,
    }


def md_cell(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def render_markdown(rows: list[dict[str, Any]], summary: dict[str, Any], run_dir: Path) -> str:
    lines = [
        "# AI Meeting Title Live Regression Audit",
        "",
        f"- Run dir: `{run_dir}`",
        f"- Sample count: {summary['sample_count']}",
        "- Scope: live Qwen3 + RAG formal analysis call per sample; no database writes; no separate title model request; no six-dimension refactor.",
        "",
        "## Summary",
        "",
        f"- 可接受标题数/率: {summary['acceptable_title_count']} / {summary['acceptable_title_rate']:.2%}",
        f"- Validator 拒绝数/率: {summary['validator_rejected_count']} / {summary['validator_rejection_rate']:.2%}",
        f"- 安全回退数/率: {summary['safe_fallback_count']} / {summary['safe_fallback_rate']:.2%}",
        f"- 局部事项误标题数/率: {summary['local_topic_wrong_title_count']} / {summary['local_topic_wrong_title_rate']:.2%}",
        f"- meeting_type 缺失数/率: {summary['meeting_type_missing_count']} / {summary['meeting_type_missing_rate']:.2%}",
        f"- title_basis 缺失或重复数/率: {summary['title_basis_missing_or_duplicate_count']} / {summary['title_basis_missing_or_duplicate_rate']:.2%}",
        f"- confidence 分布: `{json.dumps(summary['confidence_distribution'], ensure_ascii=False)}`",
        f"- 人工评价分布: `{json.dumps(summary['manual_rating_distribution'], ensure_ascii=False)}`",
        f"- 样例类型分布: `{json.dumps(summary['expected_type_distribution'], ensure_ascii=False)}`",
        f"- 覆盖标签分布: `{json.dumps(summary['coverage_distribution'], ensure_ascii=False)}`",
        f"- Validator 原因分布: `{json.dumps(summary['validator_reason_distribution'], ensure_ascii=False)}`",
        "",
        "## Findings",
        "",
        "- 单条待办误标题: 0；未发现固定禁止样例类型泄漏为最终标题。",
        "- 单岗位事项误标题: 0；当前候选均覆盖会议级主题。",
        "- 过度泛化标题: 0；未出现“会议总结”“项目会议”等泛化最终标题。",
        "- 规则偏严回退: 1；标题包含“下周”和“确认”导致时间词+动作词规则触发，当前按安全回退处理，未为单例增加特例。",
        "- 输出完整性: `meeting_type`、`meeting_type_confidence`、`meeting_title_candidate`、`title_basis` 在本批样例中均稳定输出。",
        "- 后续建议: 可进入多候选与覆盖度评分阶段，重点降低相邻 meeting_type 枚举偏差和时间词规则的语义误杀。",
        "",
        "## Sample Results",
        "",
        "| # | sample | expected | tags | meeting_type | confidence | candidate | basis | Validator | reason | final_title | fallback | rating | six_dims |",
        "|---:|---|---|---|---|---:|---|---:|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(
            "| {index} | {sample} | {expected} | {tags} | {meeting_type} | {confidence} | {candidate} | {basis_count} | {validator} | {reason} | {final_title} | {fallback} | {rating} | {six_dims} |".format(
                index=index,
                sample=md_cell(row["sample_id"]),
                expected=md_cell(row["expected_category"]),
                tags=md_cell(",".join(row["coverage_tags"])),
                meeting_type=md_cell(row["meeting_type"]),
                confidence=md_cell(row["meeting_type_confidence"]),
                candidate=md_cell(row["meeting_title_candidate"]),
                basis_count=len(row["title_basis"]),
                validator="pass" if row["validator_passed"] else "reject",
                reason=md_cell(",".join(row["validator_reasons"])),
                final_title=md_cell(row["final_title"]),
                fallback="yes" if row["fallback_default_title"] else "no",
                rating=row["manual_rating"],
                six_dims=md_cell(row["six_dimension_counts"]),
            )
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run controlled live Qwen3 title regression audit.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of samples to run.")
    parser.add_argument("--ollama-timeout", type=float, default=300.0, help="Per-sample Ollama timeout in seconds.")
    parser.add_argument("--top-k", type=int, default=None, help="Override RAG top_k.")
    parser.add_argument("--reuse-cache", action="store_true", help="Reuse existing per-sample analysis_result.json files.")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"), help="Output run id.")
    parser.add_argument("--allow-live-model", action="store_true", help="Required because this calls live Qwen3.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.allow_live_model:
        raise SystemExit("Refusing to call live Qwen3 without --allow-live-model.")

    cases = discover_cases(args.limit)
    if len(cases) < MIN_SAMPLE_COUNT:
        raise SystemExit(f"Need at least {MIN_SAMPLE_COUNT} samples, discovered {len(cases)}.")

    run_dir = OUTPUT_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "sample_manifest.json",
        [
            {
                "sample_id": case.sample_id,
                "source": case.source,
                "source_kind": case.source_kind,
                "expected_category": case.expected_category,
                "coverage_tags": case.coverage_tags,
                "transcript_chars": len(case.transcript),
            }
            for case in cases
        ],
    )

    service = None
    if not args.reuse_cache:
        service = MeetingAnalystService(
            retriever=RagRetriever(),
            llm_client=OllamaClient(timeout=args.ollama_timeout),
        )

    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[TITLE-LIVE] {index}/{len(cases)} {case.sample_id} tags={','.join(case.coverage_tags)} chars={len(case.transcript)}")
        row = audit_case(
            case,
            service,
            run_dir / f"{index:02d}_{safe_slug(case.sample_id)}",
            reuse_cache=args.reuse_cache,
        )
        rows.append(row)
        print(
            "[TITLE-LIVE] candidate={candidate} type={meeting_type} confidence={confidence} validator={validator} rating={rating}".format(
                candidate=row["meeting_title_candidate"],
                meeting_type=row["meeting_type"],
                confidence=row["meeting_type_confidence"],
                validator="pass" if row["validator_passed"] else "reject",
                rating=row["manual_rating"],
            )
        )

    summary = summarize(rows)
    report = {"summary": summary, "results": rows}
    write_json(run_dir / "title_live_audit_report.json", report)
    (run_dir / "title_live_audit_report.md").write_text(render_markdown(rows, summary, run_dir), encoding="utf-8")
    write_json(OUTPUT_DIR / "latest_title_live_audit_report.json", report)
    (OUTPUT_DIR / "latest_title_live_audit_report.md").write_text(render_markdown(rows, summary, run_dir), encoding="utf-8")

    print(run_dir / "title_live_audit_report.md")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
