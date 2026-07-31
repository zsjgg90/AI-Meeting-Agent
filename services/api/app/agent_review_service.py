from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agent_security import (
    AgentPrincipal,
    proposal_project_id,
    proposal_tenant_id,
    require_agent_permission,
)
from app.models import (
    ActionItem,
    AgentActionProposalRecord,
    AgentAuditRecord,
    AgentProposalConfirmationRecord,
    ControlledWriteCommandRecord,
    Meeting,
    Requirement,
    Risk,
)
from app.schemas import (
    AgentProposalConfirmationRead,
    AgentReviewAuditTimelineItemRead,
    AgentReviewChangeRead,
    AgentReviewCommandRead,
    AgentReviewEvidenceRead,
    AgentReviewOverviewRead,
    AgentReviewProposalCardRead,
    AgentReviewRecordDetailRead,
    AgentReviewRecordRead,
    AgentReviewRecordsRead,
)


CHANGE_LABELS = {
    "owner": "负责人",
    "due_date": "截止时间",
    "priority": "优先级",
    "status": "状态",
}
SENSITIVE_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization"}


def get_review_overview(db: Session, principal: AgentPrincipal) -> AgentReviewOverviewRead:
    pending_rows = visible_proposals(db, principal, status="pending", limit=100)
    records = list_review_records(db, principal, status="all", sort="latest", page=1, page_size=3)
    context = build_context(db, pending_rows[:3] + proposals_for_record_ids(db, [item.proposal_id for item in records.items]))
    return AgentReviewOverviewRead(
        pending_count=len(pending_rows),
        pending_proposals=[proposal_card(row, context) for row in pending_rows[:3]],
        recent_records=records.items,
    )


def list_review_records(
    db: Session,
    principal: AgentPrincipal,
    *,
    status: str = "all",
    sort: str = "latest",
    page: int = 1,
    page_size: int = 20,
) -> AgentReviewRecordsRead:
    status_values = proposal_statuses_for_filter(status)
    order = AgentActionProposalRecord.updated_at.asc() if sort == "oldest" else AgentActionProposalRecord.updated_at.desc()
    query = scope_filtered_proposal_query(
        select(AgentActionProposalRecord).where(AgentActionProposalRecord.status.in_(status_values)),
        principal,
    ).order_by(order)
    rows = list(db.scalars(query.limit(page_size * 4).offset(max(page - 1, 0) * page_size)).all())
    visible = [row for row in rows if can_view_proposal(principal, row)]
    context = build_context(db, visible)
    filtered = [row for row in visible if record_matches_filter(row, context["commands"].get(row.id), status)]
    page_rows = filtered[:page_size]
    total = count_visible_records(db, principal, status_values, status)
    items = [record_item(row, context) for row in page_rows]
    return AgentReviewRecordsRead(items=items, total=total, page=page, page_size=page_size, has_more=page * page_size < total)


