"""Offline evaluator for meeting-analysis-v1 JSON outputs.

This script compares a human expected result with an already-generated actual
result. It never imports Worker runtime modules and never calls external
services.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "eval" / "reports" / "baseline_v1.0_RC1.md"

CANONICAL_FIELDS = (
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
)

EVIDENCE_FIELDS = (
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
)

TEXT_KEYS_BY_FIELD = {
    "meeting_agenda": ("item", "title", "summary"),
    "key_conclusions": ("conclusion", "item", "summary"),
    "action_items": ("task", "description", "item"),
    "unresolved_issues": ("issue", "question", "item"),
    "risks_and_focus": ("risk", "focus_area", "item"),
}


@dataclass(frozen=True)
class EvalItem:
    field: str
    index: int
    text: str
    source_text: str
    raw: Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_text(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)


def flatten_transcript(transcript: Any) -> str:
    if transcript is None:
        return ""
    if isinstance(transcript, str):
        return transcript
    if isinstance(transcript, list):
        parts = []
        for item in transcript:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(transcript)


def unwrap_result(payload: dict[str, Any], preferred_key: str) -> dict[str, Any]:
    value = payload.get(preferred_key)
    if isinstance(value, dict):
        return value
    return payload


def extract_metadata(*payloads: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for payload in payloads:
        if isinstance(payload.get("evaluation_metadata"), dict):
            metadata.update(payload["evaluation_metadata"])
        result_meta = payload.get("metadata")
        if isinstance(result_meta, dict):
            metadata.update(
                {
                    "model": result_meta.get("model_name") or metadata.get("model"),
                    "prompt_version": result_meta.get("prompt_version") or metadata.get("prompt_version"),
                    "rag_version": (
                        result_meta.get("rag_dataset_version")
                        or result_meta.get("rag_collection_name")
                        or metadata.get("rag_version")
                    ),
                }
            )
    return metadata


def item_text(field: str, item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    for key in TEXT_KEYS_BY_FIELD.get(field, ("item",)):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def source_text(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("source_text")
        if isinstance(value, str):
            return value
    return ""


def list_items(result: dict[str, Any], field: str) -> list[EvalItem]:
    value = result.get(field, [])
    if field == "meeting_summary" and isinstance(value, str):
        return [EvalItem(field, 0, value, "", value)] if value.strip() else []
    if not isinstance(value, list):
        return []
    items: list[EvalItem] = []
    for index, raw in enumerate(value):
        text = item_text(field, raw)
        if normalize_text(text):
            items.append(EvalItem(field, index, text, source_text(raw), raw))
    return items


def matches(expected: EvalItem, actual: EvalItem) -> bool:
    expected_text = normalize_text(expected.text)
    actual_text = normalize_text(actual.text)
    if not expected_text or not actual_text:
        return False
    return expected_text in actual_text or actual_text in expected_text


def count_matches(expected_items: list[EvalItem], actual_items: list[EvalItem]) -> int:
    unused = set(range(len(actual_items)))
    matched = 0
    for expected in expected_items:
        for actual_index in list(unused):
            if matches(expected, actual_items[actual_index]):
                unused.remove(actual_index)
                matched += 1
                break
    return matched


def precision(expected_items: list[EvalItem], actual_items: list[EvalItem]) -> float:
    if not actual_items:
        return 1.0 if not expected_items else 0.0
    matched = count_matches(expected_items, actual_items)
    return matched / len(actual_items)


def recall(expected_items: list[EvalItem], actual_items: list[EvalItem]) -> float:
    if not expected_items:
        return 1.0
    matched = count_matches(expected_items, actual_items)
    return matched / len(expected_items)


def has_continuous_evidence(item: EvalItem, transcript_text: str) -> bool:
    evidence = normalize_text(item.source_text)
    transcript = normalize_text(transcript_text)
    return bool(evidence and transcript and evidence in transcript)


def evaluate_results(
    expected_result: dict[str, Any],
    actual_result: dict[str, Any],
    transcript: Any = "",
) -> dict[str, Any]:
    transcript_text = flatten_transcript(transcript)
    expected_decisions = list_items(expected_result, "key_conclusions")
    actual_decisions = list_items(actual_result, "key_conclusions")
    expected_tasks = list_items(expected_result, "action_items")
    actual_tasks = list_items(actual_result, "action_items")
    expected_risks = list_items(expected_result, "risks_and_focus")
    actual_risks = list_items(actual_result, "risks_and_focus")

    evidence_items: list[EvalItem] = []
    for field in EVIDENCE_FIELDS:
        evidence_items.extend(list_items(actual_result, field))

    covered_evidence = [
        item for item in evidence_items if has_continuous_evidence(item, transcript_text)
    ]
    hallucinated_items = [
        item
        for item in evidence_items
        if not has_continuous_evidence(item, transcript_text)
    ]

    evidence_denominator = len(evidence_items)
    evidence_coverage = (
        len(covered_evidence) / evidence_denominator if evidence_denominator else 1.0
    )
    hallucination_rate = (
        len(hallucinated_items) / evidence_denominator if evidence_denominator else 0.0
    )

    missing_fields = [field for field in CANONICAL_FIELDS if field not in actual_result]

    return {
        "schema": {
            "compatible_with": "meeting-analysis-v1",
            "missing_canonical_fields": missing_fields,
            "passed": not missing_fields,
        },
        "metrics": {
            "decision_precision": round(precision(expected_decisions, actual_decisions), 4),
            "task_recall": round(recall(expected_tasks, actual_tasks), 4),
            "risk_recall": round(recall(expected_risks, actual_risks), 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "evidence_coverage": round(evidence_coverage, 4),
        },
        "counts": {
            "expected_decisions": len(expected_decisions),
            "actual_decisions": len(actual_decisions),
            "expected_tasks": len(expected_tasks),
            "actual_tasks": len(actual_tasks),
            "expected_risks": len(expected_risks),
            "actual_risks": len(actual_risks),
            "actual_evidence_items": evidence_denominator,
            "evidence_covered_items": len(covered_evidence),
            "hallucinated_items": len(hallucinated_items),
        },
        "details": {
            "hallucinated_items": [
                {
                    "field": item.field,
                    "index": item.index,
                    "text": item.text,
                    "source_text": item.source_text,
                }
                for item in hallucinated_items
            ]
        },
    }


def render_markdown_report(
    evaluation: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    metrics = evaluation["metrics"]
    counts = evaluation["counts"]
    schema = evaluation["schema"]
    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        "# AI Meeting Analysis Baseline v1.0 RC1",
        "",
        f"- Model: {metadata.get('model') or metadata.get('model_name') or 'unknown'}",
        f"- Prompt Version: {metadata.get('prompt_version') or 'unknown'}",
        f"- RAG Version: {metadata.get('rag_version') or metadata.get('rag_dataset_version') or 'unknown'}",
        f"- Generated At: {generated_at}",
        f"- Schema Compatibility: {'PASS' if schema['passed'] else 'FAIL'}",
        "",
        "## Metrics Result",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Decision Precision | {metrics['decision_precision']:.4f} |",
        f"| Task Recall | {metrics['task_recall']:.4f} |",
        f"| Risk Recall | {metrics['risk_recall']:.4f} |",
        f"| Hallucination Rate | {metrics['hallucination_rate']:.4f} |",
        f"| Evidence Coverage | {metrics['evidence_coverage']:.4f} |",
        "",
        "## Counts",
        "",
        "| Count | Value |",
        "| --- | ---: |",
    ]

    for key, value in counts.items():
        lines.append(f"| {key} | {value} |")

    if schema["missing_canonical_fields"]:
        lines.extend(
            [
                "",
                "## Schema Gaps",
                "",
                ", ".join(schema["missing_canonical_fields"]),
            ]
        )

    hallucinated_items = evaluation["details"]["hallucinated_items"]
    if hallucinated_items:
        lines.extend(["", "## Unsupported Evidence Items", ""])
        for item in hallucinated_items:
            lines.append(f"- {item['field']}[{item['index']}]: {item['text']}")

    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate expected and actual meeting-analysis-v1 JSON files."
    )
    parser.add_argument("expected", type=Path, help="Path to expected.json")
    parser.add_argument("actual", type=Path, help="Path to actual.json")
    parser.add_argument("--transcript", type=Path, help="Optional transcript text or JSON file")
    parser.add_argument("--metadata", type=Path, help="Optional evaluation metadata JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown report path")
    parser.add_argument("--json-output", type=Path, help="Optional machine-readable JSON report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected_payload = load_json(args.expected)
    actual_payload = load_json(args.actual)
    metadata_payload = load_json(args.metadata) if args.metadata else {}

    transcript: Any = ""
    if args.transcript:
        if args.transcript.suffix.lower() == ".json":
            transcript = load_json(args.transcript).get("transcript", "")
        else:
            transcript = load_text(args.transcript)
    else:
        transcript = (
            expected_payload.get("transcript")
            or actual_payload.get("transcript")
            or metadata_payload.get("transcript")
            or ""
        )

    expected_result = unwrap_result(expected_payload, "expected_result")
    actual_result = unwrap_result(actual_payload, "actual_result")
    metadata = extract_metadata(metadata_payload, expected_payload, actual_payload)

    evaluation = evaluate_results(expected_result, actual_result, transcript)
    report = render_markdown_report(evaluation, metadata)
    write_report(args.output, report)

    if args.json_output:
        write_report(
            args.json_output,
            json.dumps({"metadata": metadata, **evaluation}, ensure_ascii=False, indent=2),
        )

    print(f"Evaluation report written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
