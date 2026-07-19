from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DimensionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str
    topic_id: str
    source_event_ids: list[str] = Field(default_factory=list)
    source_texts: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class AgendaItem(DimensionItem):
    pass


class SummaryItem(DimensionItem):
    pass


class DecisionItem(DimensionItem):
    status: str | None = None


class ActionItem(DimensionItem):
    owner: str | None = None
    deadline: str | None = None
    priority: str | None = None
    status: str | None = None


class OpenIssueItem(DimensionItem):
    status: str | None = None


class RiskItem(DimensionItem):
    condition: str | None = None
    impact: str | None = None
    mitigation: str | None = None
    status: str | None = None


class SixDimensionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meeting_id: str
    meeting_agenda: list[AgendaItem] = Field(default_factory=list)
    meeting_summary: list[SummaryItem] = Field(default_factory=list)
    key_conclusions: list[DecisionItem] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    unresolved_issues: list[OpenIssueItem] = Field(default_factory=list)
    risks_and_focus: list[RiskItem] = Field(default_factory=list)
