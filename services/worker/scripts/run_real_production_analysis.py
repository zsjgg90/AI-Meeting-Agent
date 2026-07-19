from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
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


from app.analysis_contract import analysis_to_persistence_payload, normalize_meeting_analysis_result  # noqa: E402
from app.anti_hallucination_validator import validate_meeting_analysis  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.meeting_analyst_prompt import RAG_QUERY, build_meeting_analyst_prompt  # noqa: E402
from app.meeting_analyst_service import extract_json  # noqa: E402
from app.ollama_client import build_chat_url, build_ollama_format, build_ollama_options  # noqa: E402
from app.prompt_registry import get_meeting_analyst_prompt_spec  # noqa: E402
from app.rag_retriever import RagContext, RagRetriever  # noqa: E402
from app.transcript_builder import build_transcript_text  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "data" / "debug" / "semantic_event_test" / "live_sample" / "parsed_meetings.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "debug" / "real_production_analysis"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def log_line(path: Path, event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def load_meeting(input_path: Path, meeting_id: str) -> dict[str, Any]:
    meetings = json.loads(input_path.read_text(encoding="utf-8"))
    for meeting in meetings:
        if meeting.get("meeting_id") == meeting_id:
            return meeting
    raise ValueError(f"Meeting {meeting_id} not found in {input_path}")


def meeting_to_segments(meeting: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, item in enumerate(meeting.get("dialogue", []), start=1):
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        segment_id = item.get("segment_id") or f"{meeting['meeting_id']}_seg_{index:03d}"
        speaker = item.get("speaker") or item.get("speaker_role") or "Unknown Speaker"
        segments.append(
            {
                "id": segment_id,
                "speaker_name": speaker,
                "speaker_label": speaker,
                "start_time": float((index - 1) * 10),
                "end_time": float((index - 1) * 10 + 8),
                "text": text,
            }
        )
    return segments


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
        "text": rag_context.text,
    }


