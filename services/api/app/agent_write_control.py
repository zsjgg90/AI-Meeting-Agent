from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field


AGENT_WRITE_CONTROL_SCHEMA_VERSION = "agent-write-control-v1"

TrackedObjectType = Literal["Requirement", "AgentActionItem", "Risk"]
ConfirmationDecision = Literal["approved", "rejected", "needs_changes", "expired"]
ControlledWriteOperation = Literal["create", "update", "complete", "defer", "cancel"]
ControlledWriteCommandStatus = Literal["ready", "rejected", "duplicate", "blocked"]
WriteControlResultStatus = Literal["ready", "rejected", "duplicate"]

ALLOWED_CHANGE_FIELDS: dict[TrackedObjectType, set[str]] = {
    "Requirement": {"title", "description", "status", "priority", "owner", "due_date", "target_version"},
    "AgentActionItem": {"title", "description", "owner", "due_date", "status", "priority", "dependencies"},
    "Risk": {"title", "description", "category", "level", "impact", "probability", "mitigation", "owner", "due_date", "priority", "status"},
}
HIGH_RISK_ACTIONS = {"cancel", "complete"}


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_type: str = "unknown"
    source_meeting_id: str = ""
    source_segment_id: str | None = None
    source_text: str = ""
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentActionProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    proposal_id: str = ""
    proposal_type: str = "unknown"
    action_type: str | None = None
    target_object_type: str = ""
    target_object_id: str | None = None
    title: str = ""
    description: str = ""
    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: str = "unknown"
    requires_confirmation: bool = True
    status: str = "proposed"
    needs_confirmation: bool = True
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthoritativeStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_type: TrackedObjectType
    object_id: str
    object_version: str
    status: str = "unknown"
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "unknown"
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthoritativeStateProvider(Protocol):
    def get_state(self, *, object_type: TrackedObjectType, object_id: str) -> AuthoritativeStateSnapshot | None:
        """Return current authoritative state for one bounded object id."""


