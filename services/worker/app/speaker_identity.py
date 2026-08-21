from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


IdentitySource = Literal[
    "manual_confirmation",
    "unknown",
    "voiceprint_match",
    "organization_profile",
]
IdentityStatus = Literal["confirmed", "anonymous", "suggested", "conflicted", "rejected"]
EvidenceType = Literal[
    "manual_confirmation",
    "voiceprint_match",
    "organization_profile",
]


class SpeakerIdentityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EvidenceType
    source: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    display_name: str | None = None
    role: str | None = None
    department: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeakerIdentityContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1)
    speaker_label: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str | None = None
    department: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    identity_source: IdentitySource
    identity_status: IdentityStatus
    evidence: list[SpeakerIdentityEvidence] = Field(default_factory=list)


class ManualSpeakerConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    role: str | None = None
    department: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_identity_target(self) -> "ManualSpeakerConfirmation":
        if not self.speaker_id and not (self.meeting_id and self.speaker_label):
            raise ValueError("manual confirmation requires speaker_id or meeting_id + speaker_label")
        return self

    def matches(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> bool:
        if self.speaker_id:
            return self.speaker_id == speaker_id
        return self.meeting_id == meeting_id and self.speaker_label == speaker_label

    def to_evidence(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> SpeakerIdentityEvidence:
        metadata = dict(self.metadata)
        if self.note:
            metadata.setdefault("note", self.note)
        return SpeakerIdentityEvidence(
            type="manual_confirmation",
            source="manual_confirmation",
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            meeting_id=meeting_id,
            display_name=self.display_name,
            role=self.role,
            department=self.department,
            confidence=self.confidence,
            confirmed_by=self.confirmed_by,
            confirmed_at=self.confirmed_at,
            metadata=metadata,
        )


def build_meeting_speaker_id(meeting_id: str, speaker_label: str) -> str:
    return f"meeting:{meeting_id}:{speaker_label}"


def parse_meeting_speaker_id(speaker_id: str) -> tuple[str, str]:
    prefix = "meeting:"
    if not speaker_id.startswith(prefix):
        raise ValueError("speaker_id must use meeting:<meeting_id>:<speaker_label>")
    remainder = speaker_id.removeprefix(prefix)
    meeting_id, separator, speaker_label = remainder.partition(":")
    if not meeting_id or not separator or not speaker_label:
        raise ValueError("speaker_id must use meeting:<meeting_id>:<speaker_label>")
    return meeting_id, speaker_label


class SpeakerResolver:
    def __init__(self, manual_confirmations: list[ManualSpeakerConfirmation] | None = None) -> None:
        self.manual_confirmations = manual_confirmations or []

    def resolve(
        self,
        *,
        speaker_id: str | None = None,
        meeting_id: str | None = None,
        speaker_label: str | None = None,
    ) -> SpeakerIdentityContext:
        resolved_meeting_id, resolved_speaker_label, resolved_speaker_id = self._resolve_identity_key(
            speaker_id=speaker_id,
            meeting_id=meeting_id,
            speaker_label=speaker_label,
        )
        confirmation = self._manual_confirmation_for(
            speaker_id=resolved_speaker_id,
            meeting_id=resolved_meeting_id,
            speaker_label=resolved_speaker_label,
        )
        if confirmation is not None:
            return self._from_manual_confirmation(
                confirmation,
                speaker_id=resolved_speaker_id,
                meeting_id=resolved_meeting_id,
                speaker_label=resolved_speaker_label,
            )
        return self._unknown_context(
            speaker_id=resolved_speaker_id,
            speaker_label=resolved_speaker_label,
        )

    def resolve_many(
        self,
        *,
        meeting_id: str,
        speaker_labels: list[str],
    ) -> dict[str, SpeakerIdentityContext]:
        return {
            speaker_label: self.resolve(meeting_id=meeting_id, speaker_label=speaker_label)
            for speaker_label in speaker_labels
        }

    def _manual_confirmation_for(
        self,
        *,
        speaker_id: str,
        meeting_id: str,
        speaker_label: str,
    ) -> ManualSpeakerConfirmation | None:
        for confirmation in self.manual_confirmations:
            if confirmation.matches(speaker_id=speaker_id, meeting_id=meeting_id, speaker_label=speaker_label):
                return confirmation
        return None

    @staticmethod
    def _resolve_identity_key(
        *,
        speaker_id: str | None,
        meeting_id: str | None,
        speaker_label: str | None,
    ) -> tuple[str, str, str]:
        if speaker_id:
            parsed_meeting_id, parsed_speaker_label = parse_meeting_speaker_id(speaker_id)
            if meeting_id and meeting_id != parsed_meeting_id:
                raise ValueError("meeting_id does not match speaker_id")
            if speaker_label and speaker_label != parsed_speaker_label:
                raise ValueError("speaker_label does not match speaker_id")
            return parsed_meeting_id, parsed_speaker_label, speaker_id
        if not meeting_id or not speaker_label:
            raise ValueError("resolve requires speaker_id or meeting_id + speaker_label")
        return meeting_id, speaker_label, build_meeting_speaker_id(meeting_id, speaker_label)

    @staticmethod
    def _from_manual_confirmation(
        confirmation: ManualSpeakerConfirmation,
        *,
        speaker_id: str,
        meeting_id: str,
        speaker_label: str,
    ) -> SpeakerIdentityContext:
        evidence = confirmation.to_evidence(
            speaker_id=speaker_id,
            meeting_id=meeting_id,
            speaker_label=speaker_label,
        )
        return SpeakerIdentityContext(
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            display_name=confirmation.display_name,
            role=confirmation.role,
            department=confirmation.department,
            confidence=confirmation.confidence,
            identity_source="manual_confirmation",
            identity_status="confirmed",
            evidence=[evidence],
        )

    @staticmethod
    def _unknown_context(*, speaker_id: str, speaker_label: str) -> SpeakerIdentityContext:
        return SpeakerIdentityContext(
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            display_name=speaker_label,
            role=None,
            department=None,
            confidence=0.0,
            identity_source="unknown",
            identity_status="anonymous",
            evidence=[],
        )
