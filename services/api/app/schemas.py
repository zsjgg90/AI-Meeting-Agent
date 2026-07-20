from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MeetingCreate(BaseModel):
    title: str = Field(default="Untitled meeting", max_length=255)
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)


class MeetingUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)


class MeetingBulkDelete(BaseModel):
    meeting_ids: list[str] = Field(min_length=1)


class MeetingBulkDeleteResult(BaseModel):
    deleted_count: int


class FeedbackCreate(BaseModel):
    feedback_type: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    contact: str | None = Field(default=None, max_length=255)
    image_urls: list[str] = []


class FeedbackRead(BaseModel):
    id: str
    feedback_type: str
    description: str
    contact: str | None
    image_urls: list[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AudioFileRead(BaseModel):
    id: str
    filename: str
    content_type: str | None
    path: str
    file_size_bytes: int
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TranscriptSegmentRead(BaseModel):
    id: str
    audio_file_id: str | None
    segment_index: int
    start_time: float
    end_time: float
    text: str
    speaker_label: str | None
    speaker_name: str | None = None
    speaker_gender: str | None = None
    semantic_label: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def speaker(self) -> str | None:
        return self.speaker_label


class TranscriptionTaskRead(BaseModel):
    id: str
    meeting_id: str
    status: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MeetingOutputRead(BaseModel):
    raw_transcript: str
    speaker_segments: list[dict[str, Any]]
    summary: str
    action_items: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActionItemRead(BaseModel):
    id: str
    task: str
    owner: str | None
    owner_name: str | None = None
    due_date: str | None
    deadline: str | None = None
    priority: str | None = None
    status: str
    source: str | None
    source_text: str | None = None
    source_segment_id: str | None = None
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListItem(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    task: str
    owner: str | None = None
    owner_name: str | None = None
    due_date: str | None = None
    deadline: str | None = None
    priority: str | None = None
    status: str
    source: str | None = None
    source_text: str | None = None
    source_segment_id: str | None = None
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class TaskListRead(BaseModel):
    items: list[TaskListItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class MeetingSummaryRead(BaseModel):
    id: str
    overview: str
    agenda: list[dict[str, Any]] = []
    topics: list[dict[str, Any]]
    speaker_summaries: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    open_questions: list[dict[str, Any]]
    next_steps: list[dict[str, Any]] = []
    meeting_agenda: list[dict[str, Any]] = []
    meeting_summary: str | None = None
    key_conclusions: list[dict[str, Any]] = []
    unresolved_issues: list[dict[str, Any]] = []
    risks_and_focus: list[dict[str, Any]] = []
    model_name: str | None = None
    prompt_version: str | None = None
    rag_chunk_ids: list[str] = []
    rag_dataset_version: str | None = None
    rag_chunk_schema_version: str | None = None
    rag_collection_name: str | None = None
    rag_embedding_model: str | None = None
    confidence_score: float | None = None
    action_items: list[ActionItemRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpeakerMappingRead(BaseModel):
    id: str
    speaker_label: str
    display_name: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpeakerMappingUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    note: str | None = Field(default=None, max_length=1000)


class MeetingChunkRead(BaseModel):
    id: str
    speaker: str | None
    content: str
    metadata_: dict[str, Any] = Field(validation_alias="metadata_", serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True)


class MeetingRead(BaseModel):
    id: str
    title: str
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = None
    created_at: datetime
    updated_at: datetime
    audio_files: list[AudioFileRead] = []
    transcript_segments: list[TranscriptSegmentRead] = []
    summary: MeetingSummaryRead | None = None
    action_items: list[ActionItemRead] = []
    speaker_mappings: list[SpeakerMappingRead] = []
    tasks: list[TranscriptionTaskRead] = []
    output: MeetingOutputRead | None = None
    chunks: list[MeetingChunkRead] = []

    model_config = ConfigDict(from_attributes=True)


class MeetingListItem(BaseModel):
    id: str
    title: str
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeetingCreated(BaseModel):
    id: str
    title: str
    status: str


class AudioUploaded(BaseModel):
    audio_file_id: str
    meeting_id: str
    filename: str
    path: str
    file_size_bytes: int


class AudioChunkUploaded(AudioUploaded):
    start_offset_seconds: float
    transcript_segment_count: int


class ProcessStarted(BaseModel):
    task_id: str
    meeting_id: str
    status: str


class TranscriptRead(BaseModel):
    meeting_id: str
    status: str
    raw_transcript: str | None
    segments: list[TranscriptSegmentRead]
    speaker_segments: list[dict[str, Any]]


class SummaryRead(BaseModel):
    meeting_id: str
    status: str
    overview: str | None = None
    agenda: list[dict[str, Any]] = []
    topics: list[dict[str, Any]] = []
    speaker_summaries: list[dict[str, Any]] = []
    summary: str | None
    action_items: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    risks: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    next_steps: list[dict[str, Any]] = []
    meeting_agenda: list[dict[str, Any]] = []
    meeting_summary: str = ""
    key_conclusions: list[dict[str, Any]] = []
    unresolved_issues: list[dict[str, Any]] = []
    risks_and_focus: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class AgentActionProposalCreate(BaseModel):
    proposal_id: str = Field(default="", max_length=64)
    action_type: str = Field(min_length=1, max_length=32)
    target_object_type: str = Field(min_length=1, max_length=64)
    target_object_id: str | None = Field(default=None, max_length=128)
    title: str = Field(default="", max_length=255)
    description: str = ""
    proposed_changes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: str = Field(default="unknown", max_length=32)
    requires_confirmation: bool = True
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentActionProposalRead(BaseModel):
    id: str
    action_type: str
    target_object_type: str
    target_object_id: str | None = None
    expected_object_version: str | None = None
    title: str
    description: str
    proposed_changes: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: float | None = None
    risk_level: str
    requires_confirmation: bool
    status: str
    reason: str
    metadata_: dict[str, Any] = Field(validation_alias="metadata_", serialization_alias="metadata")
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentProposalConfirmationRequest(BaseModel):
    comment: str = Field(default="", max_length=1000)


class AgentProposalConfirmationRead(BaseModel):
    id: str
    proposal_id: str
    decision: str
    reviewer: str
    reviewed_at: datetime
    comment: str
    expected_object_version: str | None = None
    permissions: list[str]
    metadata_: dict[str, Any] = Field(validation_alias="metadata_", serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True)


class ControlledWriteCommandRead(BaseModel):
    id: str
    proposal_id: str
    target_object_type: str
    target_object_id: str
    operation: str
    expected_version: str | None = None
    changes: dict[str, Any]
    idempotency_key: str
    confirmation_id: str
    audit_context: dict[str, Any]
    rollback_plan: dict[str, Any]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentAuditRecordRead(BaseModel):
    id: str
    proposal_id: str
    confirmation_id: str | None = None
    command_id: str | None = None
    target_object_type: str
    target_object_id: str
    operation: str
    reviewer: str
    decision: str
    result: str
    reasons: list[str]
    authoritative_source: str
    authoritative_version: str | None = None
    audit_context: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentProposalDecisionRead(BaseModel):
    proposal: AgentActionProposalRead
    confirmation: AgentProposalConfirmationRead
    command: ControlledWriteCommandRead | None = None
    audit: AgentAuditRecordRead | None = None
    status: str
    rejection_reasons: list[str] = Field(default_factory=list)
