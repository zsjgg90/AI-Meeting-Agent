from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent_security import AgentPrincipal
from app.config import Settings
from app.models import ActionItem, AgentActionProposalRecord, AgentAuditRecord, ControlledWriteCommandRecord


EXECUTE_RESULTS = {"execution_succeeded", "rejected"}
FAILURE_RESULTS = {"rejected", "execution_failed", "rollback_failed"}
ROLLBACK_FAILURE_RESULTS = {"rejected", "rollback_failed"}
SENSITIVE_CONTEXT_KEYS = {"authorization", "token", "access_token", "refresh_token", "password", "secret", "api_key"}


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    status_code: int = 403
    details: dict[str, Any] = field(default_factory=dict)


def evaluate_execution_guardrails(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    item: ActionItem,
    principal: AgentPrincipal,
    settings: Settings,
) -> GuardrailDecision:
    reasons: list[str] = []
    details: dict[str, Any] = {
        "tenant_id": item.tenant_id,
        "project_id": item.project_id,
        "user_id": principal.user_id,
        "grey_percentage": settings.agent_grey_percentage,
    }

    reasons.extend(global_pause_reasons(settings, tenant_id=item.tenant_id, project_id=item.project_id))
    reasons.extend(grey_rejection_reasons(settings, tenant_id=item.tenant_id, project_id=item.project_id, user_id=principal.user_id))
    reasons.extend(quota_rejection_reasons(db, settings=settings, tenant_id=item.tenant_id, project_id=item.project_id, user_id=principal.user_id))
    reasons.extend(circuit_rejection_reasons(db, settings=settings, tenant_id=item.tenant_id, project_id=item.project_id))

    if reasons:
        return GuardrailDecision(False, sorted(set(reasons)), status_code_for_reasons(reasons), details)
    return GuardrailDecision(True, [], 200, details)


def global_pause_reasons(settings: Settings, *, tenant_id: str, project_id: str) -> list[str]:
    reasons: list[str] = []
    if settings.agent_global_kill_switch:
        reasons.append("global_kill_switch_enabled")
    if settings.agent_grey_manual_paused:
        reasons.append("grey_manual_paused")
    if tenant_id in settings.agent_paused_tenant_set:
        reasons.append("tenant_paused")
    if project_id in settings.agent_paused_project_set:
        reasons.append("project_paused")
    return reasons


def grey_rejection_reasons(settings: Settings, *, tenant_id: str, project_id: str, user_id: str) -> list[str]:
    reasons: list[str] = []
    if not settings.agent_grey_enabled:
        reasons.append("grey_disabled")
    if tenant_id not in settings.agent_grey_tenant_set:
        reasons.append("grey_tenant_not_whitelisted")
    if project_id not in settings.agent_grey_project_set:
        reasons.append("grey_project_not_whitelisted")
    if user_id not in settings.agent_grey_user_set:
        reasons.append("grey_user_not_whitelisted")
    if settings.agent_grey_percentage <= 0:
        reasons.append("grey_percentage_zero")
    elif not stable_percentage_allows(f"{tenant_id}|{project_id}|{user_id}", settings.agent_grey_percentage):
        reasons.append("grey_percentage_rejected")
    if not within_time_window(settings.agent_grey_window_start, settings.agent_grey_window_end):
        reasons.append("grey_time_window_closed")
    return reasons


def quota_rejection_reasons(
    db: Session,
    *,
    settings: Settings,
    tenant_id: str,
    project_id: str,
    user_id: str,
) -> list[str]:
    reasons: list[str] = []
    if settings.agent_grey_project_daily_limit <= 0:
        reasons.append("project_daily_limit_zero")
    elif count_today_successes(db, tenant_id=tenant_id, project_id=project_id, user_id=None) >= settings.agent_grey_project_daily_limit:
        reasons.append("project_daily_limit_exceeded")
    if settings.agent_grey_user_daily_limit <= 0:
        reasons.append("user_daily_limit_zero")
    elif count_today_successes(db, tenant_id=tenant_id, project_id=project_id, user_id=user_id) >= settings.agent_grey_user_daily_limit:
        reasons.append("user_daily_limit_exceeded")
    if settings.agent_grey_concurrency_limit <= 0:
        reasons.append("concurrency_limit_zero")
    elif count_running_commands(db, tenant_id=tenant_id, project_id=project_id) >= settings.agent_grey_concurrency_limit:
        reasons.append("concurrency_limit_exceeded")
    return reasons