class AgentProposalConfirmation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmation_id: str
    proposal_id: str
    decision: ConfirmationDecision
    reviewer: str = ""
    reviewed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    comment: str = ""
    expected_object_version: str | None = None
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    audit_id: str
    proposal_id: str
    confirmation_id: str | None = None
    target_object_type: TrackedObjectType
    target_object_id: str
    operation: str
    reviewer: str = ""
    decision: str = ""
    result: WriteControlResultStatus
    reasons: list[str] = Field(default_factory=list)
    authoritative_source: str = "unknown"
    authoritative_version: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rollback_id: str
    target_object_type: TrackedObjectType
    target_object_id: str
    expected_version: str | None = None
    restore_changes: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlledWriteCommand(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command_id: str
    proposal_id: str
    target_object_type: TrackedObjectType
    target_object_id: str
    operation: ControlledWriteOperation
    expected_version: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    confirmation_id: str
    audit_context: dict[str, Any] = Field(default_factory=dict)
    status: ControlledWriteCommandStatus = "ready"
    rollback_plan: RollbackPlan | None = None


class WriteControlResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: WriteControlResultStatus
    command: ControlledWriteCommand | None = None
    audit_record: AuditRecord
    rollback_plan: RollbackPlan | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ControlledWritePlanner:
    def __init__(
        self,
        *,
        state_provider: AuthoritativeStateProvider,
        seen_idempotency_keys: set[str] | None = None,
    ) -> None:
        self.state_provider = state_provider
        self.seen_idempotency_keys = seen_idempotency_keys if seen_idempotency_keys is not None else set()

    def plan(
        self,
        *,
        proposal: AgentActionProposal,
        confirmation: AgentProposalConfirmation | None,
    ) -> WriteControlResult:
        target_type = _target_type(proposal)
        target_id = _target_id(proposal)
        operation = _operation_for(proposal)
        snapshot = self._read_authoritative_state(object_type=target_type, object_id=target_id, operation=operation)
        rejection_reasons = validate_write_request(
            proposal=proposal,
            confirmation=confirmation,
            snapshot=snapshot,
            operation=operation,
        )
        idempotency_key = build_idempotency_key(
            proposal=proposal,
            confirmation=confirmation,
            snapshot=snapshot,
            operation=operation,
        )
        if idempotency_key in self.seen_idempotency_keys:
            rejection_reasons.append("duplicate_command")

        if rejection_reasons:
            status: WriteControlResultStatus = "duplicate" if "duplicate_command" in rejection_reasons else "rejected"
            audit = build_audit_record(
                proposal=proposal,
                confirmation=confirmation,
                snapshot=snapshot,
                operation=operation,
                result=status,
                reasons=rejection_reasons,
            )
            return WriteControlResult(
                status=status,
                audit_record=audit,
                rejection_reasons=sorted(set(rejection_reasons)),
                metadata=_result_metadata(writes_performed=False),
            )

        rollback = build_rollback_plan(proposal=proposal, snapshot=snapshot, operation=operation)
        command = ControlledWriteCommand(
            command_id=stable_id("command", proposal.proposal_id, confirmation.confirmation_id, idempotency_key),
            proposal_id=proposal.proposal_id,
            target_object_type=target_type,
            target_object_id=target_id,
            operation=operation,
            expected_version=snapshot.object_version if snapshot else confirmation.expected_object_version,
            changes=normalize_command_changes(proposal.proposed_changes),
            idempotency_key=idempotency_key,
            confirmation_id=confirmation.confirmation_id,
            audit_context={
                "schema_version": AGENT_WRITE_CONTROL_SCHEMA_VERSION,
                "reviewer": confirmation.reviewer,
                "reviewed_at": confirmation.reviewed_at,
                "authoritative_state": snapshot.model_dump(mode="json") if snapshot else None,
                "proposal_reason": proposal.reason,
                "proposal_confidence": proposal.confidence,
                "writes_performed": False,
            },
            status="ready",
            rollback_plan=rollback,
        )
        self.seen_idempotency_keys.add(idempotency_key)
        audit = build_audit_record(
            proposal=proposal,
            confirmation=confirmation,
            snapshot=snapshot,
            operation=operation,
            result="ready",
            reasons=[],
            command_id=command.command_id,
        )
        return WriteControlResult(
            status="ready",
            command=command,
            audit_record=audit,
            rollback_plan=rollback,
            metadata=_result_metadata(writes_performed=False),
        )

    def _read_authoritative_state(
        self,
        *,
        object_type: TrackedObjectType,
        object_id: str,
        operation: ControlledWriteOperation,
    ) -> AuthoritativeStateSnapshot | None:
        if operation == "create" and not object_id:
            return None
        if not object_id:
            return None
        return self.state_provider.get_state(object_type=object_type, object_id=object_id)


def validate_write_request(
    *,
    proposal: AgentActionProposal,
    confirmation: AgentProposalConfirmation | None,
    snapshot: AuthoritativeStateSnapshot | None,
    operation: ControlledWriteOperation,
) -> list[str]:
    if confirmation is None:
        return ["missing_confirmation"]
    reasons: list[str] = []
    if confirmation.proposal_id != proposal.proposal_id:
        reasons.append("confirmation_proposal_mismatch")
    if confirmation.decision != "approved":
        reasons.append(f"confirmation_{confirmation.decision}")
    if _confirmation_expired(confirmation):
        reasons.append("confirmation_expired")
    if not confirmation.reviewer:
        reasons.append("missing_reviewer")
    if not _has_permission(confirmation.permissions, proposal=proposal, operation=operation):
        reasons.append("permission_denied")
    if operation != "create" and snapshot is None:
        reasons.append("target_not_found")
    if snapshot is not None and confirmation.expected_object_version != snapshot.object_version:
        reasons.append("version_conflict")
    if invalid := non_whitelisted_fields(proposal):
        reasons.append("field_not_whitelisted:" + ",".join(invalid))
    if is_high_risk_operation(proposal) and not proposal.requires_confirmation:
        reasons.append("high_risk_requires_confirmation")
    if not _has_evidence(proposal):
        reasons.append("missing_evidence")
    if not proposal.reason or not proposal.metadata:
        reasons.append("missing_audit_context")
    if not normalize_command_changes(proposal.proposed_changes):
        reasons.append("missing_changes")
    return sorted(set(reasons))


def build_audit_record(
    *,
    proposal: AgentActionProposal,
    confirmation: AgentProposalConfirmation | None,
    snapshot: AuthoritativeStateSnapshot | None,
    operation: ControlledWriteOperation,
    result: WriteControlResultStatus,
    reasons: list[str],
    command_id: str | None = None,
) -> AuditRecord:
    return AuditRecord(
        audit_id=stable_id("audit", proposal.proposal_id, confirmation.confirmation_id if confirmation else "", result),
        proposal_id=proposal.proposal_id,
        confirmation_id=confirmation.confirmation_id if confirmation else None,
        target_object_type=_target_type(proposal),
        target_object_id=_target_id(proposal),
        operation=operation,
        reviewer=confirmation.reviewer if confirmation else "",
        decision=confirmation.decision if confirmation else "missing",
        result=result,
        reasons=sorted(set(reasons)),
        authoritative_source=snapshot.source if snapshot else "none",
        authoritative_version=snapshot.object_version if snapshot else None,
        metadata={
            "schema_version": AGENT_WRITE_CONTROL_SCHEMA_VERSION,
            "command_id": command_id,
            "proposal_status": proposal.status,
            "proposal_risk_level": proposal.risk_level,
            "writes_performed": False,
        },
    )


def build_rollback_plan(
    *,
    proposal: AgentActionProposal,
    snapshot: AuthoritativeStateSnapshot | None,
    operation: ControlledWriteOperation,
) -> RollbackPlan:
    target_type = _target_type(proposal)
    target_id = _target_id(proposal)
    restore: dict[str, Any] = {}
    if snapshot is not None:
        for field in normalize_command_changes(proposal.proposed_changes):
            restore[field] = snapshot.data.get(field)
    return RollbackPlan(
        rollback_id=stable_id("rollback", proposal.proposal_id, target_id, snapshot.object_version if snapshot else "new"),
        target_object_type=target_type,
        target_object_id=target_id,
        expected_version=snapshot.object_version if snapshot else None,
        restore_changes=restore,
        source_snapshot=snapshot.model_dump(mode="json") if snapshot else {},
        metadata={
            "schema_version": AGENT_WRITE_CONTROL_SCHEMA_VERSION,
            "rollback_operation": "delete_created_object" if operation == "create" else "restore_previous_values",
            "writes_performed": False,
        },
    )


def non_whitelisted_fields(proposal: AgentActionProposal) -> list[str]:
    object_type = _target_type(proposal)
    allowed = ALLOWED_CHANGE_FIELDS[object_type]
    return sorted(field for field in normalize_command_changes(proposal.proposed_changes) if field not in allowed)


def normalize_command_changes(changes: dict[str, Any]) -> dict[str, Any]:
    if "create" in changes and isinstance(changes["create"], dict):
        return dict(changes["create"])
    normalized: dict[str, Any] = {}
    for field, value in changes.items():
        if isinstance(value, dict) and "to" in value:
            normalized[field] = value.get("to")
        else:
            normalized[field] = value
    return normalized


def build_idempotency_key(
    *,
    proposal: AgentActionProposal,
    confirmation: AgentProposalConfirmation | None,
    snapshot: AuthoritativeStateSnapshot | None,
    operation: ControlledWriteOperation,
) -> str:
    payload = {
        "proposal_id": proposal.proposal_id,
        "target_object_type": proposal.target_object_type,
        "target_object_id": _target_id(proposal),
        "operation": operation,
        "expected_version": snapshot.object_version if snapshot else (confirmation.expected_object_version if confirmation else None),
    }
    return stable_id("idempotency", json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def is_high_risk_operation(proposal: AgentActionProposal) -> bool:
    return (
        str(proposal.risk_level) in {"high", "critical"}
        or str(proposal.action_type or proposal.proposal_type) in HIGH_RISK_ACTIONS
        or "high_risk" in set(proposal.metadata.get("confirmation_reasons") or [])
        or "close_high_risk" in set(proposal.metadata.get("confirmation_reasons") or [])
    )


def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-{uuid5(NAMESPACE_URL, '|'.join(str(part or '') for part in parts))}"


def _target_type(proposal: AgentActionProposal) -> TrackedObjectType:
    value = proposal.target_object_type
    if value not in ALLOWED_CHANGE_FIELDS:
        raise ValueError(f"Unsupported target object type: {value}")
    return value  # type: ignore[return-value]


def _target_id(proposal: AgentActionProposal) -> str:
    if proposal.target_object_id:
        return proposal.target_object_id
    create_payload = proposal.proposed_changes.get("create")
    if isinstance(create_payload, dict):
        for field in ("requirement_id", "action_item_id", "risk_id"):
            if create_payload.get(field):
                return str(create_payload[field])
    return ""


def _operation_for(proposal: AgentActionProposal) -> ControlledWriteOperation:
    action = str(proposal.action_type or proposal.proposal_type or "update")
    if action in {"new", "create"}:
        return "create"
    if action in {"complete", "defer", "cancel"}:
        return action  # type: ignore[return-value]
    return "update"


def _has_permission(
    permissions: list[str],
    *,
    proposal: AgentActionProposal,
    operation: ControlledWriteOperation,
) -> bool:
    target_type = _target_type(proposal)
    accepted = {"*", "agent_write", f"agent_write:{target_type}", f"{operation}:{target_type}", f"{operation}:*"}
    return bool(set(permissions) & accepted)


def _confirmation_expired(confirmation: AgentProposalConfirmation) -> bool:
    if confirmation.decision == "expired":
        return True
    expires_at = confirmation.metadata.get("expires_at")
    if not expires_at:
        return False
    try:
        return _parse_datetime(str(expires_at)) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _has_evidence(proposal: AgentActionProposal) -> bool:
    return any(isinstance(item, EvidenceRef) and str(item.source_text or "").strip() for item in proposal.evidence)


def _result_metadata(*, writes_performed: bool) -> dict[str, Any]:
    return {
        "schema_version": AGENT_WRITE_CONTROL_SCHEMA_VERSION,
        "writes_performed": writes_performed,
        "external_calls_performed": False,
    }


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
