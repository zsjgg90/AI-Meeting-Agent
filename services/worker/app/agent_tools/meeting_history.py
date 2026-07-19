from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class SearchMeetingHistoryTool(AgentTool):
    def __init__(self, *, db_provider: Callable[[], Any], policy: ToolPolicy | None = None) -> None:
        super().__init__(
            name="search_meeting_history",
            policy=policy
            or ToolPolicy(
                timeout_seconds=8,
                max_calls_per_run=3,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.db_provider = db_provider

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip().lower()
        meeting_type = payload.get("meeting_type")
        project_id = payload.get("project_id") or context.project_id or None
        exclude_meeting_id = payload.get("exclude_meeting_id") or context.meeting_id or None
        limit = max(1, min(int(payload.get("limit") or 5), 20))

        db = self.db_provider()
        try:
            if hasattr(db, "search_meeting_history"):
                items = db.search_meeting_history(
                    query=query,
                    meeting_type=meeting_type,
                    project_id=project_id,
                    exclude_meeting_id=exclude_meeting_id,
                    limit=limit,
                )
                return {
                    "items": list(items),
                    "project_id_filter_applied": False,
                    "meeting_type_filter_applied": False,
                    "_result_source": "postgresql",
                }

            from app.models import Meeting, MeetingSummary

            rows = db.execute(
                select(Meeting, MeetingSummary)
                .join(MeetingSummary, MeetingSummary.meeting_id == Meeting.id)
                .order_by(Meeting.created_at.desc())
            ).all()
            items: list[dict[str, Any]] = []
            for meeting, summary in rows:
                if exclude_meeting_id and meeting.id == exclude_meeting_id:
                    continue
                searchable = " ".join(
                    [
                        str(meeting.id),
                        str(meeting.title or ""),
                        str(summary.meeting_summary or summary.overview or ""),
                    ]
                ).lower()
                if query and query not in searchable:
                    continue
                items.append(
                    {
                        "meeting_id": meeting.id,
                        "title": meeting.title,
                        "status": meeting.status,
                        "created_at": meeting.created_at.isoformat() if getattr(meeting, "created_at", None) else None,
                        "meeting_summary": summary.meeting_summary or summary.overview,
                        "model_name": summary.model_name,
                        "prompt_version": summary.prompt_version,
                        "result_source": "legacy_qwen_rag" if summary.model_name and "+rag" in summary.model_name else "unknown",
                        "meeting_type": None,
                    }
                )
                if len(items) >= limit:
                    break

            return {
                "items": items,
                "project_id_filter_applied": False,
                "meeting_type_filter_applied": False,
                "metadata": {
                    "project_id_ignored": bool(project_id),
                    "meeting_type_ignored": bool(meeting_type),
                },
                "_result_source": "postgresql",
            }
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()


__all__ = ["SearchMeetingHistoryTool"]
