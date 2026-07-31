from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


SemanticLabel = Literal[
    "agenda",
    "background",
    "discussion",
    "decision",
    "action",
    "unresolved_issue",
    "risk",
    "question",
    "other",
]


class CleanTranscriptSegment(BaseModel):
    id: str
    speaker_label: str | None = None
    speaker_name: str | None = None
    start_time: float
    end_time: float
    text: str


class SemanticSegment(BaseModel):
    source_segment_id: str
    semantic_label: SemanticLabel
    confidence: float = Field(
        default=0.5,
        ge=0,
        le=1,
    )


class TopicChunk(BaseModel):
    title: str
    summary: str
    start_time: float
    end_time: float
    related_segment_ids: list[str]
    speakers: list[str]


class MeetingAgendaItem(BaseModel):
    item: str
    order: int
    source_segment_ids: list[str] = []


class KeyConclusion(BaseModel):
    conclusion: str
    source_text: str
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
    )


class MeetingActionItem(BaseModel):
    owner_name: str | None = None
    task: str
    deadline: str | None = None
    priority: Literal[
        "low",
        "medium",
        "high",
    ] = "medium"
    status: Literal[
        "open",
        "in_progress",
        "done",
    ] = "open"
    source_text: str
    source_segment_id: str | None = None
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
    )


class UnresolvedIssue(BaseModel):
    issue: str
    reason: str = ""
    blocker: str = ""
    source_text: str
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
    )


class RiskAndFocus(BaseModel):
    risk: str
    impact: str = ""
    focus_area: str = ""
    mitigation: str = ""
    source_text: str
    confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
    )


class MeetingAnalysisMetadata(BaseModel):
    schema_version: str = "meeting-analysis-v1"
    model_name: str = ""
    prompt_version: str | None = None

    rag_chunk_ids: list[str] = []
    rag_dataset_version: str | None = None
    rag_chunk_schema_version: str | None = None
    rag_collection_name: str | None = None
    rag_embedding_model: str | None = None

    rag_retrieval_strategy: str | None = None
    rag_retrieval_buckets: dict[
        str,
        list[str],
    ] = {}
    rag_routed_meeting_type: str | None = None
    rag_routed_scenario: str | None = None
    rag_fallback_reason: str | None = None

    result_source: str | None = None

    confidence_score: float = Field(
        default=0.0,
        ge=0,
        le=1,
    )

    generated_at: str = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )


MeetingType = Literal[
    "project_weekly",
    "progress_sync",
    "requirement_review",
    "solution_review",
    "project_retrospective",
    "risk_review",
    "release_review",
    "customer_communication",
    "training",
    "interview",
    "one_on_one",
    "other",
]


class MeetingAnalysisSchema(BaseModel):
    meeting_title: str = ""
    meeting_type: MeetingType | str = "other"

    meeting_type_confidence: float = Field(
        default=0.0,
        ge=0,
        le=1,
    )

    meeting_title_candidate: str = ""
    title_basis: list[str] = []

    meeting_agenda: list[
        MeetingAgendaItem
    ] = []

    meeting_summary: str = ""

    key_conclusions: list[
        KeyConclusion
    ] = []

    action_items: list[
        MeetingActionItem
    ] = []

    unresolved_issues: list[
        UnresolvedIssue
    ] = []

    risks_and_focus: list[
        RiskAndFocus
    ] = []

    topics: list[
        TopicChunk
    ] = []

    metadata: MeetingAnalysisMetadata = Field(
        default_factory=MeetingAnalysisMetadata
    )
