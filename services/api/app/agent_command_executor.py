from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authoritative_state import DatabaseAuthoritativeStateProvider
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


def dry_run_command(
    db: Session,
    *,
    command_id: str,
    reviewer: str,
    permissions: list[str],
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
            reviewer=reviewer,
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
    reasons = validate_dry_run_request(command=command, permissions=permissions, snapshot=authoritative_state)

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
            reviewer=reviewer,
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
        reviewer=reviewer,
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
    permissions: list[str],
    snapshot: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    if command.status != "ready":
        reasons.append("command_not_ready")
    if not _has_command_permission(permissions, command):
        reasons.append("permission_denied")
    if not command.idempotency_key:
        reasons.append("missing_idempotency_key")
    if snapshot is None:
        reasons.append("target_not_found")
    elif command.expected_version != snapshot.get("object_version"):
        reasons.append("version_conflict")
    if not command.changes:
        reasons.append("missing_changes")
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


def get_existing_dry_run_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "dry_run")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def stable_dry_run_audit_id(command_id: str, result: str, reasons: list[str]) -> str:
    reason_key = ",".join(sorted(set(reasons)))
    return f"audit-dry-run-{uuid5(NAMESPACE_URL, f'{command_id}|{result}|{reason_key}')}"


def _has_command_permission(permissions: list[str], command: ControlledWriteCommandRecord) -> bool:
    accepted = {
        "*",
        "agent_write",
        f"agent_write:{command.target_object_type}",
        f"{command.operation}:{command.target_object_type}",
        f"{command.operation}:*",
    }
    return bool(set(permissions) & accepted)
