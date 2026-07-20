from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_write_control import AuthoritativeStateSnapshot, TrackedObjectType
from app.models import ActionItem, MeetingSummary


class DatabaseAuthoritativeStateProvider:
    """Read only the requested object from existing production state."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_state(self, *, object_type: TrackedObjectType, object_id: str) -> AuthoritativeStateSnapshot | None:
        if object_type == "AgentActionItem":
            return self._get_action_item(object_id)
        if object_type == "Requirement":
            return self._get_summary_json_object(
                object_type=object_type,
                object_id=object_id,
                fields=("requirements", "meeting_agenda", "key_conclusions", "topics"),
                source_prefix="postgresql.meeting_summaries",
            )
        if object_type == "Risk":
            return self._get_summary_json_object(
                object_type=object_type,
                object_id=object_id,
                fields=("risks_and_focus", "risks"),
                source_prefix="postgresql.meeting_summaries",
            )
        return None

    def _get_action_item(self, object_id: str) -> AuthoritativeStateSnapshot | None:
        item = self.db.get(ActionItem, object_id)
        if item is None:
            return None
        updated_at = item.updated_at.isoformat() if item.updated_at else ""
        return AuthoritativeStateSnapshot(
            object_type="AgentActionItem",
            object_id=item.id,
            object_version=updated_at,
            status=item.status or "unknown",
            updated_at=updated_at,
            source="postgresql.action_items",
            data={
                "title": item.task,
                "description": item.source_text or item.source or "",
                "owner": item.owner or item.owner_name,
                "due_date": item.due_date or item.deadline,
                "status": item.status,
                "priority": item.priority,
                "meeting_id": item.meeting_id,
                "summary_id": item.summary_id,
            },
            metadata={"table": "action_items", "writes_performed": False},
        )

    def _get_summary_json_object(
        self,
        *,
        object_type: TrackedObjectType,
        object_id: str,
        fields: tuple[str, ...],
        source_prefix: str,
    ) -> AuthoritativeStateSnapshot | None:
        summaries = self.db.scalars(select(MeetingSummary).order_by(MeetingSummary.updated_at.desc())).all()
        for summary in summaries:
            for field in fields:
                values = getattr(summary, field, None)
                if not isinstance(values, list):
                    continue
                for index, value in enumerate(values):
                    if not isinstance(value, dict):
                        continue
                    found_id = _json_object_id(value, object_type=object_type, fallback=f"{summary.id}:{field}:{index}")
                    if found_id != object_id:
                        continue
                    updated_at = summary.updated_at.isoformat() if summary.updated_at else ""
                    snapshot = dict(value)
                    snapshot.setdefault("id", found_id)
                    return AuthoritativeStateSnapshot(
                        object_type=object_type,
                        object_id=found_id,
                        object_version=updated_at,
                        status=str(snapshot.get("status") or "unknown"),
                        updated_at=updated_at,
                        source=f"{source_prefix}.{field}",
                        data=snapshot,
                        metadata={
                            "table": "meeting_summaries",
                            "summary_id": summary.id,
                            "json_field": field,
                            "json_index": index,
                            "writes_performed": False,
                        },
                    )
        return None


def _json_object_id(value: dict[str, Any], *, object_type: TrackedObjectType, fallback: str) -> str:
    keys = {
        "Requirement": ("requirement_id", "id", "target_object_id"),
        "Risk": ("risk_id", "id", "target_object_id"),
        "AgentActionItem": ("action_item_id", "id", "target_object_id"),
    }[object_type]
    for key in keys:
        if value.get(key):
            return str(value[key])
    return fallback

