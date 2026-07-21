from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentAuthSession, AgentUser


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
    authentication_source: str = "unknown"

    @property
    def project_scope(self) -> tuple[str, ...]:
        return self.project_ids

    @property
    def object_scope(self) -> dict[str, tuple[str, ...]]:
        return self.object_scopes

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


async def get_agent_principal(request: Request, db: Session = Depends(get_db)) -> AgentPrincipal:
    token = bearer_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Agent authentication is required.")
    return principal_from_bearer_token(db, token)


def bearer_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("authorization") or ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def principal_from_bearer_token(db: Session, token: str) -> AgentPrincipal:
    token_hash = hash_agent_token(token)
    session = db.scalars(select(AgentAuthSession).where(AgentAuthSession.token_hash == token_hash)).first()
    if session is None:
        raise HTTPException(status_code=401, detail="Agent session is invalid.")
    now = datetime.now(timezone.utc)
    expires_at = ensure_aware(session.expires_at)
    revoked_at = ensure_aware(session.revoked_at) if session.revoked_at else None
    if revoked_at is not None or expires_at <= now:
        raise HTTPException(status_code=401, detail="Agent session has expired.")
    user = db.get(AgentUser, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Agent user is inactive.")
    return AgentPrincipal(
        user_id=user.id,
        reviewer_identity=user.display_name or user.id,
        roles=tuple(str(item) for item in (user.roles or [])),
        permissions=tuple(str(item) for item in (user.permissions or [])),
        tenant_id=user.tenant_id,
        project_ids=tuple(str(item) for item in (user.project_scope or [])),
        object_scopes=normalize_object_scope(user.object_scope or {}),
        authentication_source=session.authentication_source,
    )


def hash_agent_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


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


def normalize_object_scope(value: dict) -> dict[str, tuple[str, ...]]:
    normalized: dict[str, tuple[str, ...]] = {}
    for object_type, ids in value.items():
        if isinstance(ids, str):
            normalized[str(object_type)] = (ids,)
        elif isinstance(ids, list):
            normalized[str(object_type)] = tuple(str(item) for item in ids)
    return normalized


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
