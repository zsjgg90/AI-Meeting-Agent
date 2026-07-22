from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agent_phase14_guardrails import (
    SENSITIVE_CONTEXT_KEYS,
    circuit_rejection_reasons,
    record_circuit_reset,
    scoped_context_value,
)
from app.agent_security import AgentPrincipal, get_agent_principal, require_agent_permission
from app.config import Settings, get_settings
from app.database import get_db
from app.models import AgentActionProposalRecord, AgentAuditRecord, ControlledWriteCommandRecord
from app.schemas import (
    AgentAuditRecordRead,
    AgentAuditSearchRead,
    AgentCircuitResetRead,
    AgentCircuitResetRequest,
    AgentCircuitStatusRead,
    AgentMetricsRead,
    AgentPreflightRead,
)

router = APIRouter(prefix="/agent/ops", tags=["agent"])


@router.get("/metrics", response_model=AgentMetricsRead)
def get_agent_metrics(
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentMetricsRead:
    rows = visible_audits(db, principal)
    totals = {
        "execute_requests": count_by_operation(rows, {"update", "complete"}),
        "success": count_by_result(rows, "execution_succeeded"),
        "failure": count_failures(rows),
        "rejected": count_by_result(rows, "rejected"),
        "duplicate": count_by_reason(rows, "duplicate_execution") + count_by_reason(rows, "duplicate_rollback"),
        "rollback_success": count_by_result(rows, "rollback_succeeded"),
        "rollback_failure": count_rollback_failures(rows),
        "version_conflict": count_reason_contains(rows, "version_conflict"),
        "permission_denied": count_reason_contains(rows, "permission_denied"),
        "whitelist_denied": count_reason_contains(rows, "whitelisted"),
        "audit_write_failure": count_reason_contains(rows, "audit_write_failed"),
        "circuit_triggers": count_reason_contains(rows, "circuit_"),
    }
    latencies = execution_latencies(rows)
    return AgentMetricsRead(
        totals=totals,
        execution_latency_ms={
            "avg": round(mean(latencies), 2) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        by_tenant=group_by_context(rows, "tenant_id"),
        by_project=group_by_context(rows, "project_id"),
        by_user=group_by_user(rows),
    )


@router.get("/audits", response_model=AgentAuditSearchRead)
def search_agent_audits(
    command_id: str | None = None,
    proposal_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    reviewer: str | None = None,
    executor: str | None = None,
    result: str | None = None,
    operation: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentAuditSearchRead:
    stmt = select(AgentAuditRecord).order_by(AgentAuditRecord.created_at.desc())
    if command_id:
        stmt = stmt.where(AgentAuditRecord.command_id == command_id)
    if proposal_id:
        stmt = stmt.where(AgentAuditRecord.proposal_id == proposal_id)
    if object_type:
        stmt = stmt.where(AgentAuditRecord.target_object_type == object_type)
    if object_id:
        stmt = stmt.where(AgentAuditRecord.target_object_id == object_id)
    if reviewer:
        stmt = stmt.where(AgentAuditRecord.reviewer == reviewer)
    if executor:
        stmt = stmt.where(AgentAuditRecord.reviewer == executor)
    if result:
        stmt = stmt.where(AgentAuditRecord.result == result)
    if operation:
        stmt = stmt.where(AgentAuditRecord.operation == operation)
    if start_at:
        stmt = stmt.where(AgentAuditRecord.created_at >= start_at)
    if end_at:
        stmt = stmt.where(AgentAuditRecord.created_at <= end_at)

    rows = [row for row in db.scalars(stmt).all() if audit_visible(row, principal)]
    if tenant_id:
        rows = [row for row in rows if scoped_context_value(row, "tenant_id") == tenant_id]
    if project_id:
        rows = [row for row in rows if scoped_context_value(row, "project_id") == project_id]
    page = rows[offset : offset + limit]
    return AgentAuditSearchRead(
        items=[AgentAuditRecordRead.model_validate(sanitize_audit(row)) for row in page],
        total=len(rows),
        limit=limit,
        offset=offset,
        has_more=offset + limit < len(rows),
    )


@router.get("/circuit-breakers", response_model=AgentCircuitStatusRead)
def get_circuit_status(
    tenant_id: str | None = None,
    project_id: str | None = None,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentCircuitStatusRead:
    settings = get_settings()
    scoped_tenant = tenant_id or principal.tenant_id or ""
    scoped_project = project_id or (principal.project_ids[0] if principal.project_ids else "")
    require_agent_permission(
        principal,
        "audit_view",
        tenant_id=scoped_tenant,
        project_id=scoped_project,
        object_type="AgentOps",
        object_id=f"{scoped_tenant}:{scoped_project}",
    )
    reasons = []
    if settings.agent_global_kill_switch:
        reasons.append("global_kill_switch_enabled")
    if settings.agent_grey_manual_paused:
        reasons.append("grey_manual_paused")
    reasons.extend(circuit_rejection_reasons(db, settings=settings, tenant_id=scoped_tenant, project_id=scoped_project))
    return AgentCircuitStatusRead(
        status="open" if reasons else "closed",
        reasons=sorted(set(reasons)),
        tenant_id=scoped_tenant,
        project_id=scoped_project,
        kill_switch_enabled=settings.agent_global_kill_switch,
        manual_paused=settings.agent_grey_manual_paused,
        recovery_hint="Clear kill/pause settings or POST /agent/ops/circuit-breakers/reset for audit-based circuit recovery.",
    )


@router.post("/circuit-breakers/reset", response_model=AgentCircuitResetRead)
def reset_circuit_status(
    payload: AgentCircuitResetRequest,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentCircuitResetRead:
    require_agent_permission(
        principal,
        "audit_view",
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        object_type="AgentOps",
        object_id=f"{payload.tenant_id}:{payload.project_id}",
    )
    audit = record_circuit_reset(
        db,
        principal=principal,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        reason=payload.reason,
    )
    return AgentCircuitResetRead(audit=AgentAuditRecordRead.model_validate(sanitize_audit(audit)), status="reset")


@router.get("/preflight", response_model=AgentPreflightRead)
def get_preflight(
    tenant_id: str | None = None,
    project_id: str | None = None,
    principal: AgentPrincipal = Depends(get_agent_principal),
    db: Session = Depends(get_db),
) -> AgentPreflightRead:
    settings = get_settings()
    checks: dict[str, dict[str, Any]] = {}
    hard_failures: list[str] = []

    add_check(checks, hard_failures, "safe_switches", not settings.agent_global_kill_switch and not settings.agent_grey_manual_paused, {
        "kill_switch": settings.agent_global_kill_switch,
        "manual_paused": settings.agent_grey_manual_paused,
    })
    add_check(checks, hard_failures, "grey_whitelist", bool(settings.agent_grey_enabled and settings.agent_grey_tenant_set and settings.agent_grey_project_set and settings.agent_grey_user_set), {
        "grey_enabled": settings.agent_grey_enabled,
        "tenant_count": len(settings.agent_grey_tenant_set),
        "project_count": len(settings.agent_grey_project_set),
        "user_count": len(settings.agent_grey_user_set),
        "percentage": settings.agent_grey_percentage,
    })
    add_check(checks, hard_failures, "auth_provider", principal.authentication_source != "unknown", {"source": principal.authentication_source})
    add_check(checks, hard_failures, "database_connection", database_ok(db), {})
    add_check(checks, hard_failures, "alembic_current_head", alembic_current(db) == alembic_head(), {"current": alembic_current(db), "head": alembic_head()})
    add_check(checks, hard_failures, "audit_writable", audit_writable(db), {})
    add_check(checks, hard_failures, "rollback_available", settings.agent_rollback_execution_enabled, {"rollback_execution_enabled": settings.agent_rollback_execution_enabled})
    scoped_tenant = tenant_id or principal.tenant_id or ""
    scoped_project = project_id or (principal.project_ids[0] if principal.project_ids else "")
    circuit_reasons = circuit_rejection_reasons(db, settings=settings, tenant_id=scoped_tenant, project_id=scoped_project)
    add_check(checks, hard_failures, "circuit_closed", not circuit_reasons, {"reasons": circuit_reasons})
    unresolved = db.scalar(select(func.count()).select_from(AgentActionProposalRecord).where(AgentActionProposalRecord.status == "pending")) or 0
    add_check(checks, hard_failures, "unresolved_review_data", unresolved == 0, {"pending_proposals": unresolved})
    add_check(checks, hard_failures, "recent_acceptance", latest_acceptance_hint() is not None, {"latest": latest_acceptance_hint()})

    return AgentPreflightRead(
        status="passed" if not hard_failures else "failed",
        can_enter_grey=not hard_failures,
        hard_failures=hard_failures,
        checks=checks,
    )


def visible_audits(db: Session, principal: AgentPrincipal) -> list[AgentAuditRecord]:
    rows = list(db.scalars(select(AgentAuditRecord).order_by(AgentAuditRecord.created_at.desc()).limit(1000)).all())
    return [row for row in rows if audit_visible(row, principal)]


def audit_visible(audit: AgentAuditRecord, principal: AgentPrincipal) -> bool:
    proposal_metadata = audit.proposal.metadata_ if audit.proposal else {}
    tenant_id = scoped_context_value(audit, "tenant_id") or proposal_metadata.get("tenant_id")
    project_id = scoped_context_value(audit, "project_id") or proposal_metadata.get("project_id")
    try:
        require_agent_permission(
            principal,
            "audit_view",
            tenant_id=tenant_id or principal.tenant_id,
            project_id=project_id or (principal.project_ids[0] if principal.project_ids else None),
            object_type=audit.target_object_type,
            object_id=audit.target_object_id,
            risk_level=None,
            operation=audit.operation,
        )
        return True
    except HTTPException:
        return False


def sanitize_audit(row: AgentAuditRecord) -> AgentAuditRecord:
    row.audit_context = sanitize_context(dict(row.audit_context or {}))
    return row


def sanitize_context(value: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in SENSITIVE_CONTEXT_KEYS:
            clean[key] = "[redacted]"
        elif isinstance(item, dict):
            clean[key] = sanitize_context(item)
        else:
            clean[key] = item
    return clean


def count_by_result(rows: list[AgentAuditRecord], result: str) -> int:
    return sum(1 for row in rows if row.result == result)


def count_by_operation(rows: list[AgentAuditRecord], operations: set[str]) -> int:
    return sum(1 for row in rows if row.operation in operations and row.decision == "execute")


def count_failures(rows: list[AgentAuditRecord]) -> int:
    return sum(1 for row in rows if row.result.endswith("_failed") or row.result == "rejected")


def count_rollback_failures(rows: list[AgentAuditRecord]) -> int:
    return sum(1 for row in rows if row.operation == "rollback" and (row.result.endswith("_failed") or row.result == "rejected"))


def count_by_reason(rows: list[AgentAuditRecord], reason: str) -> int:
    return sum(1 for row in rows if reason in row.reasons)


def count_reason_contains(rows: list[AgentAuditRecord], needle: str) -> int:
    return sum(1 for row in rows if any(needle in reason for reason in row.reasons))


def execution_latencies(rows: list[AgentAuditRecord]) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = (row.audit_context or {}).get("duration_ms")
        if isinstance(value, int | float):
            values.append(float(value))
    return values


def group_by_context(rows: list[AgentAuditRecord], key: str) -> dict[str, int]:
    grouped: dict[str, int] = {}
    for row in rows:
        value = scoped_context_value(row, key) or "unknown"
        grouped[value] = grouped.get(value, 0) + 1
    return grouped


def group_by_user(rows: list[AgentAuditRecord]) -> dict[str, int]:
    grouped: dict[str, int] = {}
    for row in rows:
        value = str((row.audit_context or {}).get("principal_user_id") or row.reviewer or "unknown")
        grouped[value] = grouped.get(value, 0) + 1
    return grouped


def database_ok(db: Session) -> bool:
    try:
        db.execute(text("select 1"))
        return True
    except Exception:
        return False


def alembic_current(db: Session) -> str | None:
    try:
        return db.execute(text("select version_num from alembic_version")).scalar()
    except Exception:
        return None


def alembic_head() -> str | None:
    versions = sorted(Path(__file__).resolve().parents[2].joinpath("alembic", "versions").glob("*.py"))
    if not versions:
        return None
    parts = versions[-1].name.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else versions[-1].stem


def audit_writable(db: Session) -> bool:
    try:
        db.execute(select(AgentAuditRecord.id).limit(1))
        return True
    except Exception:
        return False


def latest_acceptance_hint() -> str | None:
    script = Path(__file__).resolve().parents[2].joinpath("scripts", "run_agent_phase14_postgres_acceptance.py")
    return str(script) if script.exists() else None


def add_check(checks: dict[str, dict[str, Any]], hard_failures: list[str], name: str, passed: bool, details: dict[str, Any]) -> None:
    checks[name] = {"status": "ok" if passed else "failed", **details}
    if not passed:
        hard_failures.append(name)
