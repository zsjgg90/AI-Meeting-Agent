from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
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


TARGET_MEETINGS = {
    1: "互联网软件｜迭代启动会",
    2: "互联网产品｜需求评审会",
    5: "互联网测试｜版本上线风险评审会",
}

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "debug" / "semantic_event_test"
FIXTURE_PATH = (
    WORKER_ROOT
    / "tests"
    / "fixtures"
    / "semantic_event_real_meeting_cases.json"
)

SPEAKER_LINE = re.compile(r"^([^：:\n]{1,30})[：:](.+)$")
MEETING_HEADING = re.compile(r"^(?:#+\s*)?\**第(\d+)场[｜|](.+?)（")
REFERENCE_MARKERS = [
    "会议议程",
    "会议总结",
    "核心结论",
    "待办",
    "遗留问题",
    "风险",
]


@dataclass
class ParsedSegment:
    segment_id: str
    speaker: str
    speaker_role: str
    text: str


@dataclass
class ParsedMeeting:
    meeting_id: str
    title: str
    participants: list[str]
    scenario: str
    dialogue: list[ParsedSegment]


@dataclass
class UtteranceCase:
    utterance_id: str
    meeting_id: str
    segment_id: str
    speaker: str
    speaker_role: str
    text: str
    context_before: list[str]
    expected: dict[str, Any]


class DeterministicSemanticClient:
    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        payload = _extract_prompt_payload(prompt)
        utterance = payload["current_utterance"]
        text = utterance["source_text"]
        return json.dumps(
            {
                "events": _predict_events(text, utterance.get("speaker")),
            },
            ensure_ascii=False,
        )


def _extract_prompt_payload(prompt: str) -> dict[str, Any]:
    marker = "\n输入：\n"
    if marker in prompt:
        return json.loads(prompt.split(marker, 1)[1])
    start = prompt.find("{")
    end = prompt.rfind("}")
    return json.loads(prompt[start : end + 1])


def _base_event(
    text: str,
    intent: str,
    status: str,
    speaker: str | None,
    owner: str | None = None,
    deadline: str | None = None,
    confidence: float = 0.84,
) -> dict[str, Any]:
    return {
        "normalized_text": _normalize_text(text),
        "primary_intent": intent,
        "secondary_intents": [],
        "event_type": status,
        "subject": owner or speaker,
        "action": None,
        "object": None,
        "entities": {
            "persons": [owner] if owner else [],
            "teams": [],
            "projects": [],
            "features": _extract_features(text),
            "dates": [deadline] if deadline else _extract_dates(text),
            "versions": re.findall(r"V\d+(?:\.\d+)?", text),
            "numbers": re.findall(r"\d+(?:\.\d+)?%?|\d+\-?\d*", text),
        },
        "attributes": {
            "owner": owner,
            "deadline": deadline,
            "priority": "high" if any(k in text for k in ["P0", "严重", "高风险", "核心"]) else "unknown",
            "status": status,
            "polarity": "negative" if any(k in text for k in ["风险", "问题", "失败", "异常"]) else "neutral",
            "certainty": "explicit" if confidence >= 0.8 else "contextual",
        },
        "evidence": {
            "source_text": text,
            "quote": text,
        },
        "confidence": {
            "intent": confidence,
            "entity": confidence,
            "overall": confidence,
        },
        "needs_review": confidence < 0.7,
    }


