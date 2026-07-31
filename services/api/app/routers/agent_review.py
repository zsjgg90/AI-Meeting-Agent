from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agent_review_service import get_review_overview, get_review_record_detail, list_review_records
from app.agent_security import AgentPrincipal, get_agent_principal, require_agent_permission
from app.database import get_db
from app.schemas import AgentReviewOverviewRead, AgentReviewRecordDetailRead, AgentReviewRecordsRead

router = APIRouter(prefix="/agent/review", tags=["agent"])


@router.get("/overview", response_model=AgentReviewOverviewRead)
def review_overview(
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentReviewOverviewRead:
    _require_review_access(principal)
    return get_review_overview(db, principal)


@router.get("/records", response_model=AgentReviewRecordsRead)
def review_records(
    status: str = Query(default="all"),
    sort: str = Query(default="latest", pattern="^(latest|oldest)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentReviewRecordsRead:
    _require_review_access(principal)
    return list_review_records(db, principal, status=status, sort=sort, page=page, page_size=page_size)


@router.get("/records/{record_id}", response_model=AgentReviewRecordDetailRead)
def review_record_detail(
    record_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentReviewRecordDetailRead:
    _require_review_access(principal)
    return get_review_record_detail(db, principal, record_id)


def _require_review_access(principal: AgentPrincipal) -> None:
    require_agent_permission(
        principal,
        "proposal_view",
        tenant_id=principal.tenant_id,
        project_id=principal.project_scope[0] if principal.project_scope else None,
        object_type="AgentActionItem",
        object_id=principal.user_id,
    )
