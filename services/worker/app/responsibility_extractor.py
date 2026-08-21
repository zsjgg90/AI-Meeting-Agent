from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.speaker_identity import SpeakerIdentityContext
from app.speaker_role import RoleContext


ResponsibilityType = Literal["explicit_owner", "commitment", "assignment", "unknown"]
ResponsibilitySourceType = Literal[
    "transcript",
    "formal_action_item",
    "semantic_event",
    "manual_confirmation",
    "agent_proposal",
    "unknown",
]
ResponsibilityEvidenceType = Literal[
    "explicit_owner_text",
    "commitment_text",
    "assignment_text",
    "unknown_owner",
]


class ResponsibilityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ResponsibilityEvidenceType
    source_type: ResponsibilitySourceType = "semantic_event"
    meeting_id: str | None = None
    event_id: str | None = None
    utterance_id: str | None = None
    segment_id: str | None = None
    speaker_id: str | None = None
    source_text: str = Field(min_length=1)
    owner_text: str | None = None
    task_text: str | None = None
    supported_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResponsibilityContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsibility_id: str = Field(min_length=1)
    speaker_id: str | None = None
    identity_context: SpeakerIdentityContext | None = None
    role_context: RoleContext | None = None
    responsibility_type: ResponsibilityType
    task: str = Field(min_length=1)
    owner: str | None = None
    evidence: list[ResponsibilityEvidence] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: ResponsibilitySourceType = "semantic_event"

    @model_validator(mode="after")
    def validate_owner_support(self) -> "ResponsibilityContext":
        if self.responsibility_type == "unknown" and self.owner is not None:
            raise ValueError("unknown responsibility cannot have owner")
        if self.responsibility_type != "unknown" and not self.owner:
            raise ValueError("known responsibility requires owner")
        return self


