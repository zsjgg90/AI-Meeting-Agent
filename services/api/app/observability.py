from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("meeting_api")


def redact_sensitive_text(value: str) -> str:
    text = re.sub(r"(postgresql(?:\+\w+)?://[^:\s]+):([^@\s]+)@", r"\1:***@", value)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1***", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(api[_-]?key|access[_-]?key|secret|token|password)=([^&\s]+)", r"\1=***", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "***@***", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "1**********", text)
    text = re.sub(r"C:\\Users\\[^\\\s]+", r"C:\\Users\\***", text, flags=re.IGNORECASE)
    return text[:800] + "...[truncated]" if len(text) > 800 else text


def safe_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(keyword in key_lower for keyword in ("secret", "token", "password", "api_key", "access_key")):
        return "***"
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "api",
        "event": event,
        **{key: safe_value(key, value) for key, value in fields.items()},
    }
    logger.log(getattr(logging, level.upper(), logging.INFO), json.dumps(payload, ensure_ascii=False, default=str))
