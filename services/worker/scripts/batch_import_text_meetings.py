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
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_FILE.parents[3]
WORKER_ROOT = SCRIPT_FILE.parents[1]
API_ROOT = PROJECT_ROOT / "services" / "api"


def configure_worker_import_path() -> None:
    preferred_paths = [str(WORKER_ROOT), str(PROJECT_ROOT)]
    sys.path = preferred_paths + [entry for entry in sys.path if entry not in preferred_paths]

    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if module_name == "app" or module_name.startswith("app."):
            if module_file and Path(module_file).resolve().is_relative_to(API_ROOT):
                del sys.modules[module_name]


configure_worker_import_path()

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


DEBUG_SOURCE = "text_debug"
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "debug" / "batch_meetings" / "input"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "batch_meetings" / "output"
TITLE_MARKER = "【会议标题】"
CONTENT_MARKER = "【会议内容】"
SPEAKER_RE = re.compile(r"^\s*([^:：\n]{1,32})\s*[:：]\s*(.*)$")


@dataclass(frozen=True)
class ParsedUtterance:
    speaker: str
    text: str


@dataclass(frozen=True)
class ParsedMeetingText:
    title: str
    utterances: list[ParsedUtterance]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch import txt meeting transcripts and run the existing AI analysis workflow.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Directory containing *.txt meeting transcripts.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for timestamped import reports.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of txt files to import.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete previous debug meetings created by this script before importing.",
    )
    parser.add_argument("--model", default=None, help="Override OLLAMA_MODEL for this import run.")
    return parser.parse_args()


def configure_model(model: str | None) -> None:
    if model:
        os.environ["OLLAMA_MODEL"] = model


def import_app_modules() -> dict[str, Any]:
    from sqlalchemy import delete, select

    from app.database import SessionLocal
    from app.models import ActionItem, AudioFile, Meeting, MeetingChunk, MeetingSummary, TranscriptSegment
    from app.config import get_settings
    from app.analysis_contract import ensure_non_empty_analysis_result
    from app.summary_agent import summarize_meeting

    return {
        "delete": delete,
        "select": select,
        "SessionLocal": SessionLocal,
        "ActionItem": ActionItem,
        "AudioFile": AudioFile,
        "Meeting": Meeting,
        "MeetingChunk": MeetingChunk,
        "MeetingSummary": MeetingSummary,
        "TranscriptSegment": TranscriptSegment,
        "get_settings": get_settings,
        "ensure_non_empty_analysis_result": ensure_non_empty_analysis_result,
        "summarize_meeting": summarize_meeting,
    }


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8")


def parse_meeting_text(path: Path) -> ParsedMeetingText:
    raw_text = read_text_file(path).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in raw_text.split("\n")]
    title = extract_title(lines) or path.stem
    content_lines = lines_after_content_marker(lines)
    utterances = parse_utterances(content_lines)
    if not utterances:
        raise ValueError("No speaker utterances found. Expected lines like 'speaker:' followed by content.")
    return ParsedMeetingText(title=title, utterances=utterances)


