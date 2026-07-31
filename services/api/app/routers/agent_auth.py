from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.agent_auth_service import create_local_agent_session, revoke_agent_session
from app.agent_security import AgentPrincipal, bearer_token_from_request, get_agent_principal
from app.database import get_db
from app.schemas import AgentLoginRead, AgentLoginRequest, AgentLogoutRead, AgentSessionRead

router = APIRouter(prefix="/agent/auth", tags=["agent"])


@router.post("/login", response_model=AgentLoginRead)
def login_agent_session(payload: AgentLoginRequest, db: Session = Depends(get_db)) -> AgentLoginRead:
    created = create_local_agent_session(db, display_name=payload.display_name)
    return AgentLoginRead(
        token=created.token,
        token_type="bearer",
        expires_at=created.expires_at,
        user_id=created.user.id,
        display_name=created.user.display_name,
        tenant_id=created.user.tenant_id,
        project_scope=list(created.user.project_scope or []),
        permissions=list(created.user.permissions or []),
    )


@router.get("/session", response_model=AgentSessionRead)
def read_agent_session(principal: AgentPrincipal = Depends(get_agent_principal)) -> AgentSessionRead:
    return AgentSessionRead(
        user_id=principal.user_id,
        display_name=principal.reviewer_identity,
        tenant_id=principal.tenant_id or "",
        project_scope=list(principal.project_scope),
        permissions=list(principal.permissions),
        authentication_source=principal.authentication_source,
    )


@router.post("/logout", response_model=AgentLogoutRead)
def logout_agent_session(request: Request, db: Session = Depends(get_db)) -> AgentLogoutRead:
    token = bearer_token_from_request(request)
    revoked = revoke_agent_session(db, token=token) if token else False
    return AgentLogoutRead(status="ok", revoked=revoked)
