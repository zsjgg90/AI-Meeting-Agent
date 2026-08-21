from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.speaker_identity import SpeakerIdentityContext, SpeakerResolver
from app.speaker_role import RoleContext, RoleResolver


class SpeakerContextBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: str
    speaker_contexts: dict[str, SpeakerIdentityContext] = Field(default_factory=dict)
    speaker_role_context: dict[str, RoleContext] = Field(default_factory=dict)

    def to_shadow_context(self) -> dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "speaker_contexts": {
                speaker_id: context.model_dump(mode="json")
                for speaker_id, context in self.speaker_contexts.items()
            },
            "speaker_role_context": {
                speaker_id: context.model_dump(mode="json")
                for speaker_id, context in self.speaker_role_context.items()
            },
        }


def _field(item: object, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _speaker_label(item: object) -> str | None:
    value = _field(item, "speaker_label") or _field(item, "speaker") or _field(item, "speaker_name")
    if value is None:
        return None
    label = str(value).strip()
    return label or None


def collect_speaker_labels(transcript: list[Any]) -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for row in transcript:
        label = _speaker_label(row)
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


class SpeakerContextBuilder:
    def __init__(
        self,
        resolver: SpeakerResolver | None = None,
        role_resolver: RoleResolver | None = None,
    ) -> None:
        self.resolver = resolver or SpeakerResolver()
        self.role_resolver = role_resolver or RoleResolver()

    def build(self, *, meeting_id: str, transcript: list[Any]) -> SpeakerContextBuildResult:
        contexts: dict[str, SpeakerIdentityContext] = {}
        role_context: dict[str, RoleContext] = {}
        for speaker_label in collect_speaker_labels(transcript):
            context = self.resolver.resolve(meeting_id=meeting_id, speaker_label=speaker_label)
            contexts[context.speaker_id] = context
            role = self.role_resolver.resolve(meeting_id=meeting_id, speaker_label=speaker_label)
            role_context[role.speaker_id] = role
        return SpeakerContextBuildResult(
            meeting_id=meeting_id,
            speaker_contexts=contexts,
            speaker_role_context=role_context,
        )
