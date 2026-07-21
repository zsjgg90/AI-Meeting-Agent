from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActionItem, ActionItemScopeBackfillAudit, Requirement, Risk

DEFAULT_TENANT_ID = "default-tenant"
DEFAULT_PROJECT_ID = "default-project"


@dataclass(frozen=True)
class ScopeResolution:
    tenant_id: str | None
    project_id: str | None
    status: str
    reason: str
    source_ref: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScopeBackfillStats:
    run_id: str
    dry_run: bool
    scanned: int = 0
    applied: int = 0
    review: int = 0
    skipped_existing: int = 0
    skipped_idempotent: int = 0
    rolled_back: int = 0
    rollback_conflict: int = 0


def backfill_action_item_scopes(
    db: Session,
    *,
    run_id: str,
    dry_run: bool = True,
    action_item_id_prefix: str | None = None,
) -> ScopeBackfillStats:
    stats = MutableScopeBackfillStats(run_id=run_id, dry_run=dry_run)
    query = select(ActionItem).order_by(ActionItem.created_at.asc(), ActionItem.id.asc())
    if action_item_id_prefix:
        query = query.where(ActionItem.id.like(f"{action_item_id_prefix}%"))
    items = list(db.scalars(query).all())
    for item in items:
        stats.scanned += 1
        existing_audit = get_backfill_audit(db, run_id=run_id, action_item_id=item.id)
        if existing_audit and existing_audit.status in {"applied", "review", "skipped_existing", "dry_run"}:
            increment_existing(stats, existing_audit.status)
            continue
        resolution = resolve_action_item_scope(db, item)
        audit = ActionItemScopeBackfillAudit(
            id=stable_backfill_audit_id(run_id, item.id),
            run_id=run_id,
            action_item_id=item.id,
            old_tenant_id=item.tenant_id,
            old_project_id=item.project_id,
            resolved_tenant_id=resolution.tenant_id,
            resolved_project_id=resolution.project_id,
            status="dry_run" if dry_run and resolution.status == "applied" else resolution.status,
            reason=resolution.reason,
            source_ref=resolution.source_ref,
            dry_run=dry_run,
            created_at=utc_now(),
            applied_at=None,
        )
        if resolution.status == "skipped_existing":
            stats.skipped_existing += 1
        elif resolution.status == "review":
            stats.review += 1
        elif dry_run:
            stats.applied += 1
        else:
            item.tenant_id = resolution.tenant_id or item.tenant_id
            item.project_id = resolution.project_id or item.project_id
            audit.status = "applied"
            audit.applied_at = utc_now()
            stats.applied += 1
        db.merge(audit)
    db.commit()
    return stats.freeze()


def rollback_action_item_scope_backfill(db: Session, *, run_id: str) -> ScopeBackfillStats:
    stats = MutableScopeBackfillStats(run_id=run_id, dry_run=False)
    audits = list(
        db.scalars(
            select(ActionItemScopeBackfillAudit)
            .where(
                ActionItemScopeBackfillAudit.run_id == run_id,
                ActionItemScopeBackfillAudit.status == "applied",
                ActionItemScopeBackfillAudit.rolled_back_at.is_(None),
            )
            .order_by(ActionItemScopeBackfillAudit.created_at.asc())
        ).all()
    )
    for audit in audits:
        stats.scanned += 1
        item = db.get(ActionItem, audit.action_item_id)
        if item is None:
            audit.status = "rollback_conflict"
            audit.reason = append_reason(audit.reason, "action_item_missing")
            stats.rollback_conflict += 1
            continue
        if item.tenant_id != audit.resolved_tenant_id or item.project_id != audit.resolved_project_id:
            audit.status = "rollback_conflict"
            audit.reason = append_reason(audit.reason, "current_scope_changed")
            stats.rollback_conflict += 1
            continue
        item.tenant_id = audit.old_tenant_id or DEFAULT_TENANT_ID
        item.project_id = audit.old_project_id or DEFAULT_PROJECT_ID
        audit.status = "rolled_back"
        audit.rolled_back_at = utc_now()
        stats.rolled_back += 1
    db.commit()
    return stats.freeze()