def circuit_rejection_reasons(db: Session, *, settings: Settings, tenant_id: str, project_id: str) -> list[str]:
    recovery_time = parse_datetime(settings.agent_circuit_recovered_after)
    latest_reset = latest_circuit_reset(db, tenant_id=tenant_id, project_id=project_id)
    since = max(dt for dt in [recovery_time, latest_reset] if dt is not None) if recovery_time or latest_reset else None
    audits = scoped_audits(db, tenant_id=tenant_id, project_id=project_id, since=since, limit=10000)
    reasons: list[str] = []

    threshold = settings.agent_circuit_consecutive_failures
    if threshold > 0:
        recent_exec = [audit for audit in audits if audit.result in EXECUTE_RESULTS]
        last = recent_exec[:threshold]
        if len(last) >= threshold and all(audit.result in FAILURE_RESULTS for audit in last):
            reasons.append("circuit_consecutive_failures_open")

    rate_threshold = settings.agent_circuit_version_conflict_rate
    if rate_threshold > 0:
        recent_exec = [audit for audit in audits if audit.result in EXECUTE_RESULTS]
        if recent_exec:
            conflicts = [audit for audit in recent_exec if "version_conflict" in audit.reasons or "rollback_version_conflict" in audit.reasons]
            if len(conflicts) / len(recent_exec) >= rate_threshold:
                reasons.append("circuit_version_conflict_rate_open")

    rollback_threshold = settings.agent_circuit_rollback_failures
    if rollback_threshold > 0:
        rollback_failures = [
            audit
            for audit in audits
            if audit.operation == "rollback" and (audit.result in ROLLBACK_FAILURE_RESULTS or audit.reasons)
        ]
        if len(rollback_failures) >= rollback_threshold:
            reasons.append("circuit_rollback_failures_open")
    return reasons


def persist_guardrail_rejection_audit(
    db: Session,
    *,
    command: ControlledWriteCommandRecord,
    reviewer: str,
    reasons: list[str],
    item: ActionItem | None,
    context: dict[str, Any] | None = None,
) -> AgentAuditRecord:
    authoritative_state = action_item_guardrail_snapshot(item) if item else None
    audit = AgentAuditRecord(
        id=stable_guardrail_audit_id(command.id, reasons),
        proposal_id=command.proposal_id,
        confirmation_id=command.confirmation_id,
        command_id=command.id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation=command.operation,
        reviewer=reviewer,
        decision="execute",
        result="rejected",
        reasons=sorted(set(reasons)),
        authoritative_source="postgresql.action_items" if item else "none",
        authoritative_version=str(item.version) if item else None,
        audit_context={
            "phase": "agent-v1-phase14",
            "guardrail_rejection": True,
            "writes_performed": False,
            "business_writes_performed": False,
            "authoritative_state": authoritative_state,
            "guardrail_context": sanitize_mapping(context or {}),
        },
    )
    return db.merge(audit)