def get_review_record_detail(db: Session, principal: AgentPrincipal, record_id: str) -> AgentReviewRecordDetailRead:
    row = db.get(AgentActionProposalRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent review record not found.")
    require_view_proposal(principal, row)
    context = build_context(db, [row])
    confirmation = context["confirmations"].get(row.id)
    command = context["commands"].get(row.id)
    audits = context["audits"].get(row.id, [])
    timeline = [
        AgentReviewAuditTimelineItemRead(
            id=audit.id,
            result=audit.result,
            result_label=status_label(audit.result),
            decision=audit.decision,
            reviewer=audit.reviewer,
            operation=audit.operation,
            reasons=list(audit.reasons or []),
            writes_performed=bool((audit.audit_context or {}).get("writes_performed")),
            created_at=audit.created_at,
        )
        for audit in audits
    ]
    writes_performed = any(item.writes_performed for item in timeline)
    execution_audit = next((audit for audit in audits if audit.result in {"execution_succeeded", "rollback_succeeded"}), None)
    return AgentReviewRecordDetailRead(
        id=row.id,
        proposal=proposal_card(row, context),
        confirmation=AgentProposalConfirmationRead.model_validate(confirmation) if confirmation else None,
        command=command_read(command) if command else None,
        before_after=change_rows(row.proposed_changes or {}, context["snapshots"].get(row.target_object_id or "")),
        evidence=evidence_read(row, context),
        reviewer=confirmation.reviewer if confirmation else None,
        executor=execution_audit.reviewer if execution_audit else None,
        audit_timeline=timeline,
        reject_reason=reject_reason(confirmation, audits),
        rollback_reason=rollback_reason(audits),
        writes_performed=writes_performed,
        object_version_before=row.expected_object_version,
        object_version_after=object_version_after(execution_audit),
    )


def visible_proposals(
    db: Session,
    principal: AgentPrincipal,
    *,
    status: str,
    limit: int,
) -> list[AgentActionProposalRecord]:
    rows = list(
        db.scalars(
            select(AgentActionProposalRecord)
            .where(AgentActionProposalRecord.status == status)
            .order_by(AgentActionProposalRecord.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [row for row in rows if can_view_proposal(principal, row)]


def count_visible_records(db: Session, principal: AgentPrincipal, statuses: set[str], status_filter: str) -> int:
    candidate_ids = list(
        db.scalars(
            scope_filtered_proposal_query(
                select(AgentActionProposalRecord.id).where(AgentActionProposalRecord.status.in_(statuses)),
                principal,
            )
        ).all()
    )
    if not candidate_ids:
        return 0
    rows = list(db.scalars(select(AgentActionProposalRecord).where(AgentActionProposalRecord.id.in_(candidate_ids))).all())
    context = build_context(db, rows)
    return sum(1 for row in rows if can_view_proposal(principal, row) and record_matches_filter(row, context["commands"].get(row.id), status_filter))


def build_context(db: Session, proposals: list[AgentActionProposalRecord]) -> dict[str, Any]:
    proposal_ids = [row.id for row in proposals]
    action_ids = [row.target_object_id for row in proposals if row.target_object_type == "AgentActionItem" and row.target_object_id]
    requirement_ids = [row.target_object_id for row in proposals if row.target_object_type == "Requirement" and row.target_object_id]
    risk_ids = [row.target_object_id for row in proposals if row.target_object_type == "Risk" and row.target_object_id]

    action_items = {item.id: item for item in db.scalars(select(ActionItem).where(ActionItem.id.in_(action_ids))).all()} if action_ids else {}
    requirements = {item.id: item for item in db.scalars(select(Requirement).where(Requirement.id.in_(requirement_ids))).all()} if requirement_ids else {}
    risks = {item.id: item for item in db.scalars(select(Risk).where(Risk.id.in_(risk_ids))).all()} if risk_ids else {}

    source_meeting_ids = set(source_meeting_id(row) for row in proposals)
    source_meeting_ids.update(item.meeting_id for item in action_items.values())
    source_meeting_ids.update(item.source_meeting_id for item in requirements.values() if item.source_meeting_id)
    source_meeting_ids.update(item.source_meeting_id for item in risks.values() if item.source_meeting_id)
    meetings = {
        item.id: item
        for item in db.scalars(select(Meeting).where(Meeting.id.in_(source_meeting_ids))).all()
    } if source_meeting_ids else {}

    confirmations = latest_by_proposal(
        db.scalars(
            select(AgentProposalConfirmationRecord)
            .where(AgentProposalConfirmationRecord.proposal_id.in_(proposal_ids))
            .order_by(AgentProposalConfirmationRecord.reviewed_at.desc())
        ).all()
    )
    commands = latest_by_proposal(
        db.scalars(
            select(ControlledWriteCommandRecord)
            .where(ControlledWriteCommandRecord.proposal_id.in_(proposal_ids))
            .order_by(ControlledWriteCommandRecord.created_at.desc())
        ).all()
    )
    audits = audits_by_proposal(
        db.scalars(
            select(AgentAuditRecord)
            .where(AgentAuditRecord.proposal_id.in_(proposal_ids))
            .order_by(AgentAuditRecord.created_at.desc())
        ).all()
    )
    snapshots = {
        **{key: action_snapshot(value) for key, value in action_items.items()},
        **{key: requirement_snapshot(value) for key, value in requirements.items()},
        **{key: risk_snapshot(value) for key, value in risks.items()},
    }
    return {
        "action_items": action_items,
        "requirements": requirements,
        "risks": risks,
        "meetings": meetings,
        "confirmations": confirmations,
        "commands": commands,
        "audits": audits,
        "snapshots": snapshots,
    }


def latest_by_proposal(rows: Iterable[Any]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for row in rows:
        latest.setdefault(row.proposal_id, row)
    return latest


def audits_by_proposal(rows: Iterable[AgentAuditRecord]) -> dict[str, list[AgentAuditRecord]]:
    grouped: dict[str, list[AgentAuditRecord]] = {}
    for row in rows:
        grouped.setdefault(row.proposal_id, []).append(row)
    return grouped


def command_read(command: ControlledWriteCommandRecord) -> AgentReviewCommandRead:
    return AgentReviewCommandRead(
        id=command.id,
        proposal_id=command.proposal_id,
        target_object_type=command.target_object_type,
        target_object_id=command.target_object_id,
        operation=command.operation,
        expected_version=command.expected_version,
        changes=sanitize_dict(command.changes or {}),
        status=command.status,
        created_at=command.created_at,
    )


def proposals_for_record_ids(db: Session, proposal_ids: list[str]) -> list[AgentActionProposalRecord]:
    if not proposal_ids:
        return []
    return list(db.scalars(select(AgentActionProposalRecord).where(AgentActionProposalRecord.id.in_(proposal_ids))).all())


def scope_filtered_proposal_query(query: Any, principal: AgentPrincipal) -> Any:
    if principal.tenant_id and principal.tenant_id != "*":
        query = query.where(
            or_(
                AgentActionProposalRecord.metadata_["tenant_id"].as_string() == principal.tenant_id,
                AgentActionProposalRecord.metadata_["tenant"].as_string() == principal.tenant_id,
            )
        )
    if principal.project_ids and "*" not in principal.project_ids:
        query = query.where(
            or_(
                AgentActionProposalRecord.metadata_["project_id"].as_string().in_(principal.project_ids),
                AgentActionProposalRecord.metadata_["project"].as_string().in_(principal.project_ids),
                AgentActionProposalRecord.metadata_["scope_project_id"].as_string().in_(principal.project_ids),
            )
        )
    return query


def proposal_card(row: AgentActionProposalRecord, context: dict[str, Any]) -> AgentReviewProposalCardRead:
    evidence = evidence_read(row, context)
    return AgentReviewProposalCardRead(
        id=row.id,
        action_type=row.action_type,
        action_label=action_label(row),
        target_object_type=row.target_object_type,
        target_object_id=row.target_object_id,
        target_title=target_title(row, context),
        source_meeting_title=evidence.source_meeting_title if evidence else None,
        source_meeting_time=evidence.source_meeting_time if evidence else None,
        risk_level=row.risk_level,
        risk_label=risk_label(row.risk_level),
        status=row.status,
        status_label=status_label(row.status),
        changes=change_rows(row.proposed_changes or {}, context["snapshots"].get(row.target_object_id or "")),
        evidence=evidence,
        created_at=row.created_at,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
    )


def record_item(row: AgentActionProposalRecord, context: dict[str, Any]) -> AgentReviewRecordRead:
    command = context["commands"].get(row.id)
    confirmation = context["confirmations"].get(row.id)
    status = record_status(row, command)
    return AgentReviewRecordRead(
        id=row.id,
        proposal_id=row.id,
        command_id=command.id if command else None,
        action_type=row.action_type,
        action_label=record_action_label(row, command, context),
        target_object_type=row.target_object_type,
        target_object_id=row.target_object_id,
        target_title=target_title(row, context),
        change_summary=change_summary(row.proposed_changes or {}, context["snapshots"].get(row.target_object_id or "")),
        handled_at=confirmation.reviewed_at if confirmation else row.updated_at,
        status=status,
        status_label=status_label(status),
        reason_preview=confirmation.comment if row.status in {"rejected"} and confirmation else None,
    )


def record_status(row: AgentActionProposalRecord, command: ControlledWriteCommandRecord | None) -> str:
    if command and command.status in {"ready", "succeeded", "rolled_back"}:
        return command.status
    if row.status == "approved":
        return "ready"
    return row.status


def proposal_statuses_for_filter(status: str) -> set[str]:
    if status == "pending_effective":
        return {"approved"}
    if status in {"succeeded", "rolled_back"}:
        return {"approved"}
    if status in {"rejected", "expired", "conflict"}:
        return {status}
    return {"approved", "rejected", "expired", "conflict"}


def require_view_proposal(principal: AgentPrincipal, row: AgentActionProposalRecord) -> None:
    require_agent_permission(
        principal,
        "proposal_view",
        tenant_id=proposal_tenant_id(row.metadata_),
        project_id=proposal_project_id(row.metadata_),
        object_type=row.target_object_type,
        object_id=row.target_object_id or row.id,
        risk_level=row.risk_level,
        operation=row.action_type,
    )


def can_view_proposal(principal: AgentPrincipal, row: AgentActionProposalRecord) -> bool:
    try:
        require_view_proposal(principal, row)
        return True
    except HTTPException:
        return False


def action_label(row: AgentActionProposalRecord) -> str:
    if row.target_object_type == "AgentActionItem" and row.action_type == "complete":
        return "完成待办"
    if row.target_object_type == "AgentActionItem":
        return "更新待办"
    if row.target_object_type == "Requirement":
        return "更新需求"
    if row.target_object_type == "Risk":
        return "更新风险"
    return "更新记录"


def record_action_label(row: AgentActionProposalRecord, command: ControlledWriteCommandRecord | None, context: dict[str, Any]) -> str:
    if command and command.status == "rolled_back":
        return f"撤销修改：{target_title(row, context)}"
    if row.status == "rejected":
        return f"不采纳：{target_title(row, context)}"
    return f"{action_label(row)}：{target_title(row, context)}"


def record_matches_filter(row: AgentActionProposalRecord, command: ControlledWriteCommandRecord | None, status_filter: str) -> bool:
    status = record_status(row, command)
    if status_filter == "all":
        return True
    if status_filter == "pending_effective":
        return status in {"approved", "ready", "duplicate", "dry_run"}
    return status == status_filter


def target_title(row: AgentActionProposalRecord, context: dict[str, Any]) -> str:
    object_id = row.target_object_id or ""
    if row.target_object_type == "AgentActionItem" and object_id in context.get("action_items", {}):
        return context["action_items"][object_id].task
    if row.target_object_type == "Requirement" and object_id in context.get("requirements", {}):
        return context["requirements"][object_id].title
    if row.target_object_type == "Risk" and object_id in context.get("risks", {}):
        return context["risks"][object_id].title
    return row.title or row.description or object_id or "未命名对象"


def source_meeting_id(row: AgentActionProposalRecord) -> str | None:
    evidence = first_evidence(row)
    if evidence and evidence.get("source_meeting_id"):
        return str(evidence["source_meeting_id"])
    metadata = row.metadata_ or {}
    value = metadata.get("source_meeting_id") or metadata.get("meeting_id")
    return str(value) if value else None


def evidence_read(row: AgentActionProposalRecord, context: dict[str, Any]) -> AgentReviewEvidenceRead | None:
    evidence = first_evidence(row)
    if not evidence:
        return None
    meeting_id = str(evidence.get("source_meeting_id") or source_meeting_id(row) or "")
    meeting = context.get("meetings", {}).get(meeting_id)
    return AgentReviewEvidenceRead(
        source_text=str(evidence.get("source_text") or "")[:500],
        speaker=str(evidence.get("speaker") or evidence.get("speaker_name") or "") or None,
        source_meeting_id=meeting_id or None,
        source_meeting_title=meeting.title if meeting else None,
        source_meeting_time=(meeting.start_at or meeting.created_at) if meeting else None,
        source_segment_id=str(evidence.get("source_segment_id") or "") or None,
    )


def first_evidence(row: AgentActionProposalRecord) -> dict[str, Any] | None:
    if not row.evidence:
        return None
    first = row.evidence[0]
    return sanitize_dict(first) if isinstance(first, dict) else None


def change_rows(changes: dict[str, Any], snapshot: dict[str, Any] | None) -> list[AgentReviewChangeRead]:
    rows: list[AgentReviewChangeRead] = []
    for field, value in changes.items():
        if field not in CHANGE_LABELS:
            continue
        before, after = change_before_after(field, value, snapshot)
        rows.append(AgentReviewChangeRead(field=field, label=CHANGE_LABELS[field], before=before, after=after))
    return rows


def change_before_after(field: str, value: Any, snapshot: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        before = value.get("from", value.get("before"))
        after = value.get("to", value.get("after", value.get("value")))
    else:
        before = snapshot.get(field) if snapshot else None
        after = value
    return stringify_value(before), stringify_value(after)


def stringify_value(value: Any) -> str | None:
    if value is None or value == "":
        return "未设置"
    return str(value)


def change_summary(changes: dict[str, Any], snapshot: dict[str, Any] | None) -> str:
    rows = change_rows(changes, snapshot)
    if not rows:
        return "查看详情"
    return "；".join(f"{row.label}：{row.before or '未设置'} -> {row.after or '未设置'}" for row in rows[:2])


def action_snapshot(item: ActionItem) -> dict[str, Any]:
    return {
        "title": item.task,
        "owner": item.owner or item.owner_name,
        "due_date": item.due_date or item.deadline,
        "priority": item.priority,
        "status": item.status,
        "version": item.version,
    }


def requirement_snapshot(item: Requirement) -> dict[str, Any]:
    return {"title": item.title, "owner": item.owner, "due_date": item.due_date, "priority": item.priority, "status": item.status, "version": item.version}


def risk_snapshot(item: Risk) -> dict[str, Any]:
    return {"title": item.title, "owner": item.owner, "due_date": item.due_date, "priority": item.priority, "status": item.status, "version": item.version}


def risk_label(value: str) -> str:
    return {
        "low": "可安全修改",
        "medium": "需要注意",
        "high": "需要管理员确认",
        "critical": "禁止普通用户处理",
    }.get(str(value).lower(), "需要注意")


def status_label(value: str) -> str:
    return {
        "pending": "待确认",
        "approved": "待生效",
        "ready": "待生效",
        "succeeded": "已生效",
        "execution_succeeded": "已生效",
        "rejected": "已拒绝",
        "rolled_back": "已撤销",
        "rollback_succeeded": "已撤销",
        "expired": "已过期",
        "conflict": "数据已更新",
        "duplicate": "待生效",
        "dry_run": "待生效",
    }.get(value, "待生效")


def reject_reason(confirmation: AgentProposalConfirmationRecord | None, audits: list[AgentAuditRecord]) -> str | None:
    if confirmation and confirmation.decision == "rejected":
        return confirmation.comment or "未填写原因"
    audit = next((item for item in audits if item.result == "rejected"), None)
    return "；".join(audit.reasons) if audit and audit.reasons else None


def rollback_reason(audits: list[AgentAuditRecord]) -> str | None:
    audit = next((item for item in audits if item.result == "rollback_succeeded"), None)
    if not audit:
        return None
    context = audit.audit_context or {}
    return str(context.get("confirmation_comment") or context.get("comment") or "已按审计记录撤销")


def object_version_after(audit: AgentAuditRecord | None) -> str | None:
    if not audit:
        return None
    context = audit.audit_context or {}
    after_state = context.get("after_state") if isinstance(context, dict) else None
    if isinstance(after_state, dict):
        version = after_state.get("object_version") or after_state.get("version")
        return str(version) if version is not None else None
    return None


def sanitize_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: ("[redacted]" if key.lower() in SENSITIVE_KEYS else sanitize_value(item)) for key, item in value.items()}


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return sanitize_dict(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value