def resolve_action_item_scope(db: Session, item: ActionItem) -> ScopeResolution:
    if is_valid_scope(item.tenant_id, item.project_id):
        return ScopeResolution(
            tenant_id=item.tenant_id,
            project_id=item.project_id,
            status="skipped_existing",
            reason="existing_scope_valid",
            source_ref={"action_item_id": item.id},
        )
    candidates = scope_candidates_for_item(db, item)
    if len(candidates) == 1:
        (tenant_id, project_id), sources = next(iter(candidates.items()))
        return ScopeResolution(
            tenant_id=tenant_id,
            project_id=project_id,
            status="applied",
            reason="unique_authoritative_requirement_or_risk_scope",
            source_ref={"action_item_id": item.id, "sources": sources},
        )
    return ScopeResolution(
        tenant_id=None,
        project_id=None,
        status="review",
        reason="no_unique_verifiable_scope" if not candidates else "conflicting_authoritative_scopes",
        source_ref={
            "action_item_id": item.id,
            "candidate_count": len(candidates),
            "candidates": [{"tenant_id": tenant_id, "project_id": project_id} for tenant_id, project_id in candidates],
        },
    )


def scope_candidates_for_item(db: Session, item: ActionItem) -> dict[tuple[str, str], list[dict[str, Any]]]:
    candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in authoritative_rows_for_item(db, item):
        if not is_valid_scope(row.tenant_id, row.project_id):
            continue
        key = (row.tenant_id, row.project_id)
        candidates.setdefault(key, []).append(
            {
                "object_type": row.__class__.__name__,
                "object_id": row.id,
                "source_summary_id": row.source_summary_id,
                "source_meeting_id": row.source_meeting_id,
            }
        )
    return candidates


def authoritative_rows_for_item(db: Session, item: ActionItem) -> list[Requirement | Risk]:
    filters = []
    if item.summary_id:
        filters.append(("summary", item.summary_id))
    if item.meeting_id:
        filters.append(("meeting", item.meeting_id))
    rows: list[Requirement | Risk] = []
    if any(kind == "summary" for kind, _ in filters):
        rows.extend(db.scalars(select(Requirement).where(Requirement.source_summary_id == item.summary_id)).all())
        rows.extend(db.scalars(select(Risk).where(Risk.source_summary_id == item.summary_id)).all())
    if any(kind == "meeting" for kind, _ in filters):
        rows.extend(db.scalars(select(Requirement).where(Requirement.source_meeting_id == item.meeting_id)).all())
        rows.extend(db.scalars(select(Risk).where(Risk.source_meeting_id == item.meeting_id)).all())
    return rows


def is_valid_scope(tenant_id: str | None, project_id: str | None) -> bool:
    return bool(
        tenant_id
        and project_id
        and tenant_id != DEFAULT_TENANT_ID
        and project_id != DEFAULT_PROJECT_ID
    )


def get_backfill_audit(db: Session, *, run_id: str, action_item_id: str) -> ActionItemScopeBackfillAudit | None:
    return db.scalars(
        select(ActionItemScopeBackfillAudit).where(
            ActionItemScopeBackfillAudit.run_id == run_id,
            ActionItemScopeBackfillAudit.action_item_id == action_item_id,
        )
    ).first()


@dataclass
class MutableScopeBackfillStats:
    run_id: str
    dry_run: bool
    scanned: int = 0
    applied: int = 0
    review: int = 0
    skipped_existing: int = 0
    skipped_idempotent: int = 0
    rolled_back: int = 0
    rollback_conflict: int = 0

    def freeze(self) -> ScopeBackfillStats:
        return ScopeBackfillStats(**self.__dict__)


def increment_existing(stats: MutableScopeBackfillStats, status: str) -> None:
    stats.skipped_idempotent += 1
    if status == "review":
        stats.review += 1
    elif status == "skipped_existing":
        stats.skipped_existing += 1
    else:
        stats.applied += 1


def stable_backfill_audit_id(run_id: str, action_item_id: str) -> str:
    return f"scope-backfill-{uuid5(NAMESPACE_URL, f'{run_id}|{action_item_id}')}"


def append_reason(existing: str, reason: str) -> str:
    return f"{existing};{reason}" if existing else reason


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