def record_circuit_reset(
    db: Session,
    *,
    principal: AgentPrincipal,
    tenant_id: str,
    project_id: str,
    reason: str,
) -> AgentAuditRecord:
    now = datetime.now(timezone.utc)
    ops_proposal = db.get(AgentActionProposalRecord, "agent-ops")
    if ops_proposal is None:
        ops_proposal = AgentActionProposalRecord(
            id="agent-ops",
            action_type="ops",
            target_object_type="AgentOps",
            target_object_id=f"{tenant_id}:{project_id}",
            expected_object_version=None,
            title="Agent operations audit anchor",
            description="Synthetic proposal anchor for Agent operations audit records.",
            proposed_changes={},
            evidence=[],
            confidence=None,
            risk_level="low",
            requires_confirmation=True,
            status="approved",
            reason="agent_ops_audit_anchor",
            metadata_={"tenant_id": tenant_id, "project_id": project_id},
            created_at=now,
            updated_at=now,
        )
        db.add(ops_proposal)
    audit = AgentAuditRecord(
        id=f"audit-circuit-reset-{uuid5(NAMESPACE_URL, f'{tenant_id}|{project_id}|{principal.user_id}|{now.isoformat()}')}",
        proposal_id="agent-ops",
        confirmation_id=None,
        command_id=None,
        target_object_type="AgentOps",
        target_object_id=f"{tenant_id}:{project_id}",
        operation="circuit_reset",
        reviewer=principal.reviewer_identity,
        decision="manual_restore",
        result="circuit_reset",
        reasons=[],
        authoritative_source="agent_audit_records",
        authoritative_version=now.isoformat(),
        audit_context={
            "phase": "agent-v1-phase14",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "user_id": principal.user_id,
            "reason": reason,
            "writes_performed": False,
            "business_writes_performed": False,
        },
        created_at=now,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def count_today_successes(db: Session, *, tenant_id: str, project_id: str, user_id: str | None) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = scoped_audits(db, tenant_id=tenant_id, project_id=project_id, since=start, limit=10000)
    successes = [row for row in rows if row.result == "execution_succeeded"]
    if user_id is not None:
        successes = [row for row in successes if row.audit_context.get("principal_user_id") == user_id or row.reviewer == user_id]
    return len(successes)


def count_running_commands(db: Session, *, tenant_id: str, project_id: str) -> int:
    rows = db.scalars(
        select(ControlledWriteCommandRecord).where(ControlledWriteCommandRecord.status == "running")
    ).all()
    count = 0
    for row in rows:
        proposal = row.proposal
        metadata = proposal.metadata_ if proposal else {}
        if metadata.get("tenant_id") == tenant_id and metadata.get("project_id") == project_id:
            count += 1
    return count


def scoped_audits(
    db: Session,
    *,
    tenant_id: str,
    project_id: str,
    since: datetime | None = None,
    limit: int = 100,
) -> list[AgentAuditRecord]:
    stmt = select(AgentAuditRecord).order_by(AgentAuditRecord.created_at.desc()).limit(limit)
    if since is not None:
        stmt = stmt.where(AgentAuditRecord.created_at >= since)
    rows = list(db.scalars(stmt).all())
    return [
        row
        for row in rows
        if scoped_context_value(row, "tenant_id") == tenant_id and scoped_context_value(row, "project_id") == project_id
    ]


def scoped_context_value(audit: AgentAuditRecord, key: str) -> str | None:
    context = audit.audit_context or {}
    guardrail_context = context.get("guardrail_context") if isinstance(context.get("guardrail_context"), dict) else {}
    for candidate in (
        context.get(key),
        guardrail_context.get(key),
        (context.get("before_state") or {}).get("data", {}).get(key) if isinstance(context.get("before_state"), dict) else None,
        (context.get("after_state") or {}).get("data", {}).get(key) if isinstance(context.get("after_state"), dict) else None,
        (context.get("authoritative_state") or {}).get("data", {}).get(key) if isinstance(context.get("authoritative_state"), dict) else None,
    ):
        if candidate:
            return str(candidate)
    return None


def latest_circuit_reset(db: Session, *, tenant_id: str, project_id: str) -> datetime | None:
    rows = list(
        db.scalars(
            select(AgentAuditRecord)
            .where(AgentAuditRecord.result == "circuit_reset")
            .order_by(AgentAuditRecord.created_at.desc())
            .limit(50)
        ).all()
    )
    for row in rows:
        context = row.audit_context or {}
        if context.get("tenant_id") == tenant_id and context.get("project_id") == project_id:
            return ensure_aware(row.created_at)
    return None


def stable_percentage_allows(key: str, percentage: int) -> bool:
    bounded = max(0, min(100, percentage))
    bucket = int(uuid5(NAMESPACE_URL, key).int % 100) + 1
    return bucket <= bounded


def within_time_window(start_value: str, end_value: str) -> bool:
    if not start_value.strip() and not end_value.strip():
        return True
    start = parse_time(start_value)
    end = parse_time(end_value)
    if start is None or end is None:
        return False
    now = datetime.now(timezone.utc).time()
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def parse_time(value: str) -> time | None:
    if not value.strip():
        return None
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute), tzinfo=timezone.utc)
    except Exception:
        return None


def parse_datetime(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ensure_aware(parsed)
    except ValueError:
        return None


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def action_item_guardrail_snapshot(item: ActionItem) -> dict[str, Any]:
    return {
        "object_type": "AgentActionItem",
        "object_id": item.id,
        "object_version": str(item.version),
        "data": {
            "tenant_id": item.tenant_id,
            "project_id": item.project_id,
            "status": item.status,
            "owner": item.owner,
            "due_date": item.due_date,
            "priority": item.priority,
        },
    }


def status_code_for_reasons(reasons: list[str]) -> int:
    if any(reason.endswith("_exceeded") for reason in reasons):
        return 429
    if any("circuit" in reason for reason in reasons):
        return 423
    return 403


def stable_guardrail_audit_id(command_id: str, reasons: list[str]) -> str:
    return f"audit-guardrail-{uuid5(NAMESPACE_URL, f'{command_id}|{','.join(sorted(set(reasons)))}')}"


def sanitize_mapping(value: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in SENSITIVE_CONTEXT_KEYS:
            clean[key] = "[redacted]"
        elif isinstance(item, dict):
            clean[key] = sanitize_mapping(item)
        else:
            clean[key] = item
    return clean
