from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_confirmation_service import (
    approve_proposal,
    create_proposal,
    get_proposal_or_404,
    reject_proposal,
)
from app.database import get_db
from app.models import AgentAuditRecord, ControlledWriteCommandRecord, AgentActionProposalRecord
from app.schemas import (
    AgentActionProposalCreate,
    AgentActionProposalRead,
    AgentProposalConfirmationRequest,
    AgentProposalDecisionRead,
)

router = APIRouter(prefix="/agent/action-proposals", tags=["agent"])


@dataclass(frozen=True)
class AgentReviewer:
    reviewer: str
    permissions: list[str]


def get_agent_reviewer(
    x_agent_reviewer: str | None = Header(default=None),
    x_agent_permissions: str | None = Header(default=None),
) -> AgentReviewer:
    reviewer = (x_agent_reviewer or "").strip()
    permissions = [item.strip() for item in (x_agent_permissions or "").split(",") if item.strip()]
    if not reviewer:
        raise HTTPException(status_code=401, detail="X-Agent-Reviewer is required.")
    if not permissions:
        raise HTTPException(status_code=403, detail="Agent permissions are required.")
    return AgentReviewer(reviewer=reviewer, permissions=permissions)


@router.post("", response_model=AgentActionProposalRead, status_code=201)
def save_action_proposal(
    payload: AgentActionProposalCreate,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> AgentActionProposalRecord:
    if "agent_proposal:create" not in reviewer.permissions and "*" not in reviewer.permissions:
        raise HTTPException(status_code=403, detail="Agent proposal create permission is required.")
    return create_proposal(db, payload.model_dump(mode="json"))


@router.get("", response_model=list[AgentActionProposalRead])
def list_action_proposals(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=100),
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> list[AgentActionProposalRecord]:
    require_review_access(reviewer.permissions)
    return list(
        db.scalars(
            select(AgentActionProposalRecord)
            .where(AgentActionProposalRecord.status == status)
            .order_by(AgentActionProposalRecord.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/{proposal_id}", response_model=AgentActionProposalRead)
def get_action_proposal(
    proposal_id: str,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> AgentActionProposalRecord:
    require_review_access(reviewer.permissions)
    return get_proposal_or_404(db, proposal_id)


@router.post("/{proposal_id}/approve", response_model=AgentProposalDecisionRead)
def approve_action_proposal(
    proposal_id: str,
    payload: AgentProposalConfirmationRequest,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> AgentProposalDecisionRead:
    row, confirmation, result = approve_proposal(
        db,
        proposal_id=proposal_id,
        reviewer=reviewer.reviewer,
        permissions=reviewer.permissions,
        comment=payload.comment,
    )
    command = db.scalars(
        select(ControlledWriteCommandRecord)
        .where(ControlledWriteCommandRecord.proposal_id == proposal_id)
        .order_by(ControlledWriteCommandRecord.created_at.desc())
    ).first()
    audit = db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.proposal_id == proposal_id)
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()
    if result.status != "ready" and "version_conflict" in result.rejection_reasons:
        raise HTTPException(status_code=409, detail={"status": row.status, "reasons": result.rejection_reasons})
    if result.status != "ready" and "target_not_found" in result.rejection_reasons:
        raise HTTPException(status_code=404, detail={"status": row.status, "reasons": result.rejection_reasons})
    if result.status != "ready" and "permission_denied" in result.rejection_reasons:
        raise HTTPException(status_code=403, detail={"status": row.status, "reasons": result.rejection_reasons})
    if result.status != "ready" and "confirmation_expired" in result.rejection_reasons:
        raise HTTPException(status_code=409, detail={"status": row.status, "reasons": result.rejection_reasons})
    if result.status != "ready" and result.status != "duplicate":
        raise HTTPException(status_code=400, detail={"status": row.status, "reasons": result.rejection_reasons})
    return AgentProposalDecisionRead(
        proposal=row,
        confirmation=confirmation,
        command=command,
        audit=audit,
        status=result.status,
        rejection_reasons=result.rejection_reasons,
    )


@router.post("/{proposal_id}/reject", response_model=AgentProposalDecisionRead)
def reject_action_proposal(
    proposal_id: str,
    payload: AgentProposalConfirmationRequest,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> AgentProposalDecisionRead:
    row, confirmation, audit = reject_proposal(
        db,
        proposal_id=proposal_id,
        reviewer=reviewer.reviewer,
        permissions=reviewer.permissions,
        comment=payload.comment,
    )
    return AgentProposalDecisionRead(
        proposal=row,
        confirmation=confirmation,
        command=None,
        audit=audit,
        status="rejected",
        rejection_reasons=["human_rejected"],
    )


def require_review_access(permissions: list[str]) -> None:
    if not set(permissions) & {"*", "agent_review", "agent_write"}:
        raise HTTPException(status_code=403, detail="Agent proposal review permission is required.")
