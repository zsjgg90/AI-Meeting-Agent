from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WorkflowType = Literal["project_delivery", "issue_resolution", "meeting_follow_up"]
ProjectDeliveryState = Literal[
    "requirements_pending",
    "requirements_confirmed",
    "development_in_progress",
    "testing_in_progress",
    "verification_failed",
    "ready_for_release",
    "released",
    "blocked",
]
IssueResolutionState = Literal[
    "reported",
    "investigating",
    "root_cause_found",
    "fix_in_progress",
    "resolved",
    "verified",
]
MeetingFollowUpState = Literal[
    "action_created",
    "owner_confirmed",
    "pending",
    "in_progress",
    "completed_candidate",
    "needs_review",
]
WorkflowObservedState = ProjectDeliveryState | IssueResolutionState | MeetingFollowUpState
WorkflowTransitionType = Literal[
    "no_previous_state",
    "unchanged",
    "forward",
    "backward",
    "blocked",
    "failed",
    "requires_confirmation",
    "unknown",
]
WorkflowEvidenceSupportLevel = Literal["supports", "weakens", "conflicts", "context_only"]
WorkflowEvidenceStatus = Literal[
    "confirmed",
    "active",
    "candidate",
    "needs_review",
    "shadow_only",
    "conflicted",
    "expired",
    "unknown",
]


class WorkflowStateEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    meeting_id: str | None = None
    supports: list[str] = Field(default_factory=list)
    support_level: WorkflowEvidenceSupportLevel
    evidence_status: WorkflowEvidenceStatus = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_supported_parts(self) -> "WorkflowStateEvidenceRef":
        if not self.supports:
            raise ValueError("workflow state evidence ref requires supports")
        return self


class WorkflowStateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_state: WorkflowObservedState | None = None
    to_state: WorkflowObservedState
    transition_type: WorkflowTransitionType
    reason: str = Field(min_length=1)


class WorkflowStateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    workflow_type: WorkflowType
    observed_state: WorkflowObservedState
    previous_state: WorkflowObservedState | None = None
    transition: WorkflowStateTransition
    evidence_refs: list[WorkflowStateEvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool

    @model_validator(mode="after")
    def enforce_evidence_first_and_confirmation(self) -> "WorkflowStateObservation":
        if not self.evidence_refs:
            raise ValueError("workflow state observation requires evidence")
        if not any(item.support_level == "supports" for item in self.evidence_refs):
            raise ValueError("workflow state observation requires supporting evidence")
        has_conflict = any(
            item.support_level == "conflicts" or item.evidence_status == "conflicted"
            for item in self.evidence_refs
        )
        if has_conflict and not self.requires_confirmation:
            raise ValueError("conflicting workflow state evidence requires confirmation")
        if self.transition.to_state != self.observed_state:
            raise ValueError("workflow state transition target must match observed_state")
        if self.transition.from_state != self.previous_state:
            raise ValueError("workflow state transition source must match previous_state")
        return self


WORKFLOW_STATES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "project_delivery": (
        "requirements_pending",
        "requirements_confirmed",
        "development_in_progress",
        "testing_in_progress",
        "verification_failed",
        "ready_for_release",
        "released",
        "blocked",
    ),
    "issue_resolution": (
        "reported",
        "investigating",
        "root_cause_found",
        "fix_in_progress",
        "resolved",
        "verified",
    ),
    "meeting_follow_up": (
        "action_created",
        "owner_confirmed",
        "pending",
        "in_progress",
        "completed_candidate",
        "needs_review",
    ),
}


__all__ = [
    "IssueResolutionState",
    "MeetingFollowUpState",
    "ProjectDeliveryState",
    "WORKFLOW_STATES_BY_TYPE",
    "WorkflowObservedState",
    "WorkflowStateEvidenceRef",
    "WorkflowStateObservation",
    "WorkflowStateTransition",
    "WorkflowTransitionType",
    "WorkflowType",
]