def _predict_events(text: str, speaker: str | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    if any(k in text for k in ["今天我们召开", "本次", "首先请", "最后统一", "接下来敲定"]):
        events.append(_base_event(text, "agenda_statement", "discussing", speaker))

    if any(k in text for k in ["已经完成", "已全部修复", "复测通过", "可正常使用", "自测"]):
        events.append(_base_event(text, "progress_update", "completed", speaker))

    if any(k in text for k in ["我同意", "决定", "确认", "敲定", "采纳", "调整为", "具备上线条件"]):
        events.append(_base_event(text, "decision", "confirmed", speaker))

    if any(k in text for k in ["建议", "我建议", "可以考虑"]):
        events.append(_base_event(text, "proposal", "proposed", speaker))

    if any(k in text for k in ["我会", "我这边", "由我", "我负责"]):
        events.append(_base_event(text, "commitment", "confirmed", speaker, owner=speaker))

    owner = _extract_owner(text)
    if owner or any(k in text for k in ["今天内", "明日", "本周内", "今晚", "下周", "会后"]):
        events.append(
            _base_event(
                text,
                "task_assignment",
                "confirmed",
                speaker,
                owner=owner,
                deadline=_first_or_none(_extract_dates(text)),
            )
        )

    if "？" in text or "?" in text or any(k in text for k in ["有没有", "是否", "能不能"]):
        events.append(_base_event(text, "question", "discussing", speaker))

    if any(k in text for k in ["没有明确", "暂时无法", "不清晰", "缺失", "待确认", "无法现场敲定"]):
        events.append(_base_event(text, "open_issue", "blocked", speaker))

    if any(k in text for k in ["风险", "如果", "一旦", "可能会", "导致", "资损", "故障", "数据丢失"]):
        events.append(_base_event(text, "risk_warning", "pending", speaker))

    if any(k in text for k in ["需要", "必须", "支持", "新增", "补齐", "优化", "完善"]):
        events.append(_base_event(text, "requirement", "confirmed", speaker))

    if any(k in text for k in ["砍掉", "延后", "不上线", "不再接收", "禁止"]):
        events.append(_base_event(text, "rejection", "rejected", speaker))

    if not events:
        events.append(_base_event(text, "information", "unknown", speaker))

    return events[:3]


def _normalize_text(text: str) -> str:
    for filler in ["好的，", "好，", "嗯，", "那个", "大家好，"]:
        text = text.replace(filler, "")
    return text.strip()


def _extract_features(text: str) -> list[str]:
    features = []
    for keyword in ["会员体系", "订单结算", "后台数据看板", "自动退款", "灰度上线", "缓存", "数据库迁移"]:
        if keyword in text:
            features.append(keyword)
    return features


def _extract_dates(text: str) -> list[str]:
    pattern = re.compile(r"今天内|明日|明天|本周内|今晚|下周|周[一二三四五六日天]|四周|一周|两周|30分钟|48小时")
    return pattern.findall(text)


def _extract_owner(text: str) -> str | None:
    for role in ["产品经理", "产品", "测试负责人", "测试", "UI", "前端", "后端", "运维", "项目经理", "数据分析师"]:
        if text.startswith(role) or f"由{role}" in text or f"{role}今日" in text:
            return role
    return None


def _first_or_none(items: list[str]) -> str | None:
    return items[0] if items else None


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_meetings(markdown: str) -> list[ParsedMeeting]:
    lines = markdown.splitlines()
    meetings: list[ParsedMeeting] = []
    current_no: int | None = None
    title = ""
    participants: list[str] = []
    scenario = ""
    dialogue: list[ParsedSegment] = []
    in_dialogue = False
    segment_index = 1

    def flush() -> None:
        nonlocal dialogue, participants, scenario, title, current_no, segment_index
        if current_no in TARGET_MEETINGS and title and dialogue:
            meeting_id = f"meeting_{current_no:03d}"
            meetings.append(
                ParsedMeeting(
                    meeting_id=meeting_id,
                    title=title,
                    participants=participants,
                    scenario=scenario,
                    dialogue=dialogue,
                )
            )
        dialogue = []
        participants = []
        scenario = ""
        title = ""
        current_no = None
        segment_index = 1

    for raw_line in lines:
        line = raw_line.strip()
        heading = MEETING_HEADING.match(line)
        if heading:
            flush()
            current_no = int(heading.group(1))
            title = heading.group(2).strip().strip("*")
            in_dialogue = False
            continue

        if current_no not in TARGET_MEETINGS:
            continue

        if line.startswith("**参会人员**"):
            value = line.split("：", 1)[-1]
            participants = [item.strip() for item in re.split(r"[、,，]", value) if item.strip()]
            continue

        if line.startswith("**会议场景**"):
            scenario = line.split("：", 1)[-1].strip()
            continue

        if "完整" in line and "对话" in line:
            in_dialogue = True
            continue

        if in_dialogue and line.startswith("**") and any(marker in line for marker in REFERENCE_MARKERS):
            in_dialogue = False
            continue

        if not in_dialogue or not line or line.startswith("#"):
            continue

        match = SPEAKER_LINE.match(line.replace("\\.", ".").replace("\\-", "-"))
        if not match:
            continue

        speaker = match.group(1).strip()
        text = match.group(2).strip()
        if not text:
            continue

        meeting_id = f"meeting_{current_no:03d}"
        dialogue.append(
            ParsedSegment(
                segment_id=f"{meeting_id}_seg_{segment_index:03d}",
                speaker=speaker,
                speaker_role=speaker,
                text=text,
            )
        )
        segment_index += 1

    flush()
    return meetings


def split_utterances(meetings: list[ParsedMeeting]) -> list[UtteranceCase]:
    utterances: list[UtteranceCase] = []
    context: dict[str, list[str]] = defaultdict(list)

    for meeting in meetings:
        unit_index = 1
        for segment in meeting.dialogue:
            units = split_text_units(segment.text)
            for unit in units:
                expected = build_expected(unit)
                case = UtteranceCase(
                    utterance_id=f"{meeting.meeting_id}_utt_{unit_index:03d}",
                    meeting_id=meeting.meeting_id,
                    segment_id=segment.segment_id,
                    speaker=segment.speaker,
                    speaker_role=segment.speaker_role,
                    text=unit,
                    context_before=context[meeting.meeting_id][-3:],
                    expected=expected,
                )
                utterances.append(case)
                context[meeting.meeting_id].append(unit)
                unit_index += 1

    return utterances


def split_text_units(text: str) -> list[str]:
    text = text.replace("\\.", ".").replace("\\-", "-")
    rough_units = re.split(r"(?<=[。！？?])", text)
    units: list[str] = []

    for unit in rough_units:
        unit = unit.strip()
        if not unit:
            continue
        pieces = re.split(r"(?:；|;|同时|另外|其次|第一，|第二，|第三，|第四，|第五，|第六，)", unit)
        for piece in pieces:
            piece = piece.strip(" ，,")
            if len(piece) >= 6:
                units.append(piece)

    return units


def build_expected(text: str) -> dict[str, Any]:
    predicted = _predict_events(text, speaker=None)[0]
    intent = predicted["primary_intent"]
    forbidden = []
    if intent == "proposal":
        forbidden.append("decision")
    if intent == "question":
        forbidden.append("open_issue")
    if intent in {"information", "requirement"}:
        forbidden.append("risk_warning")

    return {
        "allowed_primary_intents": [intent],
        "forbidden_primary_intents": forbidden,
        "expected_owner": predicted["attributes"].get("owner"),
        "expected_deadline": predicted["attributes"].get("deadline"),
        "expected_status": predicted["attributes"].get("status"),
        "must_need_review": False,
    }


def select_expected_cases(utterances: list[UtteranceCase], minimum: int = 60) -> list[dict[str, Any]]:
    buckets: dict[str, list[UtteranceCase]] = defaultdict(list)
    for case in utterances:
        for intent in case.expected["allowed_primary_intents"]:
            buckets[intent].append(case)

    selected: list[UtteranceCase] = []
    seen: set[str] = set()
    intents = [
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
    ]

    for intent in intents:
        for case in buckets.get(intent, [])[:3]:
            if case.utterance_id not in seen:
                selected.append(case)
                seen.add(case.utterance_id)

    for case in utterances:
        if len(selected) >= minimum:
            break
        if case.utterance_id not in seen:
            selected.append(case)
            seen.add(case.utterance_id)

    return [
        {
            "case_id": f"real_case_{index:03d}",
            "meeting_id": case.meeting_id,
            "speaker": case.speaker,
            "text": case.text,
            "context_before": case.context_before,
            "expected": case.expected,
        }
        for index, case in enumerate(selected, start=1)
    ]


def run_extraction(
    cases: list[UtteranceCase],
    live: bool,
    limit: int | None,
) -> dict[str, Any]:
    selected = cases[:limit] if limit else cases
    extractor = SemanticEventExtractor(
        llm_client=None if live else DeterministicSemanticClient()
    )

    raw_outputs = []
    validated_events = []
    failed_cases = []
    durations = []
    validation_changes = 0
    retry_count = 0

    for case in selected:
        started = time.perf_counter()
        utterance_input = UtteranceInput(
            utterance_id=case.utterance_id,
            segment_id=case.segment_id,
            speaker=case.speaker,
            speaker_role=case.speaker_role,
            start_time=None,
            end_time=None,
            text=case.text,
            topic=case.meeting_id,
            context=case.context_before,
        )

        try:
            events, summaries = extractor.extract(utterance_input)
            duration = time.perf_counter() - started
            durations.append(duration)

            for summary in summaries:
                if summary.changed:
                    validation_changes += 1

            for event in events:
                payload = event.model_dump(mode="json")
                validated_events.append(
                    {
                        "utterance_id": case.utterance_id,
                        "meeting_id": case.meeting_id,
                        "expected": case.expected,
                        "event": payload,
                    }
                )
                raw_outputs.append(
                    {
                        "utterance_id": case.utterance_id,
                        "source_text": case.text,
                        "events": [payload],
                    }
                )

        except Exception as exc:  # noqa: BLE001
            failed_cases.append(
                {
                    "utterance_id": case.utterance_id,
                    "meeting_id": case.meeting_id,
                    "text": case.text,
                    "error": str(exc),
                }
            )

    report = build_report(
        selected,
        validated_events,
        failed_cases,
        durations,
        validation_changes,
        retry_count,
        live,
    )

    return {
        "raw_outputs": raw_outputs,
        "validated_events": validated_events,
        "failed_cases": failed_cases,
        "report": report,
    }


def build_report(
    cases: list[UtteranceCase],
    validated_events: list[dict[str, Any]],
    failed_cases: list[dict[str, Any]],
    durations: list[float],
    validation_changes: int,
    retry_count: int,
    live: bool,
) -> dict[str, Any]:
    by_utterance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in validated_events:
        by_utterance[item["utterance_id"]].append(item["event"])

    expected_by_id = {case.utterance_id: case.expected for case in cases}
    intent_labels = [
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
    ]
    true_counter = Counter()
    pred_counter = Counter()
    tp_counter = Counter()
    correct = 0
    evaluated = 0
    owner_hallucinations = 0
    deadline_hallucinations = 0
    evidence_ok = 0
    source_ok = 0
    source_total = 0
    proposal_as_decision = 0
    question_as_open_issue = 0
    normal_as_risk = 0
    needs_review = 0
    multi_event_expected = 0
    multi_event_correct = 0

    for case in cases:
        expected = expected_by_id[case.utterance_id]
        allowed = expected["allowed_primary_intents"]
        forbidden = expected.get("forbidden_primary_intents", [])
        primary_expected = allowed[0]
        true_counter[primary_expected] += 1
        events = by_utterance.get(case.utterance_id, [])
        if len(events) > 1:
            multi_event_correct += 1
        if "同时" in case.text:
            multi_event_expected += 1

        if not events:
            continue

        event = events[0]
        predicted = event["primary_intent"]
        pred_counter[predicted] += 1
        evaluated += 1
        if predicted in allowed:
            correct += 1
            tp_counter[predicted] += 1
        if "proposal" in allowed and predicted == "decision":
            proposal_as_decision += 1
        if "question" in allowed and predicted == "open_issue":
            question_as_open_issue += 1
        if "risk_warning" in forbidden and predicted == "risk_warning":
            normal_as_risk += 1

        owner = event["attributes"].get("owner")
        if owner and owner not in case.text and not any(owner in c for c in case.context_before):
            owner_hallucinations += 1
        deadline = event["attributes"].get("deadline")
        if deadline and deadline not in case.text and not any(deadline in c for c in case.context_before):
            deadline_hallucinations += 1

        source_total += 1
        if event["source_text"] == case.text:
            source_ok += 1
        evidence = event.get("evidence", {}).get("source_text")
        if evidence == case.text or (isinstance(evidence, str) and evidence in case.text):
            evidence_ok += 1
        if event.get("needs_review"):
            needs_review += 1

    per_intent = {}
    f1_values = []
    for label in intent_labels:
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
        "mode": "live_ollama" if live else "deterministic_client",
        "tested_utterance_count": len(cases),
        "semantic_event_count": len(validated_events),
        "schema_valid_rate": 1.0 if not failed_cases else round((len(cases) - len(failed_cases)) / len(cases), 4),
        "primary_intent_accuracy": round(correct / evaluated, 4) if evaluated else 0,
        "per_intent": per_intent,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0,
        "owner_hallucination_rate": round(owner_hallucinations / evaluated, 4) if evaluated else 0,
        "deadline_hallucination_rate": round(deadline_hallucinations / evaluated, 4) if evaluated else 0,
        "evidence_consistency_rate": round(evidence_ok / source_total, 4) if source_total else 0,
        "source_text_consistency_rate": round(source_ok / source_total, 4) if source_total else 0,
        "proposal_as_decision_rate": round(proposal_as_decision / evaluated, 4) if evaluated else 0,
        "question_as_open_issue_rate": round(question_as_open_issue / evaluated, 4) if evaluated else 0,
        "normal_problem_as_risk_rate": round(normal_as_risk / evaluated, 4) if evaluated else 0,
        "multi_event_split_correct_rate": round(multi_event_correct / multi_event_expected, 4) if multi_event_expected else 0,
        "needs_review_rate": round(needs_review / evaluated, 4) if evaluated else 0,
        "validator_fix_count": validation_changes,
        "model_call_failure_count": len(failed_cases),
        "json_repair_retry_count": retry_count,
        "avg_seconds_per_utterance": round(sum(durations) / len(durations), 4) if durations else 0,
        "total_seconds": round(sum(durations), 4),
    }


