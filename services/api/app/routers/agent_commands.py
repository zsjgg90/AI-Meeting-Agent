from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_command_executor import dry_run_command
from app.database import get_db
from app.models import AgentAuditRecord, ControlledWriteCommandRecord
from app.routers.agent_proposals import AgentReviewer, get_agent_reviewer, require_review_access
from app.schemas import AgentAuditRecordRead, AgentCommandDryRunRead, ControlledWriteCommandRead

router = APIRouter(prefix="/agent/commands", tags=["agent"])


@router.get("", response_model=list[ControlledWriteCommandRead])
def list_agent_commands(
    status: str = Query(default="ready"),
    limit: int = Query(default=50, ge=1, le=100),
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> list[ControlledWriteCommandRecord]:
    require_review_access(reviewer.permissions)
    return list(
        db.scalars(
            select(ControlledWriteCommandRecord)
            .where(ControlledWriteCommandRecord.status == status)
            .order_by(ControlledWriteCommandRecord.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.get("/{command_id}", response_model=ControlledWriteCommandRead)
def get_agent_command(
    command_id: str,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> ControlledWriteCommandRecord:
    require_review_access(reviewer.permissions)
    command = db.get(ControlledWriteCommandRecord, command_id)
    if command is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    return command


@router.post("/{command_id}/dry-run", response_model=AgentCommandDryRunRead)
def dry_run_agent_command(
    command_id: str,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> AgentCommandDryRunRead:
    result = dry_run_command(
        db,
        command_id=command_id,
        reviewer=reviewer.reviewer,
        permissions=reviewer.permissions,
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


@router.get("/{command_id}/audits", response_model=list[AgentAuditRecordRead])
def list_agent_command_audits(
    command_id: str,
    reviewer: AgentReviewer = Depends(get_agent_reviewer),
    db: Session = Depends(get_db),
) -> list[AgentAuditRecord]:
    require_review_access(reviewer.permissions)
    return list(
        db.scalars(
            select(AgentAuditRecord)
            .where(AgentAuditRecord.command_id == command_id)
            .order_by(AgentAuditRecord.created_at.desc())
        ).all()
    )
