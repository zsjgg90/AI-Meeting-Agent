from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent_contract import EvidenceRef, MeetingType


MEETING_SCENARIO_POLICY_SCHEMA_VERSION = "meeting-scenario-policy-v1"

ContextType = Literal[
    "previous_meetings",
    "previous_same_type_meeting",
    "project_state",
    "open_action_items",
    "active_risks",
    "open_issues",
    "requirements",
    "decisions",
    "dependencies",
    "milestones",
    "customer_requests",
    "project_knowledge",
]

FocusEntityType = Literal[
    "requirement",
    "decision",
    "action_item",
    "issue",
    "risk",
    "dependency",
    "milestone",
    "customer_request",
    "project_state",
]

ScenarioActionType = Literal[
    "create_action_item",
    "update_action_item",
    "complete_action_item",
    "defer_action_item",
    "create_requirement",
    "update_requirement_status",
    "create_risk",
    "update_risk_level",
    "create_issue",
    "resolve_issue",
    "create_dependency",
    "create_decision_record",
    "create_milestone",
    "update_milestone",
    "generate_next_meeting_agenda",
    "update_project_health",
]

ClassificationSource = Literal[
    "manual",
    "template",
    "rule",
    "model",
    "fallback",
]


class MeetingScenarioPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meeting_type: MeetingType
    display_name: str
    description: str
    required_context: tuple[ContextType, ...] = Field(default_factory=tuple)
    optional_context: tuple[ContextType, ...] = Field(default_factory=tuple)
    focus_entities: tuple[FocusEntityType, ...] = Field(default_factory=tuple)
    validation_rules: tuple[str, ...] = Field(default_factory=tuple)
    allowed_actions: tuple[ScenarioActionType, ...] = Field(default_factory=tuple)
    confirmation_required_actions: tuple[ScenarioActionType, ...] = Field(default_factory=tuple)
    classification_hints: tuple[str, ...] = Field(default_factory=tuple)
    needs_review: bool = False
    schema_version: str = MEETING_SCENARIO_POLICY_SCHEMA_VERSION


class MeetingClassificationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meeting_type: MeetingType = "unknown"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    source: ClassificationSource = "fallback"
    needs_review: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)


def create_policy(
    *,
    meeting_type: MeetingType,
    display_name: str,
    description: str,
    required_context: tuple[ContextType, ...] = (),
    optional_context: tuple[ContextType, ...] = (),
    focus_entities: tuple[FocusEntityType, ...],
    validation_rules: tuple[str, ...],
    allowed_actions: tuple[ScenarioActionType, ...],
    confirmation_required_actions: tuple[ScenarioActionType, ...] = (),
    classification_hints: tuple[str, ...] = (),
    needs_review: bool = False,
) -> MeetingScenarioPolicy:
    return MeetingScenarioPolicy(
        meeting_type=meeting_type,
        display_name=display_name,
        description=description,
        required_context=required_context,
        optional_context=optional_context,
        focus_entities=focus_entities,
        validation_rules=validation_rules,
        allowed_actions=allowed_actions,
        confirmation_required_actions=confirmation_required_actions,
        classification_hints=classification_hints,
        needs_review=needs_review,
    )


__all__ = [
    "MEETING_SCENARIO_POLICY_SCHEMA_VERSION",
    "ContextType",
    "FocusEntityType",
    "ScenarioActionType",
    "ClassificationSource",
    "MeetingScenarioPolicy",
    "MeetingClassificationResult",
    "create_policy",
]
