from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_security import hash_agent_token
from app.config import get_settings
from app.models import AgentAuthSession, AgentUser


LOCAL_AGENT_PERMISSIONS = [
    "proposal_view",
    "proposal_review",
    "command_dry_run",
    "command_execute",
    "audit_view",
    "rollback_execute",
]


@dataclass(frozen=True)
class CreatedAgentSession:
    token: str
    expires_at: datetime
    user: AgentUser


def create_local_agent_session(db: Session, *, display_name: str | None = None) -> CreatedAgentSession:
    settings = get_settings()
    if not settings.agent_local_auth_enabled:
        raise HTTPException(status_code=403, detail="Local Agent login is disabled.")

    user_id = "local-agent-user"
    user = db.get(AgentUser, user_id)
    if user is None:
        user = AgentUser(
            id=user_id,
            tenant_id=settings.agent_local_auth_tenant_id,
            display_name=(display_name or "本地验收用户").strip() or "本地验收用户",
            roles=[],
            permissions=LOCAL_AGENT_PERMISSIONS,
            project_scope=[settings.agent_local_auth_project_id],
            object_scope={},
            is_active=True,
        )
        db.add(user)
    else:
        user.tenant_id = settings.agent_local_auth_tenant_id
        user.display_name = (display_name or user.display_name or "本地验收用户").strip() or "本地验收用户"
        user.roles = []
        user.permissions = LOCAL_AGENT_PERMISSIONS
        user.project_scope = [settings.agent_local_auth_project_id]
        user.object_scope = {}
        user.is_active = True

    db.flush()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.agent_local_auth_token_ttl_hours)
    session = AgentAuthSession(
        user_id=user_id,
        token_hash=hash_agent_token(token),
        authentication_source="local_agent_login",
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(user)
    return CreatedAgentSession(token=token, expires_at=expires_at, user=user)


def revoke_agent_session(db: Session, *, token: str) -> bool:
    row = db.scalars(
        select(AgentAuthSession).where(AgentAuthSession.token_hash == hash_agent_token(token))
    ).first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True