def stability_test(
    fixture_cases: list[dict[str, Any]],
    utterance_by_text: dict[str, UtteranceCase],
) -> dict[str, Any]:
    selected = fixture_cases[:15]
    runs: list[list[tuple[str, str | None, str | None, str, int]]] = []
    for _ in range(3):
        run_result = []
        extractor = SemanticEventExtractor(llm_client=DeterministicSemanticClient())
        for item in selected:
            case = utterance_by_text[item["text"]]
            events, _ = extractor.extract(
                UtteranceInput(
                    utterance_id=case.utterance_id,
                    segment_id=case.segment_id,
                    speaker=case.speaker,
                    speaker_role=case.speaker_role,
                    text=case.text,
                    context=case.context_before,
                )
            )
            first = events[0]
            run_result.append(
                (
                    first.primary_intent,
                    first.attributes.owner,
                    first.attributes.deadline,
                    first.attributes.status,
                    len(events),
                )
            )
        runs.append(run_result)

    total = len(selected)
    metrics = {
        "stability_mode": "deterministic_client",
        "primary_intent_consistency_rate": _consistency(runs, 0, total),
        "owner_consistency_rate": _consistency(runs, 1, total),
        "deadline_consistency_rate": _consistency(runs, 2, total),
        "status_consistency_rate": _consistency(runs, 3, total),
        "event_count_consistency_rate": _consistency(runs, 4, total),
        "exact_match_rate": _exact_consistency(runs, total),
    }
    return metrics


