from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_command_executor import dry_run_command, rollback_dry_run_command
from app.agent_security import (
    AgentPrincipal,
    get_agent_principal,
    proposal_project_id,
    proposal_tenant_id,
    require_agent_permission,
)
from app.database import get_db
from app.models import AgentActionProposalRecord, AgentAuditRecord, ControlledWriteCommandRecord
from app.schemas import AgentAuditRecordRead, AgentCommandDryRunRead, AgentRollbackDryRunRead, ControlledWriteCommandRead

router = APIRouter(prefix="/agent/commands", tags=["agent"])


@router.get("", response_model=list[ControlledWriteCommandRead])
def list_agent_commands(
    status: str = Query(default="ready"),
    limit: int = Query(default=50, ge=1, le=100),
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> list[ControlledWriteCommandRecord]:
    rows = list(
        db.scalars(
            select(ControlledWriteCommandRecord)
            .where(ControlledWriteCommandRecord.status == status)
            .order_by(ControlledWriteCommandRecord.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [command for command in rows if command_access_allowed(db, principal, command, "command_dry_run")]


@router.get("/{command_id}", response_model=ControlledWriteCommandRead)
def get_agent_command(
    command_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> ControlledWriteCommandRecord:
    command = db.get(ControlledWriteCommandRecord, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    require_command_access(db, principal, command, "command_dry_run")
    return command


@router.post("/{command_id}/dry-run", response_model=AgentCommandDryRunRead)
def dry_run_agent_command(
    command_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentCommandDryRunRead:
    command = get_command_or_404(db, command_id)
    require_command_access(db, principal, command, "command_dry_run")
    result = dry_run_command(
        db,
        command_id=command_id,
        principal=principal,
    )
    return AgentCommandDryRunRead(
        command=ControlledWriteCommandRead.model_validate(result.command),
        audit=AgentAuditRecordRead.model_validate(result.audit),
        status=result.status,
        rejection_reasons=result.rejection_reasons,
        authoritative_state=result.authoritative_state,
        expected_changes=result.expected_changes,
        rollback_preview=result.rollback_preview,
        writes_performed=result.writes_performed,
    )


@router.post("/{command_id}/rollback/dry-run", response_model=AgentRollbackDryRunRead)
def rollback_dry_run_agent_command(
    command_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentRollbackDryRunRead:
    command = get_command_or_404(db, command_id)
    require_command_access(db, principal, command, "rollback_execute")
    result = rollback_dry_run_command(db, command_id=command_id, principal=principal)
    return AgentRollbackDryRunRead(
        command=ControlledWriteCommandRead.model_validate(result.command),
        audit=AgentAuditRecordRead.model_validate(result.audit),
        status=result.status,
        rejection_reasons=result.rejection_reasons,
        rollback_command=result.rollback_command,
        rollback_preview=result.rollback_preview,
        authoritative_state=result.authoritative_state,
        writes_performed=result.writes_performed,
    )


@router.get("/{command_id}/audits", response_model=list[AgentAuditRecordRead])
def list_agent_command_audits(
    command_id: str,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> list[AgentAuditRecord]:
    command = get_command_or_404(db, command_id)
    require_command_access(db, principal, command, "audit_view")
    return list(
        db.scalars(
            select(AgentAuditRecord)
            .where(AgentAuditRecord.command_id == command_id)
            .order_by(AgentAuditRecord.created_at.desc())
        ).all()
    )


def get_command_or_404(db: Session, command_id: str) -> ControlledWriteCommandRecord:
    command = db.get(ControlledWriteCommandRecord, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    return command


def command_proposal(db: Session, command: ControlledWriteCommandRecord) -> AgentActionProposalRecord | None:
    return db.get(AgentActionProposalRecord, command.proposal_id)


def require_command_access(
    db: Session,
    principal: AgentPrincipal,
    command: ControlledWriteCommandRecord,
    permission: str,
) -> None:
    proposal = command_proposal(db, command)
    metadata = proposal.metadata_ if proposal else {}
    risk_level = proposal.risk_level if proposal else None
    require_agent_permission(
        principal,
        permission,  # type: ignore[arg-type]
        tenant_id=proposal_tenant_id(metadata),
        project_id=proposal_project_id(metadata),
        object_type=command.target_object_type,
        object_id=command.target_object_id,
        risk_level=risk_level,
        operation=command.operation,
    )


def command_access_allowed(
    db: Session,
    principal: AgentPrincipal,
    command: ControlledWriteCommandRecord,
    permission: str,
) -> bool:
    try:
        require_command_access(db, principal, command, permission)
        return True
    except HTTPException:
        return False
