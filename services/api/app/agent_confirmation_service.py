from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_write_control import (
    AgentActionProposal,
    AgentProposalConfirmation,
    AuditRecord,
    ControlledWritePlanner,
    WriteControlResult,
)
from app.authoritative_state import DatabaseAuthoritativeStateProvider
from app.agent_security import AgentPrincipal
from app.models import (
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
)


PROPOSAL_STATUSES = {"pending", "approved", "rejected", "expired", "conflict"}
CONFIRMATION_STATUSES = {"approved", "rejected"}
COMMAND_STATUSES = {"ready", "rejected", "duplicate"}
TERMINAL_PROPOSAL_STATUSES = {"approved", "rejected", "expired", "conflict"}
REJECTION_STATUS_BY_REASON = {
    "version_conflict": "conflict",
    "confirmation_expired": "expired",
    "target_not_found": "conflict",
}
_DEFAULT_CONFIRMATION_ID = object()


def create_proposal(
    db: Session,
    payload: dict[str, Any],
    principal: AgentPrincipal | None = None,
) -> AgentActionProposalRecord:
    proposal = AgentActionProposal.model_validate(payload)
    if proposal.target_object_type not in {"Requirement", "AgentActionItem", "Risk"}:
        raise HTTPException(status_code=400, detail="Unsupported Agent proposal target object type.")
    provider = DatabaseAuthoritativeStateProvider(db, principal=principal, view_permission="proposal_review")
    snapshot = None
    if proposal.target_object_id and proposal.action_type not in {"new", "create"}:
        snapshot = provider.get_state(object_type=proposal.target_object_type, object_id=proposal.target_object_id)  # type: ignore[arg-type]
    now = utc_now()
    row = AgentActionProposalRecord(
        id=proposal.proposal_id or str(uuid4()),
        action_type=proposal.action_type or proposal.proposal_type or "unknown",
        target_object_type=proposal.target_object_type,
        target_object_id=proposal.target_object_id,
        expected_object_version=snapshot.object_version if snapshot else None,
        title=proposal.title,
        description=proposal.description,
        proposed_changes=proposal.proposed_changes,
        evidence=[item.model_dump(mode="json") for item in proposal.evidence],
        confidence=proposal.confidence,
        risk_level=proposal.risk_level,
        requires_confirmation=proposal.requires_confirmation,
        status="pending",
        reason=proposal.reason,
        metadata_=dict(proposal.metadata),
        expires_at=parse_datetime(proposal.metadata.get("expires_at")),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def approve_proposal(
    db: Session,
    *,
    proposal_id: str,
    reviewer: str,
    permissions: list[str],
    comment: str = "",
    principal: AgentPrincipal | None = None,
) -> tuple[AgentActionProposalRecord, AgentProposalConfirmationRecord, WriteControlResult]:
    row = lock_proposal_or_404(db, proposal_id)
    existing_command = get_ready_command(db, proposal_id)
    existing_confirmation = get_latest_confirmation(db, proposal_id)
    if row.status == "approved" and existing_command is not None and existing_confirmation is not None:
        result = result_from_persisted_command(existing_command, row)
        return row, existing_confirmation, result
    if row.status in TERMINAL_PROPOSAL_STATUSES:
        if existing_confirmation is not None:
            result = result_from_terminal_state(row, existing_confirmation)
            return row, existing_confirmation, result
        raise HTTPException(status_code=409, detail=f"Proposal is already {row.status}.")

    pending_confirmation = AgentProposalConfirmation(
        confirmation_id=str(uuid4()),
        proposal_id=row.id,
        decision="approved",
        reviewer=reviewer,
        comment=comment,
        expected_object_version=row.expected_object_version,
        permissions=permissions,
        metadata={"expires_at": row.expires_at.isoformat() if row.expires_at else None},
    )
    result = plan_controlled_write(db, row=row, confirmation=pending_confirmation, principal=principal)
    if result.status == "duplicate":
        duplicate = get_ready_command(db, proposal_id)
        duplicate_confirmation = get_latest_confirmation(db, proposal_id)
        if duplicate is not None and duplicate_confirmation is not None:
            return row, duplicate_confirmation, result_from_persisted_command(duplicate, row)

    if result.status == "ready" and result.command is not None:
        confirmation_row = persist_confirmation(db, pending_confirmation)
        command_row = ControlledWriteCommandRecord(
            id=result.command.command_id,
            proposal_id=row.id,
            target_object_type=result.command.target_object_type,
            target_object_id=result.command.target_object_id,
            operation=result.command.operation,
            expected_version=result.command.expected_version,
            changes=result.command.changes,
            idempotency_key=result.command.idempotency_key,
            confirmation_id=pending_confirmation.confirmation_id,
            audit_context=result.command.audit_context,
            rollback_plan=result.rollback_plan.model_dump(mode="json") if result.rollback_plan else {},
            status="ready",
        )
        db.add(command_row)
        db.flush()
        row.status = "approved"
    else:
        confirmation_row = None
        row.status = status_for_rejection(result.rejection_reasons)
    row.updated_at = utc_now()
    persist_audit(db, result.audit_record, confirmation_id=confirmation_row.id if confirmation_row else None)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return recover_duplicate_after_integrity_error(db, proposal_id)
    db.refresh(row)
    if confirmation_row is not None:
        db.refresh(confirmation_row)
        return row, confirmation_row, result
    raise_http_for_rejected_plan(row, result)
    raise HTTPException(status_code=400, detail={"status": row.status, "reasons": result.rejection_reasons})


def reject_proposal(
    db: Session,
    *,
    proposal_id: str,
    reviewer: str,
    permissions: list[str],
    comment: str = "",
) -> tuple[AgentActionProposalRecord, AgentProposalConfirmationRecord, AgentAuditRecord]:
    if not has_review_permission(permissions):
        raise HTTPException(status_code=403, detail="Agent proposal confirmation permission is required.")
    row = lock_proposal_or_404(db, proposal_id)
    existing_confirmation = get_latest_confirmation(db, proposal_id)
    if row.status == "rejected" and existing_confirmation is not None:
        audit = get_latest_audit(db, proposal_id)
        if audit is not None:
            return row, existing_confirmation, audit
        raise HTTPException(status_code=409, detail="Proposal is already rejected.")
    if row.status in TERMINAL_PROPOSAL_STATUSES:
        raise HTTPException(status_code=409, detail=f"Proposal is already {row.status}.")
    confirmation = AgentProposalConfirmation(
        confirmation_id=str(uuid4()),
        proposal_id=row.id,
        decision="rejected",
        reviewer=reviewer,
        comment=comment,
        expected_object_version=row.expected_object_version,
        permissions=permissions,
    )
    confirmation_row = persist_confirmation(db, confirmation)
    row.status = "rejected"
    row.updated_at = utc_now()
    audit = AgentAuditRecord(
        id=f"audit-{uuid4()}",
        proposal_id=row.id,
        confirmation_id=confirmation.confirmation_id,
        command_id=None,
        target_object_type=row.target_object_type,
        target_object_id=row.target_object_id or "",
        operation=row.action_type,
        reviewer=reviewer,
        decision="rejected",
        result="rejected",
        reasons=["human_rejected"],
        authoritative_source="none",
        authoritative_version=None,
        audit_context={"comment": comment, "writes_performed": False},
    )
    db.add(audit)
    db.commit()
    db.refresh(row)
    db.refresh(confirmation_row)
    db.refresh(audit)
    return row, confirmation_row, audit


def plan_controlled_write(
    db: Session,
    *,
    row: AgentActionProposalRecord,
    confirmation: AgentProposalConfirmation,
    principal: AgentPrincipal | None = None,
) -> WriteControlResult:
    provider = DatabaseAuthoritativeStateProvider(db, principal=principal, view_permission="proposal_review")
    existing_keys = set(db.scalars(select(ControlledWriteCommandRecord.idempotency_key)).all())
    planner = ControlledWritePlanner(state_provider=provider, seen_idempotency_keys=existing_keys)
    return planner.plan(proposal=proposal_from_record(row), confirmation=confirmation)


def proposal_from_record(row: AgentActionProposalRecord) -> AgentActionProposal:
    metadata = dict(row.metadata_ or {})
    if row.expires_at:
        metadata["expires_at"] = row.expires_at.isoformat()
    return AgentActionProposal(
        proposal_id=row.id,
        action_type=row.action_type,
        target_object_type=row.target_object_type,
        target_object_id=row.target_object_id,
        title=row.title,
        description=row.description,
        proposed_changes=row.proposed_changes or {},
        evidence=row.evidence or [],
        confidence=row.confidence,
        risk_level=row.risk_level,
        requires_confirmation=row.requires_confirmation,
        status="proposed",
        reason=row.reason,
        metadata=metadata,
    )


def persist_confirmation(db: Session, confirmation: AgentProposalConfirmation) -> AgentProposalConfirmationRecord:
    row = AgentProposalConfirmationRecord(
        id=confirmation.confirmation_id,
        proposal_id=confirmation.proposal_id,
        decision=confirmation.decision,
        reviewer=confirmation.reviewer,
        reviewed_at=parse_datetime(confirmation.reviewed_at) or utc_now(),
        comment=confirmation.comment,
        expected_object_version=confirmation.expected_object_version,
        permissions=confirmation.permissions,
        metadata_=confirmation.metadata,
    )
    db.add(row)
    db.flush()
    return row


def persist_audit(
    db: Session,
    audit: AuditRecord,
    *,
    confirmation_id: str | None | object = _DEFAULT_CONFIRMATION_ID,
) -> AgentAuditRecord:
    resolved_confirmation_id = audit.confirmation_id if confirmation_id is _DEFAULT_CONFIRMATION_ID else confirmation_id
    row = AgentAuditRecord(
        id=audit.audit_id,
        proposal_id=audit.proposal_id,
        confirmation_id=resolved_confirmation_id,
        command_id=audit.metadata.get("command_id"),
        target_object_type=audit.target_object_type,
        target_object_id=audit.target_object_id,
        operation=audit.operation,
        reviewer=audit.reviewer,
        decision=audit.decision,
        result=audit.result,
        reasons=audit.reasons,
        authoritative_source=audit.authoritative_source,
        authoritative_version=audit.authoritative_version,
        audit_context=audit.metadata,
    )
    db.add(row)
    return row


def get_proposal_or_404(db: Session, proposal_id: str) -> AgentActionProposalRecord:
    row = db.get(AgentActionProposalRecord, proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent action proposal not found.")
    return row


def lock_proposal_or_404(db: Session, proposal_id: str) -> AgentActionProposalRecord:
    row = db.scalars(
        select(AgentActionProposalRecord)
        .where(AgentActionProposalRecord.id == proposal_id)
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent action proposal not found.")
    return row


def get_ready_command(db: Session, proposal_id: str) -> ControlledWriteCommandRecord | None:
    return db.scalars(
        select(ControlledWriteCommandRecord)
        .where(
            ControlledWriteCommandRecord.proposal_id == proposal_id,
            ControlledWriteCommandRecord.status == "ready",
        )
        .order_by(ControlledWriteCommandRecord.created_at.desc())
    ).first()


def get_latest_confirmation(db: Session, proposal_id: str) -> AgentProposalConfirmationRecord | None:
    return db.scalars(
        select(AgentProposalConfirmationRecord)
        .where(AgentProposalConfirmationRecord.proposal_id == proposal_id)
        .order_by(AgentProposalConfirmationRecord.reviewed_at.desc())
    ).first()


def get_latest_audit(db: Session, proposal_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.proposal_id == proposal_id)
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def recover_duplicate_after_integrity_error(
    db: Session,
    proposal_id: str,
) -> tuple[AgentActionProposalRecord, AgentProposalConfirmationRecord, WriteControlResult]:
    duplicate = get_ready_command(db, proposal_id)
    duplicate_proposal = db.get(AgentActionProposalRecord, proposal_id)
    duplicate_confirmation = get_latest_confirmation(db, proposal_id)
    if duplicate is None or duplicate_proposal is None or duplicate_confirmation is None:
        raise HTTPException(status_code=409, detail="Command idempotency conflict could not be resolved.")
    result = result_from_persisted_command(duplicate, duplicate_proposal)
    return duplicate_proposal, duplicate_confirmation, result


def result_from_persisted_command(
    command: ControlledWriteCommandRecord,
    proposal: AgentActionProposalRecord,
) -> WriteControlResult:
    audit = AuditRecord(
        audit_id=f"audit-duplicate-{command.id}",
        proposal_id=proposal.id,
        confirmation_id=command.confirmation_id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation=command.operation,
        reviewer="",
        decision="approved",
        result="duplicate",
        reasons=["duplicate_command"],
        authoritative_source="persisted_command",
        authoritative_version=command.expected_version,
        metadata={"command_id": command.id, "writes_performed": False},
    )
    return WriteControlResult(status="duplicate", audit_record=audit, rejection_reasons=["duplicate_command"])


def result_from_terminal_state(
    proposal: AgentActionProposalRecord,
    confirmation: AgentProposalConfirmationRecord,
) -> WriteControlResult:
    command = get_ready_command_from_proposal(proposal)
    if proposal.status == "approved" and command is not None:
        return result_from_persisted_command(command, proposal)
    audit = AuditRecord(
        audit_id=f"audit-terminal-{proposal.id}",
        proposal_id=proposal.id,
        confirmation_id=confirmation.id,
        target_object_type=proposal.target_object_type,
        target_object_id=proposal.target_object_id or "",
        operation=proposal.action_type,
        reviewer=confirmation.reviewer,
        decision=confirmation.decision,
        result="rejected",
        reasons=[f"proposal_already_{proposal.status}"],
        authoritative_source="terminal_state",
        authoritative_version=proposal.expected_object_version,
        metadata={"writes_performed": False},
    )
    return WriteControlResult(status="rejected", audit_record=audit, rejection_reasons=[f"proposal_already_{proposal.status}"])


def get_ready_command_from_proposal(proposal: AgentActionProposalRecord) -> ControlledWriteCommandRecord | None:
    for command in proposal.commands:
        if command.status == "ready":
            return command
    return None


def status_for_rejection(reasons: list[str]) -> str:
    for reason, status in REJECTION_STATUS_BY_REASON.items():
        if reason in reasons:
            return status
    return "pending"


def raise_http_for_rejected_plan(row: AgentActionProposalRecord, result: WriteControlResult) -> None:
    if "version_conflict" in result.rejection_reasons:
        raise HTTPException(status_code=409, detail={"status": row.status, "reasons": result.rejection_reasons})
    if "target_not_found" in result.rejection_reasons:
        raise HTTPException(status_code=404, detail={"status": row.status, "reasons": result.rejection_reasons})
    if "permission_denied" in result.rejection_reasons:
        raise HTTPException(status_code=403, detail={"status": row.status, "reasons": result.rejection_reasons})
    if "confirmation_expired" in result.rejection_reasons:
        raise HTTPException(status_code=409, detail={"status": row.status, "reasons": result.rejection_reasons})
    raise HTTPException(status_code=400, detail={"status": row.status, "reasons": result.rejection_reasons})


def has_review_permission(permissions: list[str]) -> bool:
    return bool(set(permissions) & {"*", "agent_review", "agent_write"})


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