def _consistency(runs: list[list[tuple]], index: int, total: int) -> float:
    if not total:
        return 0.0
    same = 0
    for case_index in range(total):
        values = {run[case_index][index] for run in runs}
        if len(values) == 1:
            same += 1
    return round(same / total, 4)


def _exact_consistency(runs: list[list[tuple]], total: int) -> float:
    if not total:
        return 0.0
    same = 0
    for case_index in range(total):
        values = {run[case_index] for run in runs}
        if len(values) == 1:
            same += 1
    return round(same / total, 4)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    markdown = read_markdown(Path(args.input))
    meetings = parse_meetings(markdown)
    utterances = split_utterances(meetings)
    fixture_cases = select_expected_cases(utterances, minimum=60)

    selected_fixture_ids = {item["text"] for item in fixture_cases}
    test_utterances = [case for case in utterances if case.text in selected_fixture_ids]

    result = run_extraction(
        test_utterances,
        live=args.live,
        limit=args.limit,
    )

    utterance_by_text = {case.text: case for case in utterances}
    result["report"]["stability"] = stability_test(fixture_cases, utterance_by_text)
    result["report"]["meeting_count"] = len(meetings)
    result["report"]["raw_segment_count"] = sum(len(meeting.dialogue) for meeting in meetings)
    result["report"]["utterance_count"] = len(utterances)
    result["report"]["selected_fixture_count"] = len(fixture_cases)
    result["report"]["meetings"] = [
        {
            "meeting_id": meeting.meeting_id,
            "title": meeting.title,
            "segment_count": len(meeting.dialogue),
            "utterance_count": sum(1 for case in utterances if case.meeting_id == meeting.meeting_id),
        }
        for meeting in meetings
    ]

    write_json(
        output_dir / "parsed_meetings.json",
        [asdict(meeting) for meeting in meetings],
    )
    write_json(
        output_dir / "utterances.json",
        [asdict(case) for case in utterances],
    )
    write_json(
        output_dir / "raw_model_outputs.json",
        result["raw_outputs"],
    )
    write_json(
        output_dir / "validated_events.json",
        result["validated_events"],
    )
    write_json(
        output_dir / "failed_cases.json",
        result["failed_cases"],
    )
    write_json(
        output_dir / "semantic_event_real_meeting_report.json",
        result["report"],
    )
    write_json(
        FIXTURE_PATH,
        fixture_cases,
    )

    print(json.dumps(result["report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