def extract_title(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if line.strip() == TITLE_MARKER:
            for candidate in lines[index + 1 :]:
                title = candidate.strip()
                if title and title not in {CONTENT_MARKER, TITLE_MARKER}:
                    return title
            return ""
    return ""


def lines_after_content_marker(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if line.strip() == CONTENT_MARKER:
            return lines[index + 1 :]
    return lines


def parse_utterances(lines: list[str]) -> list[ParsedUtterance]:
    utterances: list[ParsedUtterance] = []
    current_speaker: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_speaker, current_parts
        if current_speaker is None:
            current_parts = []
            return
        text = normalize_utterance_text(current_parts)
        if text:
            utterances.append(ParsedUtterance(speaker=current_speaker, text=text))
        current_speaker = None
        current_parts = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line in {TITLE_MARKER, CONTENT_MARKER}:
            continue
        speaker_match = SPEAKER_RE.match(line)
        if speaker_match:
            flush()
            current_speaker = speaker_match.group(1).strip()
            inline_text = speaker_match.group(2).strip()
            current_parts = [inline_text] if inline_text else []
            continue
        if current_speaker is not None:
            current_parts.append(line)
    flush()
    return utterances


def normalize_utterance_text(parts: list[str]) -> str:
    text = "\n".join(part.strip() for part in parts if part.strip())
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def segment_times(index: int, text: str) -> tuple[float, float]:
    start = float(index * 10)
    duration = max(4.0, min(18.0, len(text) / 12))
    return start, round(start + duration, 2)


def create_debug_meeting(db: Any, modules: dict[str, Any], parsed: ParsedMeetingText) -> str:
    Meeting = modules["Meeting"]
    TranscriptSegment = modules["TranscriptSegment"]

    now = datetime.now(timezone.utc)
    meeting = Meeting(
        id=str(uuid.uuid4()),
        title=parsed.title[:255],
        title_source=DEBUG_SOURCE,
        status="transcribed",
        created_at=now,
        updated_at=now,
    )
    db.add(meeting)
    db.flush()

    speaker_labels: dict[str, str] = {}
    for index, utterance in enumerate(parsed.utterances):
        speaker_label = speaker_labels.setdefault(utterance.speaker, f"Speaker {len(speaker_labels) + 1}")
        start_time, end_time = segment_times(index, utterance.text)
        db.add(
            TranscriptSegment(
                meeting_id=meeting.id,
                audio_file_id=None,
                segment_index=index,
                start_time=start_time,
                end_time=end_time,
                text=utterance.text,
                speaker_label=speaker_label,
                speaker_name=utterance.speaker,
            )
        )

    db.commit()
    return str(meeting.id)


def cleanup_debug_meetings(db: Any, modules: dict[str, Any]) -> int:
    select = modules["select"]
    delete = modules["delete"]
    Meeting = modules["Meeting"]
    TranscriptSegment = modules["TranscriptSegment"]
    MeetingSummary = modules["MeetingSummary"]
    ActionItem = modules["ActionItem"]
    MeetingChunk = modules["MeetingChunk"]
    AudioFile = modules["AudioFile"]

    meeting_ids = list(db.scalars(select(Meeting.id).where(Meeting.title_source == DEBUG_SOURCE)).all())
    if not meeting_ids:
        return 0

    for model in (ActionItem, MeetingSummary, MeetingChunk, TranscriptSegment, AudioFile):
        db.execute(delete(model).where(model.meeting_id.in_(meeting_ids)))
    db.execute(delete(Meeting).where(Meeting.id.in_(meeting_ids)))
    db.commit()
    return len(meeting_ids)


def summary_contract_payload(summary: Any, action_items: list[Any] | None = None) -> dict[str, Any]:
    return {
        "meeting_summary": summary.meeting_summary or summary.overview or "",
        "meeting_agenda": summary.meeting_agenda or summary.agenda or [],
        "key_conclusions": summary.key_conclusions or summary.decisions or [],
        "action_items": action_items or [],
        "unresolved_issues": summary.unresolved_issues or summary.open_questions or [],
        "risks_and_focus": summary.risks_and_focus or summary.risks or [],
    }


def summary_field_counts(summary: Any, action_items: list[Any] | None = None) -> dict[str, int]:
    payload = summary_contract_payload(summary, action_items)
    return {
        "meeting_summary_chars": len(payload["meeting_summary"]),
        "meeting_agenda": len(payload["meeting_agenda"]),
        "key_conclusions": len(payload["key_conclusions"]),
        "action_items": len(payload["action_items"]),
        "unresolved_issues": len(payload["unresolved_issues"]),
        "risks_and_focus": len(payload["risks_and_focus"]),
    }


def verify_completed_summary(db: Any, modules: dict[str, Any], meeting_id: str, summary_id: str) -> dict[str, int]:
    MeetingSummary = modules["MeetingSummary"]
    ActionItem = modules["ActionItem"]
    select = modules["select"]
    ensure_non_empty_analysis_result = modules["ensure_non_empty_analysis_result"]

    db.expire_all()
    summary = db.get(MeetingSummary, summary_id)
    if summary is None or summary.meeting_id != meeting_id:
        raise RuntimeError("empty_analysis_result: summary row was not persisted for imported meeting")
    action_items = list(db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id)).all())
    payload = summary_contract_payload(summary, action_items)
    ensure_non_empty_analysis_result(payload)
    return summary_field_counts(summary, action_items)


def mark_import_analysis_failed(db: Any, modules: dict[str, Any], meeting_id: str | None) -> None:
    if not meeting_id:
        return
    Meeting = modules["Meeting"]
    meeting = db.get(Meeting, meeting_id)
    if meeting is not None:
        meeting.status = "summary_failed"
        db.commit()


def import_one(db: Any, modules: dict[str, Any], path: Path) -> dict[str, Any]:
    started_at = time.perf_counter()
    report: dict[str, Any] = {
        "meeting_id": None,
        "filename": path.name,
        "status": "failed",
        "analysis_status": "not_started",
        "error": None,
        "summary_field_counts": None,
    }
    try:
        parsed = parse_meeting_text(path)
        meeting_id = create_debug_meeting(db, modules, parsed)
        report["meeting_id"] = meeting_id
        report["status"] = "imported"

        summary = modules["summarize_meeting"](db, meeting_id)
        report["summary_id"] = summary.id
        report["summary_field_counts"] = verify_completed_summary(db, modules, meeting_id, summary.id)
        report["status"] = "completed"
        report["analysis_status"] = "completed"
    except Exception as exc:
        db.rollback()
        mark_import_analysis_failed(db, modules, report["meeting_id"])
        report["status"] = "failed"
        report["analysis_status"] = "failed" if report["meeting_id"] else "not_started"
        report["error"] = f"{exc.__class__.__name__}: {exc}"
    finally:
        report["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
    return report


def write_report(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "import_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    configure_model(args.model)
    modules = import_app_modules()

    input_dir = Path(args.input_dir)
    output_root = Path(args.output_root)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_id

    files = sorted(input_dir.glob("*.txt"))
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be greater than 0")
        files = files[: args.limit]

    report: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": DEBUG_SOURCE,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "model": modules["get_settings"]().ollama_model,
        "cleanup": {"enabled": bool(args.cleanup), "deleted_count": 0},
        "meetings": [],
    }

    SessionLocal = modules["SessionLocal"]
    db = SessionLocal()
    try:
        if args.cleanup:
            report["cleanup"]["deleted_count"] = cleanup_debug_meetings(db, modules)
        for path in files:
            report["meetings"].append(import_one(db, modules, path))
    finally:
        db.close()

    report["total_count"] = len(report["meetings"])
    report["completed_count"] = sum(1 for item in report["meetings"] if item.get("status") == "completed")
    report["failed_count"] = sum(1 for item in report["meetings"] if item.get("status") == "failed")
    write_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
