from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.speaker_identity import build_meeting_speaker_id, parse_meeting_speaker_id


RoleSource = Literal[
    "manual_confirmation",
    "organization_profile",
    "suggested_role",
    "unknown",
]
RoleStatus = Literal["confirmed", "suggested", "unknown"]


class RoleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: RoleSource
    source: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    confirmed_role: str | None = None
    suggested_role: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    person_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoleContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(min_length=1)
    speaker_label: str = Field(min_length=1)
    confirmed_role: str | None = None
    suggested_role: str | None = None
    role_status: RoleStatus
    role_source: RoleSource
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[RoleEvidence] = Field(default_factory=list)


class ManualRoleConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_role_target(self) -> "ManualRoleConfirmation":
        if not self.speaker_id and not (self.meeting_id and self.speaker_label):
            raise ValueError("manual role confirmation requires speaker_id or meeting_id + speaker_label")
        return self

    def matches(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> bool:
        if self.speaker_id:
            return self.speaker_id == speaker_id
        return self.meeting_id == meeting_id and self.speaker_label == speaker_label

    def to_evidence(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> RoleEvidence:
        metadata = dict(self.metadata)
        if self.note:
            metadata.setdefault("note", self.note)
        return RoleEvidence(
            type="manual_confirmation",
            source="manual_confirmation",
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            meeting_id=meeting_id,
            confirmed_role=self.role,
            confidence=self.confidence,
            confirmed_by=self.confirmed_by,
            confirmed_at=self.confirmed_at,
            metadata=metadata,
        )


class OrganizationRoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    person_id: str | None = None
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source: str = Field(default="organization_profile", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_profile_target(self) -> "OrganizationRoleProfile":
        if not self.speaker_id and not (self.meeting_id and self.speaker_label):
            raise ValueError("organization role profile requires speaker_id or meeting_id + speaker_label")
        return self

    def matches(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> bool:
        if self.speaker_id:
            return self.speaker_id == speaker_id
        return self.meeting_id == meeting_id and self.speaker_label == speaker_label

    def to_evidence(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> RoleEvidence:
        return RoleEvidence(
            type="organization_profile",
            source=self.source,
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            meeting_id=meeting_id,
            confirmed_role=self.role,
            confidence=self.confidence,
            person_id=self.person_id,
            metadata=dict(self.metadata),
        )


class SuggestedRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    speaker_id: str | None = None
    speaker_label: str | None = None
    meeting_id: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="suggested_role", min_length=1)
    requires_confirmation: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_suggestion_target(self) -> "SuggestedRole":
        if not self.speaker_id and not (self.meeting_id and self.speaker_label):
            raise ValueError("suggested role requires speaker_id or meeting_id + speaker_label")
        return self

    def matches(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> bool:
        if self.speaker_id:
            return self.speaker_id == speaker_id
        return self.meeting_id == meeting_id and self.speaker_label == speaker_label

    def to_evidence(self, *, speaker_id: str, meeting_id: str, speaker_label: str) -> RoleEvidence:
        metadata = dict(self.metadata)
        metadata.setdefault("requires_confirmation", self.requires_confirmation)
        return RoleEvidence(
            type="suggested_role",
            source=self.source,
            speaker_id=speaker_id,
            speaker_label=speaker_label,
            meeting_id=meeting_id,
            suggested_role=self.role,
            confidence=self.confidence,
            metadata=metadata,
        )


class RoleResolver:
    def __init__(
        self,
        *,
        manual_confirmations: list[ManualRoleConfirmation] | None = None,
        organization_profiles: list[OrganizationRoleProfile] | None = None,
        suggested_roles: list[SuggestedRole] | None = None,
    ) -> None:
        self.manual_confirmations = manual_confirmations or []
        self.organization_profiles = organization_profiles or []
        self.suggested_roles = suggested_roles or []

    def resolve(
        self,
        *,
        speaker_id: str | None = None,
        meeting_id: str | None = None,
        speaker_label: str | None = None,
    ) -> RoleContext:
        resolved_meeting_id, resolved_speaker_label, resolved_speaker_id = self._resolve_role_key(
            speaker_id=speaker_id,
            meeting_id=meeting_id,
            speaker_label=speaker_label,
        )
        manual = self._first_match(
            self.manual_confirmations,
            speaker_id=resolved_speaker_id,
            meeting_id=resolved_meeting_id,
            speaker_label=resolved_speaker_label,
        )
        if manual is not None:
            evidence = manual.to_evidence(
                speaker_id=resolved_speaker_id,
                meeting_id=resolved_meeting_id,
                speaker_label=resolved_speaker_label,
            )
            return RoleContext(
                speaker_id=resolved_speaker_id,
                speaker_label=resolved_speaker_label,
                confirmed_role=manual.role,
                suggested_role=None,
                role_status="confirmed",
                role_source="manual_confirmation",
                confidence=manual.confidence,
                evidence=[evidence],
            )

        organization = self._first_match(
            self.organization_profiles,
            speaker_id=resolved_speaker_id,
            meeting_id=resolved_meeting_id,
            speaker_label=resolved_speaker_label,
        )
        if organization is not None:
            evidence = organization.to_evidence(
                speaker_id=resolved_speaker_id,
                meeting_id=resolved_meeting_id,
                speaker_label=resolved_speaker_label,
            )
            return RoleContext(
                speaker_id=resolved_speaker_id,
                speaker_label=resolved_speaker_label,
                confirmed_role=organization.role,
                suggested_role=None,
                role_status="confirmed",
                role_source="organization_profile",
                confidence=organization.confidence,
                evidence=[evidence],
            )

        suggestion = self._first_match(
            self.suggested_roles,
            speaker_id=resolved_speaker_id,
            meeting_id=resolved_meeting_id,
            speaker_label=resolved_speaker_label,
        )
        if suggestion is not None:
            evidence = suggestion.to_evidence(
                speaker_id=resolved_speaker_id,
                meeting_id=resolved_meeting_id,
                speaker_label=resolved_speaker_label,
            )
            return RoleContext(
                speaker_id=resolved_speaker_id,
                speaker_label=resolved_speaker_label,
                confirmed_role=None,
                suggested_role=suggestion.role,
                role_status="suggested",
                role_source="suggested_role",
                confidence=suggestion.confidence,
                evidence=[evidence],
            )

        return RoleContext(
            speaker_id=resolved_speaker_id,
            speaker_label=resolved_speaker_label,
            confirmed_role=None,
            suggested_role=None,
            role_status="unknown",
            role_source="unknown",
            confidence=0.0,
            evidence=[],
        )

    def resolve_many(self, *, meeting_id: str, speaker_labels: list[str]) -> dict[str, RoleContext]:
        return {
            speaker_label: self.resolve(meeting_id=meeting_id, speaker_label=speaker_label)
            for speaker_label in speaker_labels
        }

    @staticmethod
    def _first_match(
        records: list[ManualRoleConfirmation] | list[OrganizationRoleProfile] | list[SuggestedRole],
        *,
        speaker_id: str,
        meeting_id: str,
        speaker_label: str,
    ) -> ManualRoleConfirmation | OrganizationRoleProfile | SuggestedRole | None:
        for record in records:
            if record.matches(speaker_id=speaker_id, meeting_id=meeting_id, speaker_label=speaker_label):
                return record
        return None

    @staticmethod
    def _resolve_role_key(
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
