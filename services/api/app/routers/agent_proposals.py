from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_confirmation_service import (
    approve_proposal,
    create_proposal,
    get_proposal_or_404,
    reject_proposal,
)
from app.agent_security import (
    AgentPrincipal,
    get_agent_principal,
    proposal_project_id,
    proposal_tenant_id,
    require_agent_permission,
    write_control_permissions_for,
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


@router.post("", response_model=AgentActionProposalRead, status_code=201)
def save_action_proposal(
    payload: AgentActionProposalCreate,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentActionProposalRecord:
    require_agent_permission(
        principal,
        "proposal_review",
        tenant_id=proposal_tenant_id(payload.metadata),
        project_id=proposal_project_id(payload.metadata),
        object_type=payload.target_object_type,
        object_id=payload.target_object_id or payload.proposal_id,
        risk_level=payload.risk_level,
        operation=payload.action_type,
    )
    return create_proposal(db, payload.model_dump(mode="json"), principal=principal)


@router.get("", response_model=list[AgentActionProposalRead])
def list_action_proposals(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=100),
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> list[AgentActionProposalRecord]:
    rows = list(
        db.scalars(
            select(AgentActionProposalRecord)
            .where(AgentActionProposalRecord.status == status)
            .order_by(AgentActionProposalRecord.created_at.desc())
            .limit(limit)
        ).all()
    )
    visible: list[AgentActionProposalRecord] = []
    for row in rows:
        if has_agent_access(
            principal,
            "proposal_view",
            tenant_id=proposal_tenant_id(row.metadata_),
            project_id=proposal_project_id(row.metadata_),
            object_type=row.target_object_type,
            object_id=row.target_object_id or row.id,
            risk_level=row.risk_level,
            operation=row.action_type,
            raise_on_denied=False,
        ):
            visible.append(row)
    return visible


@router.get("/{proposal_id}", response_model=AgentActionProposalRead)
def get_action_proposal(
    proposal_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentActionProposalRecord:
    row = get_proposal_or_404(db, proposal_id)
    require_proposal_access(principal, row, "proposal_view")
    return row


@router.post("/{proposal_id}/approve", response_model=AgentProposalDecisionRead)
def approve_action_proposal(
    proposal_id: str,
    payload: AgentProposalConfirmationRequest,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentProposalDecisionRead:
    proposal = get_proposal_or_404(db, proposal_id)
    require_proposal_access(principal, proposal, "proposal_review")
    row, confirmation, result = approve_proposal(
        db,
        proposal_id=proposal_id,
        reviewer=principal.reviewer_identity,
        permissions=write_control_permissions_for(principal, proposal.target_object_type),
        comment=payload.comment,
        principal=principal,
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
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentProposalDecisionRead:
    proposal = get_proposal_or_404(db, proposal_id)
    require_proposal_access(principal, proposal, "proposal_review")
    row, confirmation, audit = reject_proposal(
        db,
        proposal_id=proposal_id,
        reviewer=principal.reviewer_identity,
        permissions=write_control_permissions_for(principal, proposal.target_object_type),
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


def require_proposal_access(principal: AgentPrincipal, row: AgentActionProposalRecord, permission: str) -> None:
    require_agent_permission(
        principal,
        permission,  # type: ignore[arg-type]
        tenant_id=proposal_tenant_id(row.metadata_),
        project_id=proposal_project_id(row.metadata_),
        object_type=row.target_object_type,
        object_id=row.target_object_id or row.id,
        risk_level=row.risk_level,
        operation=row.action_type,
    )


def has_agent_access(
    principal: AgentPrincipal,
    permission: str,
    *,
    tenant_id: str | None,
    project_id: str | None,
    object_type: str,
    object_id: str | None,
    risk_level: str | None,
    operation: str | None,
    raise_on_denied: bool,
) -> bool:
    try:
        require_agent_permission(
            principal,
            permission,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            project_id=project_id,
            object_type=object_type,
            object_id=object_id,
            risk_level=risk_level,
            operation=operation,
        )
        return True
    except HTTPException:
        if raise_on_denied:
            raise
        return False
