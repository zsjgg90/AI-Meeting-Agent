from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent_security import AgentPrincipal, require_agent_permission
from app.agent_write_control import AuthoritativeStateSnapshot, TrackedObjectType
from app.models import ActionItem, Requirement, Risk


class DatabaseAuthoritativeStateProvider:
    """Read only the requested object from existing production state."""

    def __init__(
        self,
        db: Session,
        principal: AgentPrincipal | None = None,
        view_permission: str = "proposal_view",
    ) -> None:
        self.db = db
        self.principal = principal
        self.view_permission = view_permission

    def get_state(self, *, object_type: TrackedObjectType, object_id: str) -> AuthoritativeStateSnapshot | None:
        if object_type == "AgentActionItem":
            return self._get_action_item(object_id)
        if object_type == "Requirement":
            return self._get_requirement(object_id)
        if object_type == "Risk":
            return self._get_risk(object_id)
        return None

    def _get_action_item(self, object_id: str) -> AuthoritativeStateSnapshot | None:
        item = self.db.get(ActionItem, object_id)
        if item is None:
            return None
        self._require_view(
            tenant_id=item.tenant_id,
            project_id=item.project_id,
            object_type="AgentActionItem",
            object_id=item.id,
            status=item.status,
        )
        updated_at = item.updated_at.isoformat() if item.updated_at else ""
        return AuthoritativeStateSnapshot(
            object_type="AgentActionItem",
            object_id=item.id,
            object_version=str(item.version),
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
                "version": item.version,
                "tenant_id": item.tenant_id,
                "project_id": item.project_id,
                "meeting_id": item.meeting_id,
                "summary_id": item.summary_id,
            },
            metadata={"table": "action_items", "writes_performed": False},
        )

    def _get_requirement(self, object_id: str) -> AuthoritativeStateSnapshot | None:
        item = self.db.get(Requirement, object_id)
        if item is None:
            return None
        self._require_view(
            tenant_id=item.tenant_id,
            project_id=item.project_id,
            object_type="Requirement",
            object_id=item.id,
            status=item.status,
        )
        updated_at = item.updated_at.isoformat() if item.updated_at else ""
        return AuthoritativeStateSnapshot(
            object_type="Requirement",
            object_id=item.id,
            object_version=str(item.version),
            status=item.status,
            updated_at=updated_at,
            source="postgresql.requirements",
            data={
                "id": item.id,
                "tenant_id": item.tenant_id,
                "project_id": item.project_id,
                "title": item.title,
                "description": item.description,
                "status": item.status,
                "owner": item.owner,
                "due_date": item.due_date,
                "priority": item.priority,
                "version": item.version,
                "source_meeting_id": item.source_meeting_id,
                "source_ref": item.source_ref,
            },
            metadata={"table": "requirements", "writes_performed": False},
        )

    def _get_risk(self, object_id: str) -> AuthoritativeStateSnapshot | None:
        item = self.db.get(Risk, object_id)
        if item is None:
            return None
        self._require_view(
            tenant_id=item.tenant_id,
            project_id=item.project_id,
            object_type="Risk",
            object_id=item.id,
            status=item.status,
        )
        updated_at = item.updated_at.isoformat() if item.updated_at else ""
        return AuthoritativeStateSnapshot(
            object_type="Risk",
            object_id=item.id,
            object_version=str(item.version),
            status=item.status,
            updated_at=updated_at,
            source="postgresql.risks",
            data={
                "id": item.id,
                "tenant_id": item.tenant_id,
                "project_id": item.project_id,
                "title": item.title,
                "description": item.description,
                "status": item.status,
                "owner": item.owner,
                "due_date": item.due_date,
                "priority": item.priority,
                "version": item.version,
                "source_meeting_id": item.source_meeting_id,
                "level": item.level,
                "category": item.category,
                "impact": item.impact,
                "probability": item.probability,
                "mitigation": item.mitigation,
                "source_ref": item.source_ref,
            },
            metadata={"table": "risks", "writes_performed": False},
        )

    def _require_view(
        self,
        *,
        tenant_id: str,
        project_id: str,
        object_type: TrackedObjectType,
        object_id: str,
        status: str | None,
    ) -> None:
        if self.principal is None:
            return
        require_agent_permission(
            self.principal,
            self.view_permission,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            project_id=project_id,
            object_type=object_type,
            object_id=object_id,
            risk_level=status,
            operation="view",
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