def call_ollama(prompt: str, timeout: float) -> tuple[dict[str, Any], float]:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是专业 AI Meeting Analyst。"
                    "你必须严格输出合法 JSON。"
                    "不要输出 Markdown。"
                    "不要输出解释或其他多余文本。"
                    "所有事实必须来自会议原文。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": build_ollama_options(),
    }
    response_format = build_ollama_format()
    if response_format:
        payload["format"] = response_format
    started_at = time.perf_counter()
    response = requests.post(
        build_chat_url(settings.ollama_base_url),
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json(), round((time.perf_counter() - started_at) * 1000, 2)


def run(meeting_id: str, input_path: Path, output_root: Path, timeout: float) -> dict[str, Any]:
    settings = get_settings()
    prompt_spec = get_meeting_analyst_prompt_spec()
    output_dir = output_root / meeting_id
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline_log = output_dir / "pipeline.log"
    if pipeline_log.exists():
        pipeline_log.unlink()

    root_logger = logging.getLogger("meeting_worker")
    file_handler = logging.FileHandler(pipeline_log, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(file_handler)

    total_started_at = time.perf_counter()
    try:
        meeting = load_meeting(input_path, meeting_id)
        segments = meeting_to_segments(meeting)
        transcript = build_transcript_text(segments)
        (output_dir / "input_transcript.txt").write_text(transcript, encoding="utf-8")
        log_line(
            pipeline_log,
            "real_production_analysis.started",
            meeting_id=meeting_id,
            title=meeting.get("title"),
            result_source="legacy_qwen_rag",
            transcript_chars=len(transcript),
            segment_count=len(segments),
            ollama_model=settings.ollama_model,
            ollama_timeout=timeout,
            ollama_options=build_ollama_options(),
            ollama_format=build_ollama_format(),
            rag_top_k=settings.rag_top_k,
        )

        rag_started_at = time.perf_counter()
        retriever = RagRetriever()
        rag_context = retriever.build_context_payload(query=RAG_QUERY, top_k=settings.rag_top_k)
        rag_payload = serialize_rag_context(rag_context)
        write_json(output_dir / "rag_context.json", rag_payload)
        log_line(
            pipeline_log,
            "rag.completed",
            duration_ms=round((time.perf_counter() - rag_started_at) * 1000, 2),
            rag_chunk_count=len(rag_context.chunk_ids),
            rag_context_chars=len(rag_context.text),
        )

        prompt = build_meeting_analyst_prompt(rag_context=rag_context.text, transcript=transcript)
        (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        log_line(
            pipeline_log,
            "prompt.built",
            prompt_chars=len(prompt),
            prompt_version=prompt_spec.prompt_version,
        )

        raw_response, ollama_duration_ms = call_ollama(prompt, timeout)
        raw_output = str(raw_response.get("message", {}).get("content") or "")
        write_json(
            output_dir / "model_raw_output.json",
            {
                "ollama_response": raw_response,
                "raw_output": raw_output,
                "ollama_duration_ms": ollama_duration_ms,
                "ollama_model": settings.ollama_model,
                "ollama_timeout": timeout,
                "ollama_options": build_ollama_options(),
                "ollama_format": build_ollama_format(),
            },
        )
        log_line(
            pipeline_log,
            "ollama.completed",
            ollama_model=settings.ollama_model,
            ollama_timeout=timeout,
            ollama_options=build_ollama_options(),
            ollama_format=build_ollama_format(),
            ollama_duration_ms=ollama_duration_ms,
        )

        parsed = extract_json(raw_output)
        validated = validate_meeting_analysis(parsed, transcript)
        validated["_metadata"] = {
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
        analysis = normalize_meeting_analysis_result(
            validated,
            model_name=f"{settings.ollama_model}+rag",
        )
        normalized = analysis_to_persistence_payload(analysis)
        write_json(output_dir / "normalized_result.json", normalized)

        total_duration_ms = round((time.perf_counter() - total_started_at) * 1000, 2)
        report = {
            "ok": True,
            "meeting_id": meeting_id,
            "result_source": "legacy_qwen_rag",
            "transcript_chars": len(transcript),
            "rag_chunk_count": len(rag_context.chunk_ids),
            "prompt_chars": len(prompt),
            "ollama_model": settings.ollama_model,
            "ollama_timeout": timeout,
            "ollama_options": build_ollama_options(),
            "ollama_format": build_ollama_format(),
            "ollama_duration_ms": ollama_duration_ms,
            "total_duration_ms": total_duration_ms,
            "failure_reason": None,
            "output_dir": str(output_dir),
        }
        log_line(pipeline_log, "real_production_analysis.completed", **report)
        return report
    except Exception as exc:
        total_duration_ms = round((time.perf_counter() - total_started_at) * 1000, 2)
        failure = {
            "ok": False,
            "meeting_id": meeting_id,
            "result_source": "legacy_qwen_rag",
            "transcript_chars": len((output_dir / "input_transcript.txt").read_text(encoding="utf-8"))
            if (output_dir / "input_transcript.txt").exists()
            else 0,
            "rag_chunk_count": 0,
            "prompt_chars": len((output_dir / "prompt.txt").read_text(encoding="utf-8"))
            if (output_dir / "prompt.txt").exists()
            else 0,
            "ollama_model": settings.ollama_model,
            "ollama_timeout": timeout,
            "ollama_options": build_ollama_options(),
            "ollama_format": build_ollama_format(),
            "ollama_duration_ms": None,
            "total_duration_ms": total_duration_ms,
            "failure_reason": f"{exc.__class__.__name__}: {exc}",
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "model_raw_output.json", {"error": failure})
        write_json(output_dir / "normalized_result.json", {"error": failure})
        log_line(pipeline_log, "real_production_analysis.failed", **failure)
        return failure
    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run one real legacy Qwen3 + RAG production analysis and save debug artifacts.")
    parser.add_argument("--meeting-id", default="meeting_001", help="Meeting id from parsed_meetings.json. Defaults to current V3.2 meeting_001.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Parsed meeting input JSON.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root for debug artifacts.")
    parser.add_argument("--ollama-timeout", type=float, default=settings.ollama_timeout_seconds, help="Per Ollama request timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run(
        meeting_id=args.meeting_id,
        input_path=Path(args.input),
        output_root=Path(args.output_root),
        timeout=args.ollama_timeout,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
