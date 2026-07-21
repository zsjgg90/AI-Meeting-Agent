from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fastapi import HTTPException, Request


AgentPermission = Literal[
    "proposal_view",
    "proposal_review",
    "command_dry_run",
    "command_execute",
    "audit_view",
    "rollback_execute",
]

HIGH_RISK_ROLES = {"agent_admin", "agent_high_risk_approver"}
HIGH_RISK_PERMISSION = "high_risk_approve"


@dataclass(frozen=True)
class AgentPrincipal:
    user_id: str
    reviewer_identity: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)
    tenant_id: str | None = None
    project_ids: tuple[str, ...] = field(default_factory=tuple)
    object_scopes: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions

    def can_access_project(self, project_id: str | None) -> bool:
        if "*" in self.project_ids:
            return True
        if not project_id:
            return False
        return project_id in self.project_ids

    def can_access_tenant(self, tenant_id: str | None) -> bool:
        if self.tenant_id == "*":
            return True
        if not tenant_id:
            return False
        return self.tenant_id == tenant_id

    def can_access_object(self, object_type: str, object_id: str | None) -> bool:
        if not object_id:
            return False
        allowed = self.object_scopes.get(object_type) or self.object_scopes.get("*")
        if not allowed:
            return True
        return "*" in allowed or object_id in allowed

    def can_approve_high_risk(self) -> bool:
        return bool(set(self.roles) & HIGH_RISK_ROLES) or self.has_permission(HIGH_RISK_PERMISSION)


async def get_agent_principal(_: Request) -> AgentPrincipal:
    """Production auth adapter placeholder.

    The project currently has no real auth/session/JWT module. Agent APIs must
    therefore fail closed until a production provider replaces this dependency.
    Tests inject a server-side principal through FastAPI dependency overrides.
    """

    raise HTTPException(status_code=401, detail="Agent authentication provider is not configured.")


def require_agent_permission(
    principal: AgentPrincipal,
    permission: AgentPermission,
    *,
    tenant_id: str | None,
    project_id: str | None,
    object_type: str,
    object_id: str | None,
    risk_level: str | None = None,
    operation: str | None = None,
) -> None:
    if not principal.user_id or not principal.reviewer_identity:
        raise HTTPException(status_code=401, detail="Authenticated Agent principal is required.")
    if not principal.has_permission(permission):
        raise HTTPException(status_code=403, detail=f"Agent permission required: {permission}.")
    if not principal.can_access_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="Agent tenant scope denied.")
    if not principal.can_access_project(project_id):
        raise HTTPException(status_code=403, detail="Agent project scope denied.")
    if not principal.can_access_object(object_type, object_id):
        raise HTTPException(status_code=403, detail="Agent object scope denied.")
    if (
        permission in {"proposal_review", "command_execute", "rollback_execute"}
        and is_high_risk(risk_level=risk_level, operation=operation)
        and not principal.can_approve_high_risk()
    ):
        raise HTTPException(status_code=403, detail="High-risk Agent action requires elevated approval.")


def write_control_permissions_for(principal: AgentPrincipal, object_type: str) -> list[str]:
    permissions = ["agent_review", f"agent_write:{object_type}"]
    if principal.has_permission("*") or principal.has_permission("command_execute"):
        permissions.append("agent_write")
    return permissions


def is_high_risk(*, risk_level: str | None, operation: str | None = None) -> bool:
    return str(risk_level or "").lower() in {"high", "critical"} or str(operation or "").lower() in {"complete", "cancel"}


def proposal_project_id(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("project_id") or metadata.get("project") or metadata.get("scope_project_id")
    return str(value) if value else None


def proposal_tenant_id(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("tenant_id") or metadata.get("tenant")
    return str(value) if value else None
