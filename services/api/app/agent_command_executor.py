from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authoritative_state import DatabaseAuthoritativeStateProvider
from app.agent_phase14_guardrails import evaluate_execution_guardrails, persist_guardrail_rejection_audit
from app.agent_security import AgentPrincipal, require_agent_permission
from app.config import Settings, get_settings
from app.models import ActionItem, AgentAuditRecord, ControlledWriteCommandRecord


PHASE13_PILOT_FIELDS = {"owner", "due_date", "priority", "status"}
PHASE13_PILOT_OPERATIONS = {"update", "complete"}
PHASE13_PILOT_RISK_LEVELS = {"low", "medium"}


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


@dataclass(frozen=True)
class TransactionRehearsalResult:
    command: ControlledWriteCommandRecord
    audit: AgentAuditRecord
    status: str
    rejection_reasons: list[str]
    authoritative_state: dict[str, Any] | None
    writes_performed: bool = False


@dataclass(frozen=True)
class CommandExecutionResult:
    command: ControlledWriteCommandRecord
    audit: AgentAuditRecord
    status: str
    rejection_reasons: list[str]
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    writes_performed: bool = True


@dataclass(frozen=True)
class CommandRollbackExecutionResult:
    command: ControlledWriteCommandRecord
    audit: AgentAuditRecord
    status: str
    rejection_reasons: list[str]
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    writes_performed: bool = True


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
    snapshot = DatabaseAuthoritativeStateProvider(
        db,
        principal=principal,
        view_permission="command_dry_run",
    ).get_state(
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
    snapshot = DatabaseAuthoritativeStateProvider(
        db,
        principal=principal,
        view_permission="rollback_execute",
    ).get_state(
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


def rehearse_command_transaction(
    db: Session,
    *,
    command_id: str,
    principal: AgentPrincipal,
    fail_stage: str | None = None,
) -> TransactionRehearsalResult:
    command = db.scalars(
        select(ControlledWriteCommandRecord)
        .where(ControlledWriteCommandRecord.id == command_id)
        .with_for_update()
    ).first()
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    existing = get_existing_rehearsal_audit(db, command_id)
    if existing is not None:
        return TransactionRehearsalResult(
            command=command,
            audit=existing,
            status="duplicate",
            rejection_reasons=["duplicate_execution_rehearsal"],
            authoritative_state=existing.audit_context.get("authoritative_state"),
        )
    if fail_stage == "after_command_lock":
        db.rollback()
        raise RuntimeError("phase12 rehearsal failure after command lock")

    snapshot = DatabaseAuthoritativeStateProvider(
        db,
        principal=principal,
        view_permission="command_execute",
    ).get_state(
        object_type=command.target_object_type,  # type: ignore[arg-type]
        object_id=command.target_object_id,
    )
    authoritative_state = snapshot.model_dump(mode="json") if snapshot else None
    reasons = validate_dry_run_request(command=command, snapshot=authoritative_state)
    if reasons:
        audit = persist_rehearsal_audit(
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
        raise HTTPException(status_code=status_code, detail={"status": "rejected", "reasons": reasons})
    if fail_stage == "before_audit":
        db.rollback()
        raise RuntimeError("phase12 rehearsal failure before audit")

    audit = persist_rehearsal_audit(
        db,
        command=command,
        reviewer=principal.reviewer_identity,
        result="execution_rehearsal",
        reasons=[],
        authoritative_state=authoritative_state,
    )
    if fail_stage == "after_audit":
        db.rollback()
        raise RuntimeError("phase12 rehearsal failure after audit")
    db.commit()
    db.refresh(audit)
    return TransactionRehearsalResult(
        command=command,
        audit=audit,
        status="execution_rehearsal",
        rejection_reasons=[],
        authoritative_state=authoritative_state,
    )


def persist_rehearsal_audit(
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
        decision="execution_rehearsal",
        result=result,
        reasons=sorted(set(reasons)),
        authoritative_source=authoritative_state.get("source") if authoritative_state else "none",
        authoritative_version=authoritative_state.get("object_version") if authoritative_state else None,
        audit_context={
            "phase": "agent-v1-phase12",
            "transaction_rehearsal": True,
            "writes_performed": False,
            "business_writes_performed": False,
            "idempotency_key": command.idempotency_key,
            "expected_changes": dict(command.changes or {}),
            "rollback_preview": dict(command.rollback_plan or {}),
            "authoritative_state": authoritative_state,
            "transaction_order": [
                "lock_command",
                "validate_ready",
                "reread_authoritative_state",
                "validate_permission_and_version",
                "skip_business_change_for_rehearsal",
                "write_agent_audit",
                "commit_single_transaction",
            ],
        },
    )
    return db.merge(audit)


def get_existing_rehearsal_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_rehearsal")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def execute_command_in_transaction(
    db: Session,
    *,
    command_id: str,
    principal: AgentPrincipal,
    settings: Settings | None = None,
    fail_stage: str | None = None,
) -> CommandExecutionResult:
    resolved_settings = settings or get_settings()
    validate_pilot_switches(resolved_settings, rollback=False)
    try:
        command = lock_command(db, command_id)
        existing = get_existing_execution_audit(db, command_id)
        if existing is not None and command.status == "succeeded":
            return CommandExecutionResult(
                command=command,
                audit=existing,
                status="duplicate",
                rejection_reasons=["duplicate_execution"],
                before_state=existing.audit_context.get("before_state"),
                after_state=existing.audit_context.get("after_state"),
            )
        if command.status != "ready":
            db.rollback()
            raise HTTPException(status_code=400, detail={"status": "rejected", "reasons": ["command_not_ready"]})
        if fail_stage == "after_command_lock":
            raise RuntimeError("phase13 execution failure after command lock")

        item = lock_action_item(db, command.target_object_id)
        before_state = action_item_snapshot(item)
        guardrail = evaluate_execution_guardrails(
            db,
            command=command,
            item=item,
            principal=principal,
            settings=resolved_settings,
        )
        if not guardrail.allowed:
            audit = persist_guardrail_rejection_audit(
                db,
                command=command,
                reviewer=principal.reviewer_identity,
                reasons=guardrail.reasons,
                item=item,
                context=guardrail.details,
            )
            db.commit()
            db.refresh(audit)
            raise HTTPException(status_code=guardrail.status_code, detail={"status": "rejected", "reasons": guardrail.reasons})
        validate_pilot_command(
            command=command,
            item=item,
            principal=principal,
            settings=resolved_settings,
            snapshot=before_state,
        )
        if fail_stage == "before_business_update":
            raise RuntimeError("phase13 execution failure before business update")

        apply_action_item_changes(item, command.changes or {})
        item.version += 1
        item.updated_at = utc_now()
        after_state = action_item_snapshot(item)
        if fail_stage == "after_business_update":
            raise RuntimeError("phase13 execution failure after business update")

        audit = persist_execution_audit(
            db,
            command=command,
            reviewer=principal.reviewer_identity,
            principal_user_id=principal.user_id,
            before_state=before_state,
            after_state=after_state,
        )
        if fail_stage == "after_audit":
            raise RuntimeError("phase13 execution failure after audit")
        command.status = "succeeded"
        command.audit_context = {
            **dict(command.audit_context or {}),
            "phase": "agent-v1-phase13",
            "pilot_execution": True,
            "writes_performed": True,
            "business_writes_performed": True,
            "principal_user_id": principal.user_id,
            "execution_audit_id": audit.id,
            "before_state": before_state,
            "after_state": after_state,
        }
        db.commit()
        db.refresh(command)
        db.refresh(audit)
        return CommandExecutionResult(
            command=command,
            audit=audit,
            status="succeeded",
            rejection_reasons=[],
            before_state=before_state,
            after_state=after_state,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def rollback_command_in_transaction(
    db: Session,
    *,
    command_id: str,
    principal: AgentPrincipal,
    confirmation_comment: str = "",
    settings: Settings | None = None,
    fail_stage: str | None = None,
) -> CommandRollbackExecutionResult:
    resolved_settings = settings or get_settings()
    validate_pilot_switches(resolved_settings, rollback=True)
    try:
        command = lock_command(db, command_id)
        existing = get_existing_rollback_execution_audit(db, command_id)
        if existing is not None and command.status == "rolled_back":
            return CommandRollbackExecutionResult(
                command=command,
                audit=existing,
                status="duplicate",
                rejection_reasons=["duplicate_rollback"],
                before_state=existing.audit_context.get("before_state"),
                after_state=existing.audit_context.get("after_state"),
            )
        if command.status != "succeeded":
            db.rollback()
            raise HTTPException(status_code=400, detail={"status": "rejected", "reasons": ["command_not_succeeded"]})
        execution_audit = get_existing_execution_audit(db, command_id)
        if execution_audit is None:
            db.rollback()
            raise HTTPException(status_code=400, detail={"status": "rejected", "reasons": ["missing_execution_audit"]})
        if fail_stage == "after_command_lock":
            raise RuntimeError("phase13 rollback failure after command lock")

        item = lock_action_item(db, command.target_object_id)
        before_state = action_item_snapshot(item)
        validate_pilot_rollback(
            command=command,
            item=item,
            principal=principal,
            settings=resolved_settings,
            execution_audit=execution_audit,
        )
        if fail_stage == "before_business_update":
            raise RuntimeError("phase13 rollback failure before business update")

        restore_changes = dict((command.rollback_plan or {}).get("restore_changes") or {})
        apply_action_item_changes(item, restore_changes)
        item.version += 1
        item.updated_at = utc_now()
        after_state = action_item_snapshot(item)
        if fail_stage == "after_business_update":
            raise RuntimeError("phase13 rollback failure after business update")

        audit = persist_rollback_execution_audit(
            db,
            command=command,
            reviewer=principal.reviewer_identity,
            confirmation_comment=confirmation_comment,
            before_state=before_state,
            after_state=after_state,
            execution_audit=execution_audit,
        )
        if fail_stage == "after_audit":
            raise RuntimeError("phase13 rollback failure after audit")
        command.status = "rolled_back"
        command.audit_context = {
            **dict(command.audit_context or {}),
            "phase": "agent-v1-phase13",
            "pilot_rollback": True,
            "rollback_audit_id": audit.id,
            "rollback_confirmation": {
                "reviewer": principal.reviewer_identity,
                "comment": confirmation_comment,
            },
        }
        db.commit()
        db.refresh(command)
        db.refresh(audit)
        return CommandRollbackExecutionResult(
            command=command,
            audit=audit,
            status="rolled_back",
            rejection_reasons=[],
            before_state=before_state,
            after_state=after_state,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def stable_dry_run_audit_id(command_id: str, result: str, reasons: list[str]) -> str:
    reason_key = ",".join(sorted(set(reasons)))
    return f"audit-dry-run-{uuid5(NAMESPACE_URL, f'{command_id}|{result}|{reason_key}')}"


def validate_pilot_switches(settings: Settings, *, rollback: bool) -> None:
    reasons: list[str] = []
    if not settings.agent_command_execution_enabled:
        reasons.append("command_execution_disabled")
    if settings.agent_command_dry_run_only:
        reasons.append("command_dry_run_only")
    if not settings.agent_command_pilot_enabled:
        reasons.append("command_pilot_disabled")
    if rollback and not settings.agent_rollback_execution_enabled:
        reasons.append("rollback_execution_disabled")
    if reasons:
        raise HTTPException(status_code=403, detail={"status": "rejected", "reasons": reasons})


def lock_command(db: Session, command_id: str) -> ControlledWriteCommandRecord:
    command = db.scalars(
        select(ControlledWriteCommandRecord)
        .where(ControlledWriteCommandRecord.id == command_id)
        .with_for_update()
    ).first()
    if command is None:
        raise HTTPException(status_code=404, detail="Controlled write command not found.")
    return command


def lock_action_item(db: Session, action_item_id: str) -> ActionItem:
    item = db.scalars(
        select(ActionItem)
        .where(ActionItem.id == action_item_id)
        .with_for_update()
    ).first()
    if item is None:
        db.rollback()
        raise HTTPException(status_code=404, detail={"status": "rejected", "reasons": ["target_not_found"]})
    return item


def validate_pilot_command(
    *,
    command: ControlledWriteCommandRecord,
    item: ActionItem,
    principal: AgentPrincipal,
    settings: Settings,
    snapshot: dict[str, Any],
) -> None:
    reasons = pilot_rejection_reasons(command=command, item=item, settings=settings, snapshot=snapshot)
    if reasons:
        raise HTTPException(status_code=pilot_status_code(reasons), detail={"status": "rejected", "reasons": reasons})
    require_agent_permission(
        principal,
        "command_execute",
        tenant_id=item.tenant_id,
        project_id=item.project_id,
        object_type="AgentActionItem",
        object_id=item.id,
        risk_level=proposal_risk_level(command),
        operation=command.operation,
    )


def validate_pilot_rollback(
    *,
    command: ControlledWriteCommandRecord,
    item: ActionItem,
    principal: AgentPrincipal,
    settings: Settings,
    execution_audit: AgentAuditRecord,
) -> None:
    snapshot = action_item_snapshot(item)
    reasons = pilot_rejection_reasons(command=command, item=item, settings=settings, snapshot=snapshot, rollback=True)
    after_state = execution_audit.audit_context.get("after_state") or {}
    expected_current_version = after_state.get("object_version")
    if expected_current_version and str(item.version) != str(expected_current_version):
        reasons.append("rollback_version_conflict")
    if reasons:
        raise HTTPException(status_code=pilot_status_code(reasons), detail={"status": "rejected", "reasons": sorted(set(reasons))})
    require_agent_permission(
        principal,
        "rollback_execute",
        tenant_id=item.tenant_id,
        project_id=item.project_id,
        object_type="AgentActionItem",
        object_id=item.id,
        risk_level=proposal_risk_level(command),
        operation="rollback",
    )


def pilot_rejection_reasons(
    *,
    command: ControlledWriteCommandRecord,
    item: ActionItem,
    settings: Settings,
    snapshot: dict[str, Any],
    rollback: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if command.target_object_type != "AgentActionItem":
        reasons.append("pilot_object_not_allowed")
    if command.operation not in PHASE13_PILOT_OPERATIONS:
        reasons.append("pilot_operation_not_allowed")
    if item.tenant_id not in settings.command_pilot_tenant_set:
        reasons.append("pilot_tenant_not_whitelisted")
    if item.project_id not in settings.command_pilot_project_set:
        reasons.append("pilot_project_not_whitelisted")
    risk_level = proposal_risk_level(command)
    if risk_level not in PHASE13_PILOT_RISK_LEVELS:
        reasons.append("pilot_risk_not_allowed")
    changes = dict((command.rollback_plan or {}).get("restore_changes") or {}) if rollback else dict(command.changes or {})
    if not changes:
        reasons.append("missing_changes")
    invalid_fields = sorted(field for field in changes if field not in PHASE13_PILOT_FIELDS)
    if invalid_fields:
        reasons.append("pilot_field_not_allowed:" + ",".join(invalid_fields))
    if not rollback and command.operation == "complete" and changes.get("status") not in {"completed", "done"}:
        reasons.append("pilot_complete_requires_completed_status")
    if not rollback and command.expected_version != snapshot.get("object_version"):
        reasons.append("version_conflict")
    return sorted(set(reasons))


def pilot_status_code(reasons: list[str]) -> int:
    if "version_conflict" in reasons or "rollback_version_conflict" in reasons:
        return 409
    if any("not_whitelisted" in reason or "not_allowed" in reason for reason in reasons):
        return 403
    return 400


def proposal_risk_level(command: ControlledWriteCommandRecord) -> str:
    proposal = command.proposal
    if proposal is None:
        return "unknown"
    return str(proposal.risk_level or "unknown").lower()


def action_item_snapshot(item: ActionItem) -> dict[str, Any]:
    updated_at = item.updated_at.isoformat() if item.updated_at else ""
    return {
        "object_type": "AgentActionItem",
        "object_id": item.id,
        "object_version": str(item.version),
        "status": item.status or "unknown",
        "updated_at": updated_at,
        "source": "postgresql.action_items",
        "data": {
            "title": item.task,
            "description": item.source_text or item.source or "",
            "owner": item.owner or item.owner_name,
            "due_date": item.due_date or item.deadline,
            "status": item.status,
            "priority": item.priority,
            "version": item.version,
            "tenant_id": item.tenant_id,
            "project_id": item.project_id,
            "meeting_id": item.meeting_id,
            "summary_id": item.summary_id,
        },
        "metadata": {"table": "action_items", "writes_performed": False},
    }


def apply_action_item_changes(item: ActionItem, changes: dict[str, Any]) -> None:
    for field in PHASE13_PILOT_FIELDS:
        if field in changes:
            setattr(item, field, changes[field])


def persist_execution_audit(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    reviewer: str,
    principal_user_id: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> AgentAuditRecord:
    audit = AgentAuditRecord(
        id=stable_execution_audit_id(command.id, "execution_succeeded"),
        proposal_id=command.proposal_id,
        confirmation_id=command.confirmation_id,
        command_id=command.id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation=command.operation,
        reviewer=reviewer,
        decision="execute",
        result="execution_succeeded",
        reasons=[],
        authoritative_source=after_state.get("source") or "postgresql.action_items",
        authoritative_version=after_state.get("object_version"),
        audit_context={
            "phase": "agent-v1-phase13",
            "pilot_execution": True,
            "writes_performed": True,
            "business_writes_performed": True,
            "principal_user_id": principal_user_id,
            "idempotency_key": command.idempotency_key,
            "expected_changes": dict(command.changes or {}),
            "rollback_preview": dict(command.rollback_plan or {}),
            "before_state": before_state,
            "after_state": after_state,
        },
    )
    return db.merge(audit)


def persist_rollback_execution_audit(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    reviewer: str,
    confirmation_comment: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    execution_audit: AgentAuditRecord,
) -> AgentAuditRecord:
    audit = AgentAuditRecord(
        id=stable_execution_audit_id(command.id, "rollback_succeeded"),
        proposal_id=command.proposal_id,
        confirmation_id=command.confirmation_id,
        command_id=command.id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation="rollback",
        reviewer=reviewer,
        decision="rollback_execute",
        result="rollback_succeeded",
        reasons=[],
        authoritative_source=after_state.get("source") or "postgresql.action_items",
        authoritative_version=after_state.get("object_version"),
        audit_context={
            "phase": "agent-v1-phase13",
            "pilot_rollback": True,
            "writes_performed": True,
            "business_writes_performed": True,
            "original_command_id": command.id,
            "execution_audit_id": execution_audit.id,
            "rollback_changes": dict((command.rollback_plan or {}).get("restore_changes") or {}),
            "rollback_confirmation": {
                "reviewer": reviewer,
                "comment": confirmation_comment,
            },
            "before_state": before_state,
            "after_state": after_state,
        },
    )
    return db.merge(audit)


def get_existing_execution_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "execution_succeeded")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def get_existing_rollback_execution_audit(db: Session, command_id: str) -> AgentAuditRecord | None:
    return db.scalars(
        select(AgentAuditRecord)
        .where(AgentAuditRecord.command_id == command_id, AgentAuditRecord.result == "rollback_succeeded")
        .order_by(AgentAuditRecord.created_at.desc())
    ).first()


def stable_execution_audit_id(command_id: str, result: str) -> str:
    return f"audit-execution-{uuid5(NAMESPACE_URL, f'{command_id}|{result}')}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
