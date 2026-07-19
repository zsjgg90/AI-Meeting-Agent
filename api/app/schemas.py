from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MeetingCreate(BaseModel):
    title: str = Field(default="Untitled meeting", max_length=255)


class AudioFileRead(BaseModel):
    id: str
    filename: str
    content_type: str | None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    created_at: datetime
    updated_at: datetime
    audio_files: list[AudioFileRead] = []
    tasks: list[TranscriptionTaskRead] = []
    output: MeetingOutputRead | None = None
    chunks: list[MeetingChunkRead] = []

    model_config = ConfigDict(from_attributes=True)


class MeetingCreated(BaseModel):
    meeting_id: str
    status: str


class AudioUploaded(BaseModel):
    audio_file_id: str
    meeting_id: str
    filename: str


class TaskCreated(BaseModel):
    task_id: str
    meeting_id: str
    status: str
