from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from app.anti_hallucination_validator import normalize_text


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TRACE_ROOT = PROJECT_ROOT / "data" / "debug" / "action_validator_trace"


ACTION_TRACE_FIELDS = (
    "task",
    "source_text",
    "source_segment_id",
    "confidence",
)


def action_trace_item(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in ACTION_TRACE_FIELDS}


def action_match_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_text(item.get("task")),
        normalize_text(item.get("source_text")),
        normalize_text(item.get("source_segment_id")),
    )


def _audit_item(event: dict[str, Any]) -> dict[str, Any] | None:
    before = event.get("before")
    if isinstance(before, dict):
        return before
    after = event.get("after")
    if isinstance(after, dict):
        return after
    return None


def _remove_audit_by_key(audit: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    events: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in audit:
        if event.get("field") != "action_items" or event.get("action") != "remove":
            continue
        item = _audit_item(event)
        if not item:
            continue
        events.setdefault(action_match_key(item), event)
    return events


def build_action_validator_trace(
    validator_input: dict[str, Any],
    validator_output: dict[str, Any],
    validator_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    input_actions = [
        item for item in validator_input.get("action_items", []) if isinstance(item, dict)
    ]
    output_actions = [
        item for item in validator_output.get("action_items", []) if isinstance(item, dict)
    ]
    output_keys = {action_match_key(item) for item in output_actions}
    remove_audit = _remove_audit_by_key(validator_audit)
    final_task_list = [str(item.get("task") or "") for item in output_actions]

    trace_items: list[dict[str, Any]] = []
    removed_items: list[dict[str, Any]] = []

    for index, item in enumerate(input_actions):
        key = action_match_key(item)
        kept = key in output_keys
        event = remove_audit.get(key)
        reason = event.get("reason") if event else None
        if not kept and not reason:
            reason = "unattributed_validator_removal"

        entry = {
            "index": index,
            "before_validator": action_trace_item(item),
            "validator_result": {
                "decision": "keep" if kept else "remove",
                "remove_reason": None if kept else reason,
                "rule_name": None if kept else reason,
            },
            "after_validator": {
                "final_task_list": final_task_list,
            },
        }
        trace_items.append(entry)
        if not kept:
            removed_items.append(
                {
                    "task": item.get("task"),
                    "remove_reason": reason,
                    "rule_name": reason,
                    "before_validator": action_trace_item(item),
                    "audit_event": deepcopy(event) if event else None,
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_action_count": len(input_actions),
        "output_action_count": len(output_actions),
        "removed_action_count": len(removed_items),
        "items": trace_items,
        "removed_items": removed_items,
        "after_validator": {
            "final_task_list": final_task_list,
        },
    }


def write_action_validator_trace(
    validator_input: dict[str, Any],
    validator_output: dict[str, Any],
    validator_audit: list[dict[str, Any]],
    *,
    output_dir: Path | str | None = None,
) -> Path:
    target_root = Path(output_dir) if output_dir is not None else DEFAULT_TRACE_ROOT
    target_dir = target_root / _run_id()
    target_dir.mkdir(parents=True, exist_ok=True)

    trace = build_action_validator_trace(
        validator_input=validator_input,
        validator_output=validator_output,
        validator_audit=validator_audit,
    )

    _write_json(
        target_dir / "validator_input.json",
        {
            "action_item_count": trace["input_action_count"],
            "action_items": [
                item["before_validator"] for item in trace["items"]
            ],
        },
    )
    _write_json(
        target_dir / "validator_output.json",
        {
            "action_item_count": trace["output_action_count"],
            "action_items": validator_output.get("action_items", []),
            "after_validator": trace["after_validator"],
            "trace": trace["items"],
        },
    )
    _write_json(target_dir / "validator_removed_items.json", trace["removed_items"])
    return target_dir


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
