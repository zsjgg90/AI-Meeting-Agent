from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import time
from typing import Any


LOGGER_NAME = "meeting_worker"
MAX_FIELD_LENGTH = 800


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(LOGGER_NAME)


SECRET_KEYWORDS = (
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "token",
    "password",
    "credential",
)

CONTENT_KEYS = {
    "prompt",
    "transcript",
    "rag_context",
    "raw_output",
    "source_text",
    "audio_bytes",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redact_sensitive_text(value: str) -> str:
    text = value
    text = re.sub(r"(postgresql(?:\+\w+)?://[^:\s]+):([^@\s]+)@", r"\1:***@", text)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(api[_-]?key|access[_-]?key|secret|token|password)=([^&\s]+)", r"\1=***", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "***@***", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "1**********", text)
    text = re.sub(r"C:\\Users\\[^\\\s]+", r"C:\\Users\\***", text, flags=re.IGNORECASE)
    if len(text) > MAX_FIELD_LENGTH:
        text = f"{text[:MAX_FIELD_LENGTH]}...[truncated]"
    return text


def safe_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(keyword in key_lower for keyword in SECRET_KEYWORDS):
        return "***"
    if key_lower in CONTENT_KEYS:
        text = str(value or "")
        return {
            "sha256": text_digest(text),
            "length": len(text),
        }
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {str(child_key): safe_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [safe_value(key, item) for item in value]
    return value


def safe_error(exc: BaseException) -> str:
    return redact_sensitive_text(str(exc))


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    payload = {
        "timestamp": utc_now(),
        "service": "worker",
        "event": event,
        **{key: safe_value(key, value) for key, value in fields.items()},
    }
    level_no = getattr(logging, level.upper(), logging.INFO)
    logger.log(level_no, json.dumps(payload, ensure_ascii=False, default=str))


@contextmanager
def log_stage(stage: str, **fields: Any) -> Iterator[None]:
    started_at = time.perf_counter()
    log_event("pipeline.stage.started", pipeline_stage=stage, **fields)
    try:
        yield
    except Exception as exc:
        log_event(
            "pipeline.stage.failed",
            level="error",
            pipeline_stage=stage,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error_type=exc.__class__.__name__,
            error_message=safe_error(exc),
            **fields,
        )
        raise
    else:
        log_event(
            "pipeline.stage.completed",
            pipeline_stage=stage,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            **fields,
        )
