from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class GetOpenActionItemsTool(AgentTool):
    def __init__(self, *, db_provider: Callable[[], Any], policy: ToolPolicy | None = None) -> None:
        super().__init__(
            name="get_open_action_items",
            policy=policy
            or ToolPolicy(
                timeout_seconds=5,
                max_calls_per_run=3,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.db_provider = db_provider

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_id = payload.get("meeting_id") or None
        owner = str(payload.get("owner") or "").strip()
        limit = max(1, min(int(payload.get("limit") or 20), 50))

        db = self.db_provider()
        try:
            if hasattr(db, "get_open_action_items"):
                return {
                    "items": list(db.get_open_action_items(meeting_id=meeting_id, owner=owner or None, limit=limit)),
                    "status_filter": "open",
                    "_result_source": "postgresql",
                }

            from app.models import ActionItem

            statement = select(ActionItem).where(ActionItem.status == "open")
            if meeting_id:
                statement = statement.where(ActionItem.meeting_id == meeting_id)
            statement = statement.order_by(ActionItem.created_at.desc()).limit(limit)
            rows = list(db.scalars(statement).all())
            items = []
            for item in rows:
                item_owner = item.owner or item.owner_name or ""
                if owner and owner != item_owner:
                    continue
                items.append(
                    {
                        "id": item.id,
                        "meeting_id": item.meeting_id,
                        "summary_id": item.summary_id,
                        "task": item.task,
                        "owner": item.owner,
                        "owner_name": item.owner_name,
                        "due_date": item.due_date,
                        "deadline": item.deadline,
                        "priority": item.priority,
                        "status": item.status,
                        "source": item.source,
                        "source_text": item.source_text,
                        "source_segment_id": item.source_segment_id,
                        "confidence": item.confidence,
                    }
                )

            return {
                "items": items,
                "status_filter": "open",
                "_result_source": "postgresql",
            }
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()


__all__ = ["GetOpenActionItemsTool"]