class ResponsibilityExtractor:
    _FIRST_PERSON_COMMITMENT_RE = re.compile(
        r"(^|[，。,.;；\s])("
        r"我(会|来|负责|去|可以负责|可以来|继续|马上|明天|今天|本周|下周)"
        r"|I'll|I will|I can handle|I can take|I am going to"
        r")",
        re.IGNORECASE,
    )
    _DISCUSSION_ONLY_RE = re.compile(r"(讨论|评估|看看|看一下|考虑|建议|可能|也许|maybe|consider)", re.IGNORECASE)
    _ASSIGNMENT_RE = re.compile(
        r"(请|麻烦|安排|交给|由)\s*(?P<owner>[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,40}?)(负责|处理|跟进|完成|同步|确认|推进)"
        r"|(?P<owner_en>[A-Z][A-Za-z ._-]{0,40}?)(,?\s+please\s+(handle|follow up|finish|sync|confirm))",
        re.IGNORECASE,
    )

    def extract(
        self,
        *,
        semantic_event: Any,
        meeting_id: str | None = None,
        speaker_context: SpeakerIdentityContext | None = None,
        role_context: RoleContext | None = None,
    ) -> ResponsibilityContext:
        source_text = self._source_text(semantic_event)
        task = self._task_text(semantic_event, source_text)
        speaker_id = self._speaker_id(semantic_event, speaker_context)
        source_confidence = self._event_confidence(semantic_event)

        owner_from_event = self._event_owner(semantic_event)
        if owner_from_event and self._contains_text(source_text, owner_from_event):
            return self._context(
                responsibility_type="explicit_owner",
                task=task,
                owner=owner_from_event,
                evidence_type="explicit_owner_text",
                evidence_confidence=max(0.75, source_confidence),
                semantic_event=semantic_event,
                meeting_id=meeting_id,
                speaker_id=speaker_id,
                source_text=source_text,
                speaker_context=speaker_context,
                role_context=role_context,
            )

        assignment_owner = self._assignment_owner(source_text)
        if assignment_owner and self._looks_actionable(semantic_event, source_text):
            return self._context(
                responsibility_type="assignment",
                task=task,
                owner=assignment_owner,
                evidence_type="assignment_text",
                evidence_confidence=max(0.7, source_confidence),
                semantic_event=semantic_event,
                meeting_id=meeting_id,
                speaker_id=speaker_id,
                source_text=source_text,
                speaker_context=speaker_context,
                role_context=role_context,
            )

        if self._is_first_person_commitment(semantic_event, source_text):
            owner = self._speaker_owner(semantic_event, speaker_context)
            if owner:
                identity_confirmed = speaker_context is not None and speaker_context.identity_status == "confirmed"
                return self._context(
                    responsibility_type="commitment",
                    task=task,
                    owner=owner,
                    evidence_type="commitment_text",
                    evidence_confidence=0.82 if identity_confirmed else 0.62,
                    semantic_event=semantic_event,
                    meeting_id=meeting_id,
                    speaker_id=speaker_id,
                    source_text=source_text,
                    speaker_context=speaker_context,
                    role_context=role_context,
                    requires_confirmation=not identity_confirmed,
                )

        return self._context(
            responsibility_type="unknown",
            task=task,
            owner=None,
            evidence_type="unknown_owner",
            evidence_confidence=min(0.35, source_confidence),
            semantic_event=semantic_event,
            meeting_id=meeting_id,
            speaker_id=speaker_id,
            source_text=source_text,
            speaker_context=speaker_context,
            role_context=role_context,
            supported_fields=["task"],
        )

    def extract_many(
        self,
        *,
        semantic_events: list[Any],
        meeting_id: str | None = None,
        speaker_contexts: dict[str, SpeakerIdentityContext] | None = None,
        role_contexts: dict[str, RoleContext] | None = None,
    ) -> list[ResponsibilityContext]:
        contexts: list[ResponsibilityContext] = []
        for event in semantic_events:
            speaker_key = self._event_speaker_key(event)
            contexts.append(
                self.extract(
                    semantic_event=event,
                    meeting_id=meeting_id,
                    speaker_context=self._lookup_context(speaker_contexts, speaker_key, meeting_id),
                    role_context=self._lookup_context(role_contexts, speaker_key, meeting_id),
                )
            )
        return contexts

    def _context(
        self,
        *,
        responsibility_type: ResponsibilityType,
        task: str,
        owner: str | None,
        evidence_type: ResponsibilityEvidenceType,
        evidence_confidence: float,
        semantic_event: Any,
        meeting_id: str | None,
        speaker_id: str | None,
        source_text: str,
        speaker_context: SpeakerIdentityContext | None,
        role_context: RoleContext | None,
        requires_confirmation: bool = False,
        supported_fields: list[str] | None = None,
    ) -> ResponsibilityContext:
        if supported_fields is None:
            supported_fields = ["task", "owner"] if owner else ["task"]
        evidence = ResponsibilityEvidence(
            type=evidence_type,
            source_type="semantic_event",
            meeting_id=meeting_id,
            event_id=self._optional_str(semantic_event, "event_id"),
            utterance_id=self._optional_str(semantic_event, "utterance_id"),
            segment_id=self._optional_str(semantic_event, "segment_id"),
            speaker_id=speaker_id,
            source_text=source_text,
            owner_text=owner,
            task_text=task,
            supported_fields=supported_fields,
            confidence=evidence_confidence,
            requires_confirmation=requires_confirmation,
        )
        return ResponsibilityContext(
            responsibility_id=self._responsibility_id(
                meeting_id=meeting_id,
                source_id=evidence.segment_id or evidence.event_id or evidence.utterance_id,
                task=task,
                owner=owner,
                source_text=source_text,
            ),
            speaker_id=speaker_id,
            identity_context=speaker_context,
            role_context=role_context,
            responsibility_type=responsibility_type,
            task=task,
            owner=owner,
            evidence=[evidence],
            confidence=evidence_confidence,
            source_type="semantic_event",
        )

    @staticmethod
    def _source_text(semantic_event: Any) -> str:
        source_text = ResponsibilityExtractor._optional_str(semantic_event, "source_text")
        if source_text:
            return source_text
        evidence = getattr(semantic_event, "evidence", None)
        evidence_text = getattr(evidence, "source_text", None) if evidence is not None else None
        if evidence_text:
            return str(evidence_text).strip()
        normalized_text = ResponsibilityExtractor._optional_str(semantic_event, "normalized_text")
        return normalized_text or "unknown source text"

    @staticmethod
    def _task_text(semantic_event: Any, source_text: str) -> str:
        action = ResponsibilityExtractor._optional_str(semantic_event, "action")
        obj = ResponsibilityExtractor._optional_str(semantic_event, "object")
        if action and obj:
            return f"{action}{obj}" if ResponsibilityExtractor._contains_cjk(action + obj) else f"{action} {obj}"
        return obj or action or ResponsibilityExtractor._trim_task_source(source_text)

    @staticmethod
    def _trim_task_source(source_text: str) -> str:
        return source_text.strip().strip("。.!?？") or "unknown task"

    @staticmethod
    def _event_owner(semantic_event: Any) -> str | None:
        attributes = getattr(semantic_event, "attributes", None)
        owner = getattr(attributes, "owner", None) if attributes is not None else None
        if owner:
            return str(owner).strip()
        return None

    @staticmethod
    def _event_confidence(semantic_event: Any) -> float:
        confidence = getattr(semantic_event, "confidence", None)
        value = getattr(confidence, "overall", None) if confidence is not None else None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, result))

    @staticmethod
    def _speaker_id(semantic_event: Any, speaker_context: SpeakerIdentityContext | None) -> str | None:
        if speaker_context is not None:
            return speaker_context.speaker_id
        return ResponsibilityExtractor._optional_str(semantic_event, "speaker")

    @staticmethod
    def _speaker_owner(semantic_event: Any, speaker_context: SpeakerIdentityContext | None) -> str | None:
        if speaker_context is not None:
            return speaker_context.display_name
        return ResponsibilityExtractor._optional_str(semantic_event, "speaker")

    @staticmethod
    def _event_speaker_key(semantic_event: Any) -> str | None:
        return ResponsibilityExtractor._optional_str(semantic_event, "speaker")

    @staticmethod
    def _lookup_context(contexts: dict[str, Any] | None, speaker_key: str | None, meeting_id: str | None) -> Any | None:
        if not contexts or not speaker_key:
            return None
        meeting_speaker_id = f"meeting:{meeting_id}:{speaker_key}" if meeting_id else None
        if meeting_speaker_id and meeting_speaker_id in contexts:
            return contexts[meeting_speaker_id]
        return contexts.get(speaker_key) or contexts.get(speaker_key.lower())

    @staticmethod
    def _assignment_owner(source_text: str) -> str | None:
        match = ResponsibilityExtractor._ASSIGNMENT_RE.search(source_text)
        if not match:
            return None
        owner = match.groupdict().get("owner") or match.groupdict().get("owner_en")
        if not owner:
            return None
        return owner.strip(" ，。,.;；")

    @staticmethod
    def _is_first_person_commitment(semantic_event: Any, source_text: str) -> bool:
        primary_intent = ResponsibilityExtractor._optional_str(semantic_event, "primary_intent")
        if primary_intent != "commitment" and not ResponsibilityExtractor._FIRST_PERSON_COMMITMENT_RE.search(source_text):
            return False
        if ResponsibilityExtractor._DISCUSSION_ONLY_RE.search(source_text) and not ResponsibilityExtractor._FIRST_PERSON_COMMITMENT_RE.search(source_text):
            return False
        return ResponsibilityExtractor._FIRST_PERSON_COMMITMENT_RE.search(source_text) is not None

    @staticmethod
    def _looks_actionable(semantic_event: Any, source_text: str) -> bool:
        primary_intent = ResponsibilityExtractor._optional_str(semantic_event, "primary_intent")
        if primary_intent in {"task_assignment", "commitment"}:
            return True
        return ResponsibilityExtractor._DISCUSSION_ONLY_RE.search(source_text) is None

    @staticmethod
    def _optional_str(obj: Any, field_name: str) -> str | None:
        value = getattr(obj, field_name, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _contains_text(source_text: str, value: str) -> bool:
        return value.strip().lower() in source_text.lower()

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return re.search(r"[\u4e00-\u9fff]", value) is not None

    @staticmethod
    def _responsibility_id(
        *,
        meeting_id: str | None,
        source_id: str | None,
        task: str,
        owner: str | None,
        source_text: str,
    ) -> str:
        basis = "|".join([meeting_id or "unknown", source_id or "unknown", task, owner or "", source_text])
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
        return f"resp:{meeting_id or 'unknown'}:{source_id or 'unknown'}:{digest}"


__all__ = [
    "ResponsibilityContext",
    "ResponsibilityEvidence",
    "ResponsibilityExtractor",
    "ResponsibilityEvidenceType",
    "ResponsibilitySourceType",
    "ResponsibilityType",
]
