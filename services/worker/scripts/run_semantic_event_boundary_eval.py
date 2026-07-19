from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]

for path in (PROJECT_ROOT, WORKER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.semantic_event_extractor import SemanticEventExtractor  # noqa: E402
from app.semantic_event_schema import UtteranceInput  # noqa: E402

FIXTURE_PATH = WORKER_ROOT / "tests" / "fixtures" / "semantic_event_boundary_cases.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "debug" / "semantic_event_boundary_eval"
INTENTS = [
    "agenda_statement",
    "progress_update",
    "decision",
    "proposal",
    "commitment",
    "task_assignment",
    "question",
    "open_issue",
    "risk_warning",
    "requirement",
    "rejection",
    "information",
    "non_event",
]


class BoundaryDeterministicClient:
    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        payload = _extract_payload(prompt)
        text = payload["current_utterance"]["source_text"]
        speaker = payload["current_utterance"].get("speaker")
        return json.dumps({"events": _predict_events(text, speaker)}, ensure_ascii=False)


def _extract_payload(prompt: str) -> dict[str, Any]:
    marker = "\n输入：\n"
    if marker in prompt:
        return json.loads(prompt.split(marker, 1)[1])
    start = prompt.find("{")
    end = prompt.rfind("}")
    return json.loads(prompt[start : end + 1])


def _event(text: str, intent: str, status: str = "unknown", owner: str | None = None, deadline: str | None = None) -> dict[str, Any]:
    return {
        "normalized_text": text,
        "primary_intent": intent,
        "secondary_intents": [],
        "event_type": status,
        "subject": owner,
        "action": None,
        "object": None,
        "entities": {
            "persons": [owner] if owner else [],
            "teams": [],
            "projects": [],
            "features": [],
            "dates": [deadline] if deadline else [],
            "versions": re.findall(r"V\d+(?:\.\d+)?", text),
            "numbers": re.findall(r"\d+(?:\.\d+)?%?", text),
        },
        "attributes": {
            "owner": owner,
            "deadline": deadline,
            "priority": "high" if "必须" in text or "极高" in text else "unknown",
            "status": status,
            "polarity": "negative" if any(k in text for k in ["风险", "失败", "无法", "延期"]) else "neutral",
            "certainty": "explicit",
        },
        "evidence": {"source_text": text, "quote": text},
        "confidence": {"intent": 0.9, "entity": 0.85, "overall": 0.88},
        "needs_review": False,
    }


def _predict_events(text: str, speaker: str | None) -> list[dict[str, Any]]:
    stripped = re.sub(r"[\s，,。.!！?？、]+", "", text)
    if stripped in {"大家好", "我补充一下", "无问题", "无异议", "好的", "会议结束"}:
        return [_event(text, "non_event")]
    if "大家有没有问题" in text:
        return [_event(text, "non_event")]

    events: list[dict[str, Any]] = []
    if any(k in text for k in ["今天主要", "本次会议控制", "接下来请"]):
        events.append(_event(text, "agenda_statement", "discussing"))
    if any(k in text for k in ["已经完成", "目前只支持", "反馈", "出现", "加载慢", "不完整"]):
        events.append(_event(text, "information"))
    if any(k in text for k in ["我建议", "可以考虑", "是不是可以"]):
        events.append(_event(text, "proposal", "proposed"))
    if any(k in text for k in ["同意", "就这么定", "决定", "确认"]):
        ev = _event(text, "decision", "confirmed")
        if any(k in text for k in ["砍掉", "不上线", "暂缓"]):
            ev["secondary_intents"] = ["rejection"]
        events.append(ev)
    elif any(k in text for k in ["不做", "否决", "不上线"]):
        events.append(_event(text, "rejection", "rejected"))
    if any(k in text for k in ["我会", "我负责", "我后续跟进"]):
        deadline = "今天" if "今天" in text else None
        events.append(_event(text, "commitment", "confirmed", owner=speaker, deadline=deadline))
    if "由测试负责" in text:
        events.append(_event(text, "task_assignment", "confirmed", owner="测试", deadline="周五前" if "周五" in text else None))
    if "张三" in text:
        events.append(_event(text, "task_assignment", "confirmed", owner="张三", deadline="明天" if "明天" in text else None))
    if any(k in text for k in ["能不能", "有没有", "是否需要"]):
        events.append(_event(text, "question", "discussing"))
    if any(k in text for k in ["没有容错方案", "还没确认", "无法继续", "没有测试账号", "无法开始", "先记录"]):
        events.append(_event(text, "open_issue", "blocked"))
    if any(k in text for k in ["风险", "如果", "一旦", "可能导致", "可能延期"]):
        events.append(_event(text, "risk_warning", "pending"))
    if any(k in text for k in ["必须", "需要"]):
        events.append(_event(text, "requirement", "confirmed"))
    if not events:
        events.append(_event(text, "information"))
    return events[:3]


def read_cases(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_cases(cases: list[dict[str, Any]], live: bool) -> dict[str, Any]:
    extractor = SemanticEventExtractor(llm_client=None if live else BoundaryDeterministicClient())
    raw_outputs: list[dict[str, Any]] = []
    before_validation: list[dict[str, Any]] = []
    after_validation: list[dict[str, Any]] = []
    failed_cases: list[dict[str, Any]] = []
    durations: list[float] = []
    retry_count = 0
    validator_fix_count = 0

    for case in cases:
        started = time.perf_counter()
        utterance = UtteranceInput(
            utterance_id=case["case_id"],
            segment_id=case["case_id"],
            speaker="发言人A",
            speaker_role=None,
            text=case["text"],
            context=case.get("context_before", []),
            topic=case.get("category"),
        )
        try:
            events, summaries, debug = extractor.extract_with_debug(utterance)
            duration = time.perf_counter() - started
            durations.append(duration)
            retry_count += debug.retry_count
            validator_fix_count += sum(1 for item in summaries if item.changed)
            raw_outputs.append(
                {
                    "case_id": case["case_id"],
                    "text": case["text"],
                    "raw_output": debug.raw_output,
                    "bypass_reason": debug.bypass_reason,
                    "failure_reason": debug.failure_reason,
                    "seconds": round(duration, 4),
                }
            )
            before_validation.append(
                {
                    "case_id": case["case_id"],
                    "expected": _expected_payload(case),
                    "events": debug.parsed_before_validation or [],
                }
            )
            after_validation.append(
                {
                    "case_id": case["case_id"],
                    "expected": _expected_payload(case),
                    "validation_changes": [s.reasons or [] for s in summaries],
                    "events": [event.model_dump(mode="json") for event in events],
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed_cases.append({"case_id": case["case_id"], "text": case["text"], "error": str(exc)})

    report = build_report(cases, after_validation, failed_cases, durations, retry_count, validator_fix_count, live)
    return {
        "raw_model_outputs": raw_outputs,
        "before_validation": before_validation,
        "after_validation": after_validation,
        "failed_cases": failed_cases,
        "report": report,
    }


def _expected_payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed_primary_intents": case["allowed_primary_intents"],
        "forbidden_primary_intents": case["forbidden_primary_intents"],
        "expected_event_count": case["expected_event_count"],
        "expected_owner": case["expected_owner"],
        "expected_deadline": case["expected_deadline"],
        "expected_status": case["expected_status"],
        "expected_needs_review": case["expected_needs_review"],
    }


def build_report(
    cases: list[dict[str, Any]],
    after_validation: list[dict[str, Any]],
    failed_cases: list[dict[str, Any]],
    durations: list[float],
    retry_count: int,
    validator_fix_count: int,
    live: bool,
) -> dict[str, Any]:
    by_id = {item["case_id"]: item["events"] for item in after_validation}
    true_counter = Counter()
    pred_counter = Counter()
    tp_counter = Counter()
    category_counter: dict[str, Counter] = defaultdict(Counter)
    failures: list[dict[str, Any]] = []

    correct_primary = 0
    evaluated = 0
    schema_ok = len(cases) - len(failed_cases)
    non_event_total = 0
    non_event_correct = 0
    flow_misclassified = 0
    proposal_as_decision = 0
    question_as_open_issue = 0
    normal_problem_as_risk = 0
    multi_total = 0
    multi_correct = 0
    owner_hallucination = 0
    deadline_hallucination = 0
    source_ok = 0
    evidence_ok = 0
    source_total = 0

    for case in cases:
        expected_intents = set(case["allowed_primary_intents"])
        forbidden = set(case["forbidden_primary_intents"])
        expected_primary = case["allowed_primary_intents"][0]
        for intent in set(case["allowed_primary_intents"]):
            true_counter[intent] += 1
        events = by_id.get(case["case_id"], [])
        if expected_primary == "non_event":
            non_event_total += 1
        if not events:
            failures.append(_failure_record(case, None, "no_event"))
            continue

        evaluated += 1
        predicted_intents = [event.get("primary_intent") for event in events]
        first_intent = predicted_intents[0]
        for intent in set(predicted_intents):
            pred_counter[intent] += 1
        category_counter[case["category"]]["total"] += 1

        primary_ok = any(intent in expected_intents for intent in predicted_intents)
        if primary_ok:
            correct_primary += 1
            category_counter[case["category"]]["correct"] += 1
        else:
            failures.append(_failure_record(case, events, "intent_mismatch"))
        for intent in set(predicted_intents).intersection(expected_intents):
            tp_counter[intent] += 1

        if expected_primary == "non_event" and first_intent == "non_event":
            non_event_correct += 1
        if expected_primary == "non_event" and first_intent != "non_event":
            flow_misclassified += 1
        if "proposal" in expected_intents and "decision" in predicted_intents:
            proposal_as_decision += 1
        if "question" in expected_intents and "open_issue" in predicted_intents:
            question_as_open_issue += 1
        if "risk_warning" in forbidden and "risk_warning" in predicted_intents:
            normal_problem_as_risk += 1

        if case["expected_event_count"] > 1:
            multi_total += 1
            predicted_set = set(predicted_intents)
            if len(events) >= case["expected_event_count"] and expected_intents.issubset(predicted_set):
                multi_correct += 1
            else:
                failures.append(_failure_record(case, events, "multi_event_split_mismatch"))

        for event in events:
            source_total += 1
            if event.get("source_text") == case["text"]:
                source_ok += 1
            evidence_source = (event.get("evidence") or {}).get("source_text")
            if evidence_source == case["text"] or (isinstance(evidence_source, str) and evidence_source in case["text"]):
                evidence_ok += 1
            owner = (event.get("attributes") or {}).get("owner")
            if owner and owner != case.get("expected_owner") and owner not in case["text"] and not any(owner in c for c in case.get("context_before", [])):
                owner_hallucination += 1
            deadline = (event.get("attributes") or {}).get("deadline")
            if deadline and deadline != case.get("expected_deadline") and deadline not in case["text"] and not any(deadline in c for c in case.get("context_before", [])):
                deadline_hallucination += 1

    per_intent = {}
    f1_values = []
    for label in INTENTS:
        tp = tp_counter[label]
        precision = tp / pred_counter[label] if pred_counter[label] else 0.0
        recall = tp / true_counter[label] if true_counter[label] else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        if true_counter[label]:
            f1_values.append(f1)
        per_intent[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": true_counter[label],
        }

    return {
        "mode": "live_model_evaluation" if live else "pipeline_test",
        "model": "qwen3:14b" if live else "deterministic_client",
        "case_count": len(cases),
        "schema_valid_rate": round(schema_ok / len(cases), 4) if cases else 0,
        "primary_intent_accuracy": round(correct_primary / evaluated, 4) if evaluated else 0,
        "per_intent": per_intent,
        "per_category_accuracy": {
            category: round(counter["correct"] / counter["total"], 4) if counter["total"] else 0
            for category, counter in category_counter.items()
        },
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0,
        "non_event_accuracy": round(non_event_correct / non_event_total, 4) if non_event_total else 0,
        "flow_phrase_misclassification_rate": round(flow_misclassified / non_event_total, 4) if non_event_total else 0,
        "proposal_as_decision_rate": round(proposal_as_decision / evaluated, 4) if evaluated else 0,
        "question_as_open_issue_rate": round(question_as_open_issue / evaluated, 4) if evaluated else 0,
        "normal_problem_as_risk_rate": round(normal_problem_as_risk / evaluated, 4) if evaluated else 0,
        "multi_event_split_correct_rate": round(multi_correct / multi_total, 4) if multi_total else 0,
        "owner_hallucination_rate": round(owner_hallucination / source_total, 4) if source_total else 0,
        "deadline_hallucination_rate": round(deadline_hallucination / source_total, 4) if source_total else 0,
        "source_text_consistency_rate": round(source_ok / source_total, 4) if source_total else 0,
        "evidence_consistency_rate": round(evidence_ok / source_total, 4) if source_total else 0,
        "avg_seconds_per_utterance": round(sum(durations) / len(durations), 4) if durations else 0,
        "total_seconds": round(sum(durations), 4),
        "json_repair_retry_count": retry_count,
        "validator_fix_count": validator_fix_count,
        "model_call_failure_count": len(failed_cases),
        "failure_or_disputed_cases": failures[:20],
    }


def _failure_record(case: dict[str, Any], events: list[dict[str, Any]] | None, reason: str) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "text": case["text"],
        "reason": reason,
        "expected": _expected_payload(case),
        "actual": events or [],
    }


def run_stability(cases: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    selected = cases[:limit]
    all_runs: list[list[tuple[Any, ...]]] = []
    raw_runs: list[dict[str, Any]] = []
    for run_index in range(3):
        result = run_cases(selected, live=True)
        run_values = []
        for item in result["after_validation"]:
            events = item["events"]
            first = events[0] if events else {}
            attrs = first.get("attributes") or {}
            run_values.append(
                (
                    first.get("primary_intent"),
                    len(events),
                    attrs.get("owner"),
                    attrs.get("deadline"),
                    attrs.get("status"),
                )
            )
        all_runs.append(run_values)
        raw_runs.append({"run_index": run_index + 1, "report": result["report"]})

    total = len(selected)
    return {
        "sample_count": total,
        "repeat_count": 3,
        "primary_intent_consistency_rate": _consistency(all_runs, 0, total),
        "event_count_consistency_rate": _consistency(all_runs, 1, total),
        "owner_consistency_rate": _consistency(all_runs, 2, total),
        "deadline_consistency_rate": _consistency(all_runs, 3, total),
        "status_consistency_rate": _consistency(all_runs, 4, total),
        "exact_match_rate": _exact_consistency(all_runs, total),
        "runs": raw_runs,
    }


def _consistency(runs: list[list[tuple[Any, ...]]], index: int, total: int) -> float:
    if not total:
        return 0.0
    same = 0
    for case_index in range(total):
        values = {run[case_index][index] for run in runs if case_index < len(run)}
        if len(values) == 1:
            same += 1
    return round(same / total, 4)


def _exact_consistency(runs: list[list[tuple[Any, ...]]], total: int) -> float:
    if not total:
        return 0.0
    same = 0
    for case_index in range(total):
        values = {run[case_index] for run in runs if case_index < len(run)}
        if len(values) == 1:
            same += 1
    return round(same / total, 4)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--skip-stability", action="store_true")
    parser.add_argument("--stability-limit", type=int, default=15)
    args = parser.parse_args()

    cases = read_cases(Path(args.fixture))
    output_dir = Path(args.output_dir)

    pipeline = run_cases(cases, live=False)
    live = run_cases(cases, live=True)
    stability = None if args.skip_stability else run_stability(cases, args.stability_limit)

    final_report = {
        "pipeline_test": pipeline["report"],
        "live_model_evaluation": live["report"],
        "stability_test": stability,
        "conclusion_basis": "live_model_evaluation_only",
    }

    write_json(output_dir / "pipeline_raw_outputs.json", pipeline["raw_model_outputs"])
    write_json(output_dir / "pipeline_before_validation.json", pipeline["before_validation"])
    write_json(output_dir / "pipeline_after_validation.json", pipeline["after_validation"])
    write_json(output_dir / "pipeline_failed_cases.json", pipeline["failed_cases"])
    write_json(output_dir / "live_raw_model_outputs.json", live["raw_model_outputs"])
    write_json(output_dir / "live_before_validation.json", live["before_validation"])
    write_json(output_dir / "live_after_validation.json", live["after_validation"])
    write_json(output_dir / "live_failed_cases.json", live["failed_cases"])
    write_json(output_dir / "semantic_event_boundary_report.json", final_report)

    print(json.dumps(final_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
