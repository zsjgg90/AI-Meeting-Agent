from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authoritative_state import DatabaseAuthoritativeStateProvider
from app.agent_security import AgentPrincipal
from app.config import Settings, get_settings
from app.models import AgentAuditRecord, ControlledWriteCommandRecord


@dataclass(frozen=True)
class DryRunResult:
    command: ControlledWriteCommandRecord
    audit: AgentAuditRecord
    status: str
    rejection_reasons: list[str]
    authoritative_state: dict[str, Any] | None
    expected_changes: dict[str, Any]
    rollback_preview: dict[str, Any]
    writes_performed: bool = False


@dataclass(frozen=True)
class RollbackDryRunResult:
    command: ControlledWriteCommandRecord
    audit: AgentAuditRecord
    status: str
    rejection_reasons: list[str]
    rollback_command: dict[str, Any]
    rollback_preview: dict[str, Any]
    authoritative_state: dict[str, Any] | None
    writes_performed: bool = False


def dry_run_command(
    db: Session,
    *,
    command_id: str,
    principal: AgentPrincipal,
    settings: Settings | None = None,
) -> DryRunResult:
    resolved_settings = settings or get_settings()
    command = db.get(ControlledWriteCommandRecord, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    if not resolved_settings.agent_command_execution_enabled:
        audit = persist_dry_run_audit(
            db,
            command=command,
            reviewer=principal.reviewer_identity,
            result="rejected",
            reasons=["command_execution_disabled"],
            authoritative_state=None,
        )
        db.commit()
        db.refresh(audit)
        raise HTTPException(
            status_code=403,
            detail={"status": "rejected", "reasons": ["command_execution_disabled"]},
        )
    if not resolved_settings.agent_command_dry_run_only:
        raise HTTPException(status_code=403, detail={"status": "rejected", "reasons": ["real_write_not_supported"]})

    existing = get_existing_dry_run_audit(db, command.id)
    snapshot = DatabaseAuthoritativeStateProvider(db).get_state(
        object_type=command.target_object_type,  # type: ignore[arg-type]
        object_id=command.target_object_id,
    )
    authoritative_state = snapshot.model_dump(mode="json") if snapshot else None
    reasons = validate_dry_run_request(command=command, snapshot=authoritative_state)

    if existing is not None and not reasons:
        return DryRunResult(
            command=command,
            audit=existing,
            status="duplicate",
            rejection_reasons=["duplicate_dry_run"],
            authoritative_state=authoritative_state,
            expected_changes=dict(command.changes or {}),
            rollback_preview=dict(command.rollback_plan or {}),
        )

    if reasons:
        audit = persist_dry_run_audit(
            db,
            command=command,
            reviewer=principal.reviewer_identity,
            result="rejected",
            reasons=reasons,
            authoritative_state=authoritative_state,
        )
        db.commit()
        db.refresh(audit)
        status_code = 409 if "version_conflict" in reasons else 400
        if "permission_denied" in reasons:
            status_code = 403
        raise HTTPException(status_code=status_code, detail={"status": "rejected", "reasons": reasons})

    audit = persist_dry_run_audit(
        db,
        command=command,
        reviewer=principal.reviewer_identity,
        result="dry_run",
        reasons=[],
        authoritative_state=authoritative_state,
    )
    db.commit()
    db.refresh(audit)
    return DryRunResult(
        command=command,
        audit=audit,
        status="dry_run",
        rejection_reasons=[],
        authoritative_state=authoritative_state,
        expected_changes=dict(command.changes or {}),
        rollback_preview=dict(command.rollback_plan or {}),
    )


def validate_dry_run_request(
    *,
    command: ControlledWriteCommandRecord,
    snapshot: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if command.status != "ready":
        reasons.append("command_not_ready")
    if not command.idempotency_key:
        reasons.append("missing_idempotency_key")
    if snapshot is None:
        reasons.append("target_not_found")
    elif command.expected_version != snapshot.get("object_version"):
        reasons.append("version_conflict")
    if not command.changes:
        reasons.append("missing_changes")
    return sorted(set(reasons))


def rollback_dry_run_command(
    db: Session,
    *,
    command_id: str,
    principal: AgentPrincipal,
    settings: Settings | None = None,
) -> RollbackDryRunResult:
    resolved_settings = settings or get_settings()
    command = db.get(ControlledWriteCommandRecord, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    if resolved_settings.agent_rollback_execution_enabled:
        raise HTTPException(status_code=403, detail={"status": "rejected", "reasons": ["real_rollback_not_supported"]})

    existing = get_existing_rollback_dry_run_audit(db, command.id)
    snapshot = DatabaseAuthoritativeStateProvider(db).get_state(
        object_type=command.target_object_type,  # type: ignore[arg-type]
        object_id=command.target_object_id,
    )
    authoritative_state = snapshot.model_dump(mode="json") if snapshot else None
    reasons = validate_rollback_dry_run_request(db=db, command=command, snapshot=authoritative_state)
    rollback_command = build_rollback_command(command=command, reviewer=principal.reviewer_identity)

    if existing is not None and not reasons:
        return RollbackDryRunResult(
            command=command,
            audit=existing,
            status="duplicate",
            rejection_reasons=["duplicate_rollback_dry_run"],
            rollback_command=rollback_command,
            rollback_preview=dict(command.rollback_plan or {}),
            authoritative_state=authoritative_state,
        )

    if reasons:
        audit = persist_rollback_dry_run_audit(
            db,
            command=command,
            reviewer=principal.reviewer_identity,
            result="rejected",
            reasons=reasons,
            authoritative_state=authoritative_state,
            rollback_command=rollback_command,
        )
        db.commit()
        db.refresh(audit)
        status_code = 409 if "rollback_version_conflict" in reasons else 400
        raise HTTPException(status_code=status_code, detail={"status": "rejected", "reasons": reasons})

    audit = persist_rollback_dry_run_audit(
        db,
        command=command,
        reviewer=principal.reviewer_identity,
        result="rollback_dry_run",
        reasons=[],
        authoritative_state=authoritative_state,
        rollback_command=rollback_command,
    )
    db.commit()
    db.refresh(audit)
    return RollbackDryRunResult(
        command=command,
        audit=audit,
        status="rollback_dry_run",
        rejection_reasons=[],
        rollback_command=rollback_command,
        rollback_preview=dict(command.rollback_plan or {}),
        authoritative_state=authoritative_state,
    )


def validate_rollback_dry_run_request(
    *,
    db: Session,
    command: ControlledWriteCommandRecord,
    snapshot: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if command.status != "ready":
        reasons.append("command_not_ready")
    if not command.rollback_plan:
        reasons.append("missing_rollback_plan")
    if not get_original_dry_run_marker(command) or get_existing_dry_run_audit(db, command.id) is None:
        reasons.append("missing_original_dry_run_audit")
    if snapshot is None:
        reasons.append("target_not_found")
    elif command.expected_version != snapshot.get("object_version"):
        reasons.append("rollback_version_conflict")
    return sorted(set(reasons))


def persist_dry_run_audit(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    reviewer: str,
    result: str,
    reasons: list[str],
    authoritative_state: dict[str, Any] | None,
) -> AgentAuditRecord:
    audit = AgentAuditRecord(
        id=stable_dry_run_audit_id(command.id, result, reasons),
        proposal_id=command.proposal_id,
        confirmation_id=command.confirmation_id,
        command_id=command.id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation=command.operation,
        reviewer=reviewer,
        decision="dry_run",
        result=result,
        reasons=sorted(set(reasons)),
        authoritative_source=authoritative_state.get("source") if authoritative_state else "none",
        authoritative_version=authoritative_state.get("object_version") if authoritative_state else None,
        audit_context={
            "dry_run": True,
            "writes_performed": False,
            "idempotency_key": command.idempotency_key,
            "expected_changes": dict(command.changes or {}),
            "rollback_preview": dict(command.rollback_plan or {}),
            "authoritative_state": authoritative_state,
        },
    )
    return db.merge(audit)


def persist_rollback_dry_run_audit(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    reviewer: str,
    result: str,
    reasons: list[str],
    authoritative_state: dict[str, Any] | None,
    rollback_command: dict[str, Any],
) -> AgentAuditRecord:
    audit = AgentAuditRecord(
        id=stable_dry_run_audit_id(command.id, result, reasons),
        proposal_id=command.proposal_id,
        confirmation_id=command.confirmation_id,
        command_id=command.id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation="rollback",
        reviewer=reviewer,
        decision="rollback_dry_run",
        result=result,
        reasons=sorted(set(reasons)),
        authoritative_source=authoritative_state.get("source") if authoritative_state else "none",
        authoritative_version=authoritative_state.get("object_version") if authoritative_state else None,
        audit_context={
            "dry_run": True,
            "rollback_dry_run": True,
            "writes_performed": False,
            "original_command_id": command.id,
            "rollback_command": rollback_command,
            "rollback_preview": dict(command.rollback_plan or {}),
            "authoritative_state": authoritative_state,
        },
    )
    return db.merge(audit)


def get_existing_dry_run_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "dry_run")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def get_existing_rollback_dry_run_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "rollback_dry_run")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def build_rollback_command(*, command: ControlledWriteCommandRecord, reviewer: str) -> dict[str, Any]:
    return {
        "command_id": f"rollback-{uuid5(NAMESPACE_URL, command.id)}",
        "original_command_id": command.id,
        "target_object_type": command.target_object_type,
        "target_object_id": command.target_object_id,
        "operation": "rollback",
        "expected_version": command.expected_version,
        "changes": (command.rollback_plan or {}).get("restore_changes", {}),
        "reviewer": reviewer,
        "dry_run": True,
        "writes_performed": False,
    }


def get_original_dry_run_marker(command: ControlledWriteCommandRecord) -> bool:
    context = command.audit_context or {}
    return context.get("writes_performed") is False and bool(command.idempotency_key)


def stable_dry_run_audit_id(command_id: str, result: str, reasons: list[str]) -> str:
    reason_key = ",".join(sorted(set(reasons)))
    return f"audit-dry-run-{uuid5(NAMESPACE_URL, f'{command_id}|{result}|{reason_key}')}"


def execute_command_in_transaction(*_: Any, **__: Any) -> None:
    """Phase 10 contract stub for the future real write executor.

    A later phase must implement authoritative re-read, expected-version check,
    command status check, idempotency recovery, one database transaction,
    business write, same-transaction audit, failure rollback, and final command
    status transition. Phase 10 deliberately refuses real writes.
    """

    raise HTTPException(status_code=403, detail={"status": "rejected", "reasons": ["real_write_not_supported"]})
