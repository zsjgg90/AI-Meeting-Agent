from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MeetingCreate(BaseModel):
    title: str = Field(default="Untitled meeting", max_length=255)
    title_source: str | None = Field(default=None, max_length=32)
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=255)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
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


class TaskAttachmentRead(BaseModel):
    id: str
    task_id: str
    filename: str
    content_type: str | None = None
    file_size_bytes: int
    download_url: str
    url: str
    uploaded_at: datetime


class TaskListItem(BaseModel):
    id: str
    meeting_id: str
    meeting_title: str
    task: str
    owner: str | None = None
    owner_name: str | None = None
    description: str | None = None
    due_date: str | None = None
    deadline: str | None = None
    priority: str | None = None
    reminder_offset_minutes: int | None = None
    reminder_channel: str | None = None
    status: str
    source: str | None = None
    source_text: str | None = None
    source_segment_id: str | None = None
    confidence: float | None = None
    attachments: list[TaskAttachmentRead] = []
    created_at: datetime
    updated_at: datetime


class TaskListRead(BaseModel):
    items: list[TaskListItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class TaskStatusUpdate(BaseModel):
    status: str


class TaskUpdate(BaseModel):
    task: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=5000)
    owner: str | None = Field(default=None, max_length=255)
    due_date: str | None = Field(default=None, max_length=64)
    priority: str | None = Field(default=None, max_length=32)
    reminder_offset_minutes: int | None = None
    reminder_channel: str | None = Field(default=None, max_length=32)




class KnowledgeOverviewRead(BaseModel):
    meeting_count: int
    decision_count: int
    unresolved_issue_count: int
    risk_count: int
    all_count: int
    sync_status: dict[str, int] = Field(default_factory=dict)


class KnowledgeMeetingItemRead(BaseModel):
    meeting_id: str
    title: str
    meeting_type: str | None = None
    meeting_time: datetime | None = None
    duration: float | None = None
    summary_status: str
    conclusion_count: int
    action_count: int
    unresolved_issue_count: int
    risk_count: int


class KnowledgeItemRead(BaseModel):
    id: str
    content_type: str
    title: str
    content: str
    meeting_id: str
    meeting_title: str
    meeting_date: datetime | None = None
    evidence_text: str | None = None
    source_segment_id: str | None = None
    speaker_label: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    highlight: str | None = None


