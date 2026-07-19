from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AGENT_CONTRACT_SCHEMA_VERSION = "agent-contract-v1"

MeetingType = Literal[
    "requirement_review",
    "project_weekly",
    "technical_review",
    "version_planning",
    "cross_department",
    "project_retrospective",
    "management_decision",
    "customer_requirement",
    "unknown",
]

EvidenceSourceType = Literal[
    "transcript",
    "meeting_history",
    "project_knowledge",
    "manual",
    "unknown",
]

RequirementStatus = Literal[
    "proposed",
    "under_review",
    "confirmed",
    "deferred",
    "cancelled",
    "implemented",
    "unknown",
]

DecisionStatus = Literal[
    "proposed",
    "confirmed",
    "deferred",
    "cancelled",
    "superseded",
    "unknown",
]

ActionItemStatus = Literal[
    "open",
    "in_progress",
    "blocked",
    "completed",
    "deferred",
    "cancelled",
    "unknown",
]

RiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
RiskStatus = Literal["active", "mitigated", "accepted", "closed", "unknown"]
IssueStatus = Literal["open", "in_progress", "resolved", "deferred", "cancelled", "unknown"]
DependencyType = Literal["blocks", "blocked_by", "relates_to", "depends_on", "unknown"]
MilestoneStatus = Literal["planned", "in_progress", "completed", "delayed", "cancelled", "unknown"]
CustomerRequestStatus = Literal[
    "new",
    "under_review",
    "accepted",
    "rejected",
    "deferred",
    "implemented",
    "unknown",
]
ProjectHealth = Literal["normal", "at_risk", "blocked", "critical", "unknown"]
AgentActionProposalType = Literal[
    "create",
    "update",
    "complete",
    "defer",
    "cancel",
    "notify",
    "unknown",
]
AgentActionProposalStatus = Literal["proposed", "confirmed", "rejected", "executed", "cancelled"]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_type: EvidenceSourceType = "unknown"
    source_meeting_id: str = ""
    source_segment_id: str | None = None
    source_text: str = ""
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Requirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirement_id: str = ""
    title: str = ""
    description: str = ""
    status: RequirementStatus = "proposed"
    priority: str | None = None
    owner: str | None = None
    target_version: str | None = None
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_review: bool = False


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision_id: str = ""
    topic: str = ""
    decision: str = ""
    rationale: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    status: DecisionStatus = "confirmed"
    decision_maker: str | None = None
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_confirmation: bool = False


class AgentActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_item_id: str = ""
    title: str = ""
    description: str = ""
    owner: str | None = None
    due_date: str | None = None
    status: ActionItemStatus = "open"
    priority: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_review: bool = False


class Issue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issue_id: str = ""
    title: str = ""
    description: str = ""
    status: IssueStatus = "open"
    owner: str | None = None
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_review: bool = False


class Risk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_id: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    level: RiskLevel = "medium"
    impact: str | None = None
    probability: str | None = None
    mitigation: list[str] = Field(default_factory=list)
    owner: str | None = None
    status: RiskStatus = "active"
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Dependency(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dependency_id: str = ""
    upstream_object_id: str = ""
    downstream_object_id: str = ""
    dependency_type: DependencyType = "blocks"
    description: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Milestone(BaseModel):
    model_config = ConfigDict(extra="ignore")

    milestone_id: str = ""
    title: str = ""
    target_date: str | None = None
    status: MilestoneStatus = "planned"
    owner: str | None = None
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class CustomerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_request_id: str = ""
    customer: str | None = None
    title: str = ""
    description: str = ""
    status: CustomerRequestStatus = "new"
    priority: str | None = None
    owner: str | None = None
    source_meeting_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    needs_review: bool = False


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str = ""
    stage: str = ""
    health: ProjectHealth = "normal"
    open_action_items: int = 0
    blocked_action_items: int = 0
    active_risks: int = 0
    open_issues: int = 0
    next_milestone: Milestone | None = None
    last_meeting_id: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentActionProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    proposal_id: str = ""
    proposal_type: AgentActionProposalType = "unknown"
    target_object_type: str = ""
    target_object_id: str | None = None
    title: str = ""
    description: str = ""
    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: AgentActionProposalStatus = "proposed"
    needs_confirmation: bool = True


class AgentContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = ""
    meeting_id: str = ""
    project_id: str = ""
    user_id: str = ""
    meeting_type: MeetingType = "unknown"
    objective: str = ""
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    meeting_analysis: dict[str, Any] = Field(default_factory=dict)
    project_state: ProjectState | dict[str, Any] = Field(default_factory=ProjectState)
    meeting_history: list[dict[str, Any]] = Field(default_factory=list)
    open_action_items: list[AgentActionItem] = Field(default_factory=list)
    active_risks: list[Risk] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    action_proposals: list[AgentActionProposal] = Field(default_factory=list)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_schema_version_metadata(self) -> "AgentContext":
        metadata = dict(self.runtime_metadata)
        metadata["schema_version"] = AGENT_CONTRACT_SCHEMA_VERSION
        self.runtime_metadata = metadata
        return self


__all__ = [
    "AGENT_CONTRACT_SCHEMA_VERSION",
    "MeetingType",
    "EvidenceSourceType",
    "RequirementStatus",
    "DecisionStatus",
    "ActionItemStatus",
    "RiskLevel",
    "RiskStatus",
    "IssueStatus",
    "DependencyType",
    "MilestoneStatus",
    "CustomerRequestStatus",
    "ProjectHealth",
    "AgentActionProposalType",
    "AgentActionProposalStatus",
    "EvidenceRef",
    "Requirement",
    "Decision",
    "AgentActionItem",
    "Issue",
    "Risk",
    "Dependency",
    "Milestone",
    "CustomerRequest",
    "ProjectState",
    "AgentActionProposal",
    "AgentContext",
]
