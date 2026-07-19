import sys
import json
import time
import traceback
from pathlib import Path
from typing import Any
from collections import Counter


PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from services.worker.app.meeting_analyst_service import analyze_meeting


EVAL_CASES_DIR = PROJECT_ROOT / "data" / "eval" / "meetings"
REPORT_DIR = PROJECT_ROOT / "data" / "eval" / "reports"

BASELINE_REPORT_FILE = REPORT_DIR / "eval_report_baseline.json"
LATEST_REPORT_FILE = REPORT_DIR / "eval_report_latest.json"


REQUIRED_FIELDS = [
    "meeting_agenda",
    "meeting_summary",
    "key_conclusions",
    "action_items",
    "unresolved_issues",
    "risks_and_focus",
]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)

    remove_chars = [
        " ", "\n", "\t", "\r",
        "，", "。", "！", "？", "；", "：", "、",
        "“", "”", "‘", "’", "'", '"',
        "（", "）", "(", ")", "【", "】", "[", "]",
        "《", "》", "「", "」", "『", "』", "…", ".",
    ]

    text = value.lower()

    for char in remove_chars:
        text = text.replace(char, "")

    return text


def flatten_field(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return " ".join(flatten_field(item) for item in value)

    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(flatten_field(item))
        return " ".join(parts)

    return str(value)


def contains_keyword(value: Any, keyword: str) -> bool:
    return normalize_text(keyword) in normalize_text(flatten_field(value))


def find_keyword_locations(result: dict, keyword: str) -> list[dict]:
    """
    must_not_include 只检查 forbidden 是否被模型当成：
    1. 核心结论
    2. 待办任务

    不检查：
    - meeting_summary
    - unresolved_issues
    - risks_and_focus
    - source_text

    因为“目前没有建立自动预警机制”作为遗留问题证据是正确的，
    不能被误判为 forbidden。
    """

    locations = []

    check_targets = []

    for index, item in enumerate(result.get("key_conclusions", [])):
        check_targets.append(
            (
                "key_conclusions",
                index,
                item.get("conclusion", ""),
            )
        )

    for index, item in enumerate(result.get("action_items", [])):
        check_targets.append(
            (
                "action_items",
                index,
                item.get("task", ""),
            )
        )

    for field, index, text in check_targets:
        if contains_keyword(text, keyword):
            locations.append(
                {
                    "field": field,
                    "index": index,
                    "matched_text": text,
                }
            )

    return locations


def load_eval_cases() -> list[dict]:
    if not EVAL_CASES_DIR.exists():
        raise FileNotFoundError(f"Eval directory not found: {EVAL_CASES_DIR}")

    files = sorted(EVAL_CASES_DIR.glob("*.json"))

    if not files:
        raise RuntimeError(f"No eval JSON files found in: {EVAL_CASES_DIR}")

    cases = []

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            case = json.load(f)

        case["_file"] = file_path.name
        cases.append(case)

    return cases


def check_schema(result: dict) -> dict:
    missing_fields = [field for field in REQUIRED_FIELDS if field not in result]

    return {
        "passed": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


def evaluate_must_include(result: dict, expected: dict) -> dict:
    must_include = expected.get("must_include", {})

    total = 0
    passed = 0
    missing_items = []

    for field, keywords in must_include.items():
        actual_value = result.get(field)

        for keyword in keywords:
            total += 1

            if contains_keyword(actual_value, keyword):
                passed += 1
            else:
                missing_items.append({
                    "field": field,
                    "keyword": keyword,
                    "actual_field_value": actual_value,
                })

    score = passed / total if total else 1.0

    return {
        "total": total,
        "passed": passed,
        "score": round(score, 4),
        "missing_items": missing_items,
    }


def evaluate_must_not_include(result: dict, expected: dict) -> dict:
    forbidden_keywords = expected.get("must_not_include", [])

    total = len(forbidden_keywords)
    passed = 0
    forbidden_hits = []

    for keyword in forbidden_keywords:
        locations = find_keyword_locations(result, keyword)

        if locations:
            forbidden_hits.append({
                "keyword": keyword,
                "locations": locations,
            })
        else:
            passed += 1

    score = passed / total if total else 1.0

    return {
        "total": total,
        "passed": passed,
        "score": round(score, 4),
        "forbidden_hits": forbidden_hits,
    }


def count_needs_review(result: dict) -> dict:
    count = 0
    locations = []

    for field in [
        "key_conclusions",
        "action_items",
        "unresolved_issues",
        "risks_and_focus",
    ]:
        items = result.get(field, [])

        if not isinstance(items, list):
            continue

        for index, item in enumerate(items):
            if isinstance(item, dict) and item.get("needs_review") is True:
                count += 1
                locations.append({
                    "field": field,
                    "index": index,
                    "review_reason": item.get("review_reason"),
                    "item": item,
                })

    return {
        "count": count,
        "locations": locations,
    }


def detect_issue_action_conflict(result: dict) -> dict:
    action_items = result.get("action_items", [])
    unresolved_issues = result.get("unresolved_issues", [])

    shared_terms = [
        "差评关键词",
        "差评监控",
        "自动预警",
        "监控机制",
        "新品替换",
        "替代方案",
        "用户行为数据",
        "底层能力",
    ]

    conflicts = []

    for action in action_items:
        task = normalize_text(action.get("task", ""))

        for issue in unresolved_issues:
            issue_text = normalize_text(issue.get("issue", ""))

            for term in shared_terms:
                term_norm = normalize_text(term)

                if term_norm in task and term_norm in issue_text:
                    conflicts.append({
                        "type": "issue_to_action_conflict",
                        "term": term,
                        "action_item": action,
                        "unresolved_issue": issue,
                    })

    return {
        "count": len(conflicts),
        "conflicts": conflicts,
    }


def detect_error_types(case_result: dict) -> list[dict]:
    error_types = []

    for item in case_result.get("must_include", {}).get("missing_items", []):
        error_types.append({
            "type": "missing_must_include",
            "field": item["field"],
            "keyword": item["keyword"],
        })

    for item in case_result.get("must_not_include", {}).get("forbidden_hits", []):
        keyword = item["keyword"]

        error_type = "forbidden_output"

        if "建立" in keyword or "监控机制" in keyword:
            error_type = "issue_auto_converted_to_action"
        elif "取消个性化推荐" in keyword or "短视频素材工具V2.0" in keyword:
            error_type = "cross_meeting_hallucination"
        else:
            error_type = "forbidden_output"

        error_types.append({
            "type": error_type,
            "keyword": keyword,
            "locations": item["locations"],
        })

    for item in case_result.get("needs_review", {}).get("locations", []):
        error_types.append({
            "type": "needs_review",
            "reason": item.get("review_reason"),
            "field": item.get("field"),
            "item": item.get("item"),
        })

    for item in case_result.get("issue_action_conflict", {}).get("conflicts", []):
        error_types.append({
            "type": "issue_to_action_conflict",
            "term": item.get("term"),
            "action_item": item.get("action_item"),
            "unresolved_issue": item.get("unresolved_issue"),
        })

    return error_types


def evaluate_case(case: dict) -> dict:
    case_id = case["case_id"]
    domain = case.get("domain")
    transcript = case["transcript"]
    expected = case.get("expected", {})

    print()
    print("=" * 80)
    print(f"[CASE] {case_id}")
    print(f"[DOMAIN] {domain}")
    print("=" * 80)

    started_at = time.time()

    try:
        result = analyze_meeting(transcript)
        elapsed = round(time.time() - started_at, 2)

        schema_check = check_schema(result)
        include_eval = evaluate_must_include(result, expected)
        exclude_eval = evaluate_must_not_include(result, expected)
        review_eval = count_needs_review(result)
        conflict_eval = detect_issue_action_conflict(result)

        passed = (
            schema_check["passed"]
            and include_eval["score"] >= 0.70
            and exclude_eval["score"] == 1.0
            and conflict_eval["count"] == 0
        )

        case_result = {
            "case_id": case_id,
            "domain": domain,
            "file": case.get("_file"),
            "status": "success",
            "passed": passed,
            "elapsed_seconds": elapsed,
            "schema": schema_check,
            "must_include": include_eval,
            "must_not_include": exclude_eval,
            "needs_review": review_eval,
            "issue_action_conflict": conflict_eval,
            "result": result,
        }

        case_result["error_types"] = detect_error_types(case_result)

        print(f"[RESULT] {'PASS' if passed else 'FAIL'}")
        print(f"[MUST INCLUDE] {include_eval['passed']}/{include_eval['total']}")
        print(f"[MUST NOT INCLUDE] {exclude_eval['passed']}/{exclude_eval['total']}")
        print(f"[MISSING ITEMS] {len(include_eval['missing_items'])}")
        print(f"[FORBIDDEN HITS] {len(exclude_eval['forbidden_hits'])}")
        print(f"[NEEDS REVIEW] {review_eval['count']}")
        print(f"[ISSUE -> ACTION CONFLICT] {conflict_eval['count']}")
        print(f"[TIME] {elapsed}s")

        if include_eval["missing_items"]:
            print("[MISSING DETAIL]")
            for item in include_eval["missing_items"]:
                print(f"  - {item['field']}: {item['keyword']}")

        if exclude_eval["forbidden_hits"]:
            print("[FORBIDDEN DETAIL]")
            for item in exclude_eval["forbidden_hits"]:
                print(f"  - {item['keyword']}")
                for loc in item["locations"]:
                    print(f"    field={loc['field']}, index={loc['index']}")

        return case_result

    except Exception as exc:
        elapsed = round(time.time() - started_at, 2)

        print(f"[ERROR] {exc}")
        traceback.print_exc()

        return {
            "case_id": case_id,
            "domain": domain,
            "file": case.get("_file"),
            "status": "error",
            "passed": False,
            "elapsed_seconds": elapsed,
            "error": str(exc),
            "error_types": [
                {
                    "type": "runtime_error",
                    "message": str(exc),
                }
            ],
        }


def build_summary(case_results: list[dict]) -> dict:
    total = len(case_results)

    success_cases = [
        item for item in case_results
        if item["status"] == "success"
    ]

    passed_cases = [
        item for item in case_results
        if item.get("passed") is True
    ]

    failed_cases = [
        item for item in case_results
        if item.get("passed") is not True
    ]

    schema_passed = sum(
        1 for item in success_cases
        if item["schema"]["passed"]
    )

    total_include = sum(
        item["must_include"]["total"]
        for item in success_cases
    )

    passed_include = sum(
        item["must_include"]["passed"]
        for item in success_cases
    )

    total_exclude = sum(
        item["must_not_include"]["total"]
        for item in success_cases
    )

    passed_exclude = sum(
        item["must_not_include"]["passed"]
        for item in success_cases
    )

    needs_review_count = sum(
        item["needs_review"]["count"]
        for item in success_cases
    )

    issue_action_conflicts = sum(
        item["issue_action_conflict"]["count"]
        for item in success_cases
    )

    error_counter = Counter()

    for item in case_results:
        for error in item.get("error_types", []):
            error_counter[error["type"]] += 1

    field_missing_counter = Counter()

    for item in success_cases:
        for missing in item["must_include"]["missing_items"]:
            field_missing_counter[missing["field"]] += 1

    forbidden_counter = Counter()

    for item in success_cases:
        for forbidden in item["must_not_include"]["forbidden_hits"]:
            forbidden_counter[forbidden["keyword"]] += 1

    schema_rate = schema_passed / len(success_cases) if success_cases else 0
    include_recall = passed_include / total_include if total_include else 0
    exclude_accuracy = passed_exclude / total_exclude if total_exclude else 0
    pass_rate = len(passed_cases) / total if total else 0

    return {
        "total_cases": total,
        "successful_runs": len(success_cases),
        "passed_cases": len(passed_cases),
        "failed_cases": len(failed_cases),
        "pass_rate": round(pass_rate, 4),
        "schema_complete_rate": round(schema_rate, 4),
        "must_include_recall": round(include_recall, 4),
        "must_not_include_accuracy": round(exclude_accuracy, 4),
        "needs_review_count": needs_review_count,
        "issue_action_conflict_count": issue_action_conflicts,
        "top_error_types": error_counter.most_common(10),
        "top_missing_fields": field_missing_counter.most_common(10),
        "top_forbidden_keywords": forbidden_counter.most_common(10),
        "failed_case_ids": [
            item["case_id"] for item in failed_cases
        ],
    }


def save_report(path: Path, case_results: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "summary": build_summary(case_results),
        "cases": case_results,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    print()
    print("========== MEETING ANALYST BATCH EVALUATION ==========")
    print(f"Cases directory: {EVAL_CASES_DIR}")

    cases = load_eval_cases()

    print(f"Loaded cases: {len(cases)}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    case_results = []

    for index, case in enumerate(cases, start=1):
        print()
        print(f"Running {index}/{len(cases)}")

        case_result = evaluate_case(case)
        case_results.append(case_result)

        save_report(LATEST_REPORT_FILE, case_results)

    save_report(BASELINE_REPORT_FILE, case_results)
    save_report(LATEST_REPORT_FILE, case_results)

    summary = build_summary(case_results)

    print()
    print("=" * 80)
    print("FINAL EVALUATION SUMMARY")
    print("=" * 80)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print()
    print(f"Baseline report saved to: {BASELINE_REPORT_FILE}")
    print(f"Latest report saved to:   {LATEST_REPORT_FILE}")


if __name__ == "__main__":
    main()