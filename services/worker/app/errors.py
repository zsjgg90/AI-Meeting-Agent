from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.observability import safe_error


PipelineStage = Literal[
    "api_request",
    "task_submission",
    "transcription",
    "diarization",
    "rag_retrieval",
    "prompt_build",
    "model_inference",
    "json_parse",
    "validation",
    "persistence",
    "summary",
    "unknown",
]


@dataclass(frozen=True)
class ErrorInfo:
    pipeline_stage: str
    error_type: str
    error_code: str
    retryable: bool
    safe_message: str


def classify_exception(exc: BaseException, stage: PipelineStage | str = "unknown") -> ErrorInfo:
    error_name = exc.__class__.__name__
    message = safe_error(exc)
    lowered = message.lower()

    if "timeout" in lowered:
        return ErrorInfo(str(stage), error_name, "external_timeout", True, message)
    if "connection" in lowered or "connect" in lowered or "getaddrinfo" in lowered:
        return ErrorInfo(str(stage), error_name, "external_connection_failed", True, message)
    if "json" in lowered or "validation" in lowered or "schema" in lowered:
        return ErrorInfo(str(stage), error_name, "contract_validation_failed", False, message)
    if "not found" in lowered:
        return ErrorInfo(str(stage), error_name, "resource_not_found", False, message)
    if "transcript" in lowered and "required" in lowered:
        return ErrorInfo(str(stage), error_name, "missing_transcript_segments", False, message)

    return ErrorInfo(str(stage), error_name, "pipeline_failed", False, message)