class KnowledgeListRead(BaseModel):
    items: list[KnowledgeItemRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeMeetingListRead(BaseModel):
    items: list[KnowledgeMeetingItemRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeSyncRead(BaseModel):
    meeting_id: str
    status: str
    source_version: str
    item_count: int
    sync_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    title_source: str = "fallback"
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
    title_source: str = "fallback"
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
    title_source: str = "fallback"
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


class AgentLoginRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)


class AgentLoginRead(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    user_id: str
    display_name: str
    tenant_id: str
    project_scope: list[str]
    permissions: list[str]


class AgentSessionRead(BaseModel):
    user_id: str
    display_name: str
    tenant_id: str
    project_scope: list[str]
    permissions: list[str]
    authentication_source: str


class AgentLogoutRead(BaseModel):
    status: str
    revoked: bool = False


class AgentProposalGenerationDiagnosticRead(BaseModel):
    action_item_id: str
    task: str
    matched_object_id: str | None = None
    match_reason: str = ""
    confidence: float = 0.0
    field_changes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    generated: bool = False
    proposal_id: str | None = None
    skip_reason: str | None = None


class AgentProposalGenerationResponse(BaseModel):
    meeting_id: str
    diagnostics: list[AgentProposalGenerationDiagnosticRead]
    generated_count: int


class AgentProposalConfirmationRequest(BaseModel):
    comment: str = Field(default="", max_length=1000)


class AgentCommandExecutionRequest(BaseModel):
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


class AgentCommandDryRunRead(BaseModel):
    command: ControlledWriteCommandRead
    audit: AgentAuditRecordRead
    status: str
    rejection_reasons: list[str] = Field(default_factory=list)
    authoritative_state: dict[str, Any] | None = None
    expected_changes: dict[str, Any] = Field(default_factory=dict)
    rollback_preview: dict[str, Any] = Field(default_factory=dict)
    writes_performed: bool = False


class AgentRollbackDryRunRead(BaseModel):
    command: ControlledWriteCommandRead
    audit: AgentAuditRecordRead
    status: str
    rejection_reasons: list[str] = Field(default_factory=list)
    rollback_command: dict[str, Any] = Field(default_factory=dict)
    rollback_preview: dict[str, Any] = Field(default_factory=dict)
    authoritative_state: dict[str, Any] | None = None
    writes_performed: bool = False


class AgentCommandExecutionRead(BaseModel):
    command: ControlledWriteCommandRead
    audit: AgentAuditRecordRead
    status: str
    rejection_reasons: list[str] = Field(default_factory=list)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    writes_performed: bool = True


class AgentRollbackExecutionRead(BaseModel):
    command: ControlledWriteCommandRead
    audit: AgentAuditRecordRead
    status: str
    rejection_reasons: list[str] = Field(default_factory=list)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    writes_performed: bool = True


class AgentAuditSearchRead(BaseModel):
    items: list[AgentAuditRecordRead]
    total: int
    limit: int
    offset: int
    has_more: bool


class AgentMetricsRead(BaseModel):
    totals: dict[str, int]
    execution_latency_ms: dict[str, float | None]
    by_tenant: dict[str, int]
    by_project: dict[str, int]
    by_user: dict[str, int]


class AgentCircuitStatusRead(BaseModel):
    status: str
    reasons: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    project_id: str | None = None
    kill_switch_enabled: bool = False
    manual_paused: bool = False
    recovery_hint: str = ""


class AgentCircuitResetRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class AgentCircuitResetRead(BaseModel):
    audit: AgentAuditRecordRead
    status: str


class AgentPreflightRead(BaseModel):
    status: str
    can_enter_grey: bool
    hard_failures: list[str] = Field(default_factory=list)
    checks: dict[str, dict[str, Any]]


class AgentReviewChangeRead(BaseModel):
    field: str
    label: str
    before: str | None = None
    after: str | None = None


class AgentReviewEvidenceRead(BaseModel):
    source_text: str
    speaker: str | None = None
    source_meeting_id: str | None = None
    source_meeting_title: str | None = None
    source_meeting_time: datetime | None = None
    source_segment_id: str | None = None


class AgentReviewProposalCardRead(BaseModel):
    id: str
    action_type: str
    action_label: str
    target_object_type: str
    target_object_id: str | None = None
    target_title: str
    source_meeting_title: str | None = None
    source_meeting_time: datetime | None = None
    risk_level: str
    risk_label: str
    status: str
    status_label: str
    changes: list[AgentReviewChangeRead]
    evidence: AgentReviewEvidenceRead | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class AgentReviewRecordRead(BaseModel):
    id: str
    proposal_id: str
    command_id: str | None = None
    action_type: str
    action_label: str
    target_object_type: str
    target_object_id: str | None = None
    target_title: str
    change_summary: str
    handled_at: datetime
    status: str
    status_label: str
    reason_preview: str | None = None


class AgentReviewOverviewRead(BaseModel):
    pending_count: int
    pending_proposals: list[AgentReviewProposalCardRead]
    recent_records: list[AgentReviewRecordRead]


class AgentReviewRecordsRead(BaseModel):
    items: list[AgentReviewRecordRead]
    total: int
    page: int
    page_size: int
    has_more: bool


class AgentReviewAuditTimelineItemRead(BaseModel):
    id: str
    result: str
    result_label: str
    decision: str
    reviewer: str
    operation: str
    reasons: list[str] = Field(default_factory=list)
    writes_performed: bool = False
    created_at: datetime


class AgentReviewCommandRead(BaseModel):
    id: str
    proposal_id: str
    target_object_type: str
    target_object_id: str
    operation: str
    expected_version: str | None = None
    changes: dict[str, Any]
    status: str
    created_at: datetime


class AgentReviewRecordDetailRead(BaseModel):
    id: str
    proposal: AgentReviewProposalCardRead
    confirmation: AgentProposalConfirmationRead | None = None
    command: AgentReviewCommandRead | None = None
    before_after: list[AgentReviewChangeRead]
    evidence: AgentReviewEvidenceRead | None = None
    reviewer: str | None = None
    executor: str | None = None
    audit_timeline: list[AgentReviewAuditTimelineItemRead]
    reject_reason: str | None = None
    rollback_reason: str | None = None
    writes_performed: bool = False
    object_version_before: str | None = None
    object_version_after: str | None = None
