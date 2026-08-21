from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.workflow_state import WorkflowStateEvidenceRef


WorkflowRecommendationType = Literal[
    "request_confirmation",
    "refresh_evidence",
    "review_dependency",
    "manual_review",
    "no_action",
]


class WorkflowRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    recommendation_type: WorkflowRecommendationType
    reason: str = Field(min_length=1)
    evidence_refs: list[WorkflowStateEvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool

    @model_validator(mode="after")
    def enforce_evidence_first_and_observation_only(self) -> "WorkflowRecommendation":
        if not self.evidence_refs:
            raise ValueError("workflow recommendation requires evidence")
        if not any(item.support_level == "supports" for item in self.evidence_refs):
            raise ValueError("workflow recommendation requires supporting evidence")
        has_conflict = any(
            item.support_level == "conflicts" or item.evidence_status == "conflicted"
            for item in self.evidence_refs
        )
        if has_conflict and not self.requires_confirmation:
            raise ValueError("conflicting workflow recommendation evidence requires confirmation")
        if self.recommendation_type == "request_confirmation" and not self.requires_confirmation:
            raise ValueError("request_confirmation recommendation requires confirmation")
        if self.recommendation_type == "no_action" and self.requires_confirmation:
            raise ValueError("no_action recommendation must not require confirmation")
        return self


__all__ = [
    "WorkflowRecommendation",
    "WorkflowRecommendationType",
]
