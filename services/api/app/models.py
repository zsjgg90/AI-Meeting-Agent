import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    audio_files: Mapped[list["AudioFile"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.segment_index",
    )
    summary: Mapped["MeetingSummary | None"] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False,
    )
    action_items: Mapped[list["ActionItem"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    speaker_mappings: Mapped[list["SpeakerMapping"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["TranscriptionTask"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    output: Mapped["MeetingOutput | None"] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False,
    )
    chunks: Mapped[list["MeetingChunk"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


class AudioFile(Base):
    __tablename__ = "audio_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    path: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="audio_files")


class TranscriptionTask(Base):
    __tablename__ = "transcription_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meeting: Mapped[Meeting] = relationship(back_populates="tasks")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    audio_file_id: Mapped[str | None] = mapped_column(ForeignKey("audio_files.id"), nullable=True, index=True)
    segment_index: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speaker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    speaker_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    semantic_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="transcript_segments")
    audio_file: Mapped[AudioFile | None] = relationship()


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), unique=True, index=True)
    overview: Mapped[str] = mapped_column(Text)
    agenda: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    topics: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    speaker_summaries: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    decisions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    risks: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    open_questions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    next_steps: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    meeting_agenda: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    meeting_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_conclusions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    unresolved_issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    risks_and_focus: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rag_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rag_dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rag_chunk_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rag_collection_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rag_embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="summary")
    action_items: Mapped[list["ActionItem"]] = relationship(back_populates="summary", cascade="all, delete-orphan")


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    summary_id: Mapped[str | None] = mapped_column(ForeignKey("meeting_summaries.id"), nullable=True, index=True)
    task: Mapped[str] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_segment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="action_items")
    summary: Mapped[MeetingSummary | None] = relationship(back_populates="action_items")


class SpeakerMapping(Base):
    __tablename__ = "speaker_mappings"
    __table_args__ = (UniqueConstraint("meeting_id", "speaker_label", name="uq_speaker_mappings_meeting_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    speaker_label: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="speaker_mappings")


class MeetingOutput(Base):
    __tablename__ = "meeting_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), unique=True, index=True)
    raw_transcript: Mapped[str] = mapped_column(Text)
    speaker_segments: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    summary: Mapped[str] = mapped_column(Text)
    action_items: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    decisions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="output")


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), index=True)
    speaker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    meeting: Mapped[Meeting] = relationship(back_populates="chunks")


class UserFeedback(Base):
    __tablename__ = "user_feedbacks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    feedback_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
