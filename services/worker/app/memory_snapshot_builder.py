from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.responsibility_evidence_matrix import ResponsibilityEvidenceMatrix
from app.responsibility_extractor import ResponsibilityContext
from app.speaker_identity import SpeakerIdentityContext
from app.speaker_role import RoleContext


MemoryType = Literal["entity", "responsibility", "meeting"]
MemoryStatus = Literal[
    "candidate",
    "active",
    "needs_review",
    "confirmed",
    "superseded",
    "expired",
    "conflicted",
    "rejected",
]
MeetingMemoryType = Literal[
    "decision",
    "risk",
    "unresolved_issue",
    "project_fact",
    "dependency",
    "scope_change",
    "requirement_change",
]


class MemorySourceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    meeting_id: str | None = None
    source_id: str | None = None
    occurred_at: datetime | None = None


class MemoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    meeting_id: str | None = None
    source_id: str | None = None
    segment_id: str | None = None
    speaker_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    source_text: str | None = None
    supported_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1)
    memory_type: MemoryType
    content: dict[str, Any] = Field(default_factory=dict)
    source_event: MemorySourceEvent
    evidence: list[MemoryEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    status: MemoryStatus = "candidate"

    @model_validator(mode="after")
    def require_evidence_for_fact_memory(self) -> "MemoryContext":
        if self.memory_type in {"entity", "responsibility", "meeting"} and not self.evidence:
            raise ValueError("memory context requires evidence")
        return self


class MemorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: str | None = None
    as_of: datetime
    memories: list[MemoryContext] = Field(default_factory=list)


class MemorySnapshotBuilder:
    def build(
        self,
        *,
        speaker_contexts: dict[str, SpeakerIdentityContext] | list[SpeakerIdentityContext] | None = None,
        role_contexts: dict[str, RoleContext] | list[RoleContext] | None = None,
        responsibility_contexts: list[ResponsibilityContext | dict[str, Any]] | None = None,
        responsibility_matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None = None,
        meeting_analysis_events: list[Any] | None = None,
        meeting_id: str | None = None,
        created_at: datetime | None = None,
    ) -> MemorySnapshot:
        resolved_created_at = created_at or datetime.now(UTC)
        candidates: list[MemoryContext] = []
        role_by_speaker = self._index_by_speaker_id(role_contexts)

        for speaker_context in self._iter_values(speaker_contexts):
            candidates.extend(
                self._entity_memories(
                    speaker_context=speaker_context,
                    role_context=role_by_speaker.get(speaker_context.speaker_id),
                    created_at=resolved_created_at,
                )
            )

        for role_context in self._iter_values(role_contexts):
            if role_context.speaker_id in {item.content.get("speaker_id") for item in candidates}:
                continue
            candidates.extend(
                self._role_only_entity_memories(
                    role_context=role_context,
                    created_at=resolved_created_at,
                )
            )

        for context in responsibility_contexts or []:
            memory = self._responsibility_memory(
                context=context,
                created_at=resolved_created_at,
            )
            if memory is not None:
                candidates.append(memory)

        for row in self._matrix_rows(responsibility_matrix):
            memory = self._responsibility_matrix_memory(row=row, created_at=resolved_created_at)
            if memory is not None:
                candidates.append(memory)

        for event in meeting_analysis_events or []:
            memory = self._meeting_memory(event=event, meeting_id=meeting_id, created_at=resolved_created_at)
            if memory is not None:
                candidates.append(memory)

        return MemorySnapshot(
            meeting_id=meeting_id,
            as_of=resolved_created_at,
            memories=self._deduplicate(candidates),
        )

    def _entity_memories(
        self,
        *,
        speaker_context: SpeakerIdentityContext,
        role_context: RoleContext | None,
        created_at: datetime,
    ) -> list[MemoryContext]:
        evidence = [
            self._speaker_evidence(item, created_at=created_at)
            for item in speaker_context.evidence
        ]
        if role_context is not None:
            evidence.extend(
                self._role_evidence(item, created_at=created_at)
                for item in role_context.evidence
            )
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return []

        role = role_context.confirmed_role if role_context and role_context.confirmed_role else speaker_context.role
        suggested_role = role_context.suggested_role if role_context else None
        content = {
            "entity_type": "person",
            "person_id": None,
            "speaker_id": speaker_context.speaker_id,
            "display_name": speaker_context.display_name,
            "role": role,
            "suggested_role": suggested_role,
            "department": speaker_context.department,
            "identity_status": speaker_context.identity_status,
            "role_status": role_context.role_status if role_context else None,
            "scope": "meeting",
        }
        confidence = self._bounded_max([speaker_context.confidence, role_context.confidence if role_context else 0.0])
        return [
            self._context(
                memory_type="entity",
                content=content,
                source_event=MemorySourceEvent(
                    source_type="speaker_context",
                    meeting_id=evidence[0].meeting_id,
                    source_id=speaker_context.speaker_id,
                    occurred_at=self._first_datetime(evidence),
                ),
                evidence=evidence,
                confidence=confidence,
                created_at=created_at,
            )
        ]

    def _role_only_entity_memories(self, *, role_context: RoleContext, created_at: datetime) -> list[MemoryContext]:
        evidence = [self._role_evidence(item, created_at=created_at) for item in role_context.evidence]
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return []
        content = {
            "entity_type": "person",
            "person_id": None,
            "speaker_id": role_context.speaker_id,
            "display_name": role_context.speaker_label,
            "role": role_context.confirmed_role,
            "suggested_role": role_context.suggested_role,
            "department": None,
            "identity_status": None,
            "role_status": role_context.role_status,
            "scope": "meeting",
        }
        return [
            self._context(
                memory_type="entity",
                content=content,
                source_event=MemorySourceEvent(
                    source_type="role_context",
                    meeting_id=evidence[0].meeting_id,
                    source_id=role_context.speaker_id,
                    occurred_at=self._first_datetime(evidence),
                ),
                evidence=evidence,
                confidence=role_context.confidence,
                created_at=created_at,
            )
        ]

    def _responsibility_memory(
        self,
        *,
        context: ResponsibilityContext | dict[str, Any],
        created_at: datetime,
    ) -> MemoryContext | None:
        evidence = [self._responsibility_evidence(item, created_at=created_at) for item in self._value(context, "evidence") or []]
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return None
        responsibility_type = self._clean_text(self._value(context, "responsibility_type")) or "unknown"
        content = {
            "task": self._clean_text(self._value(context, "task")),
            "owner": self._clean_text(self._value(context, "owner")),
            "responsibility_type": responsibility_type,
            "deadline": None,
            "priority": None,
            "status": "unknown" if responsibility_type == "unknown" else "open",
            "dependency": None,
        }
        return self._context(
            memory_type="responsibility",
            content=content,
            source_event=MemorySourceEvent(
                source_type="responsibility_context",
                meeting_id=evidence[0].meeting_id,
                source_id=self._clean_text(self._value(context, "responsibility_id")),
                occurred_at=self._first_datetime(evidence),
            ),
            evidence=evidence,
            confidence=self._float_value(self._value(context, "confidence")),
            created_at=created_at,
        )

    def _responsibility_matrix_memory(self, *, row: Any, created_at: datetime) -> MemoryContext | None:
        if self._value(row, "consistency_status") not in {"owner_missing", "owner_conflict"}:
            return None
        evidence_items = self._value(row, "evidence") or []
        evidence = [self._responsibility_evidence(item, created_at=created_at) for item in evidence_items]
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return None
        candidates = self._value(row, "responsibility_candidates") or []
        first_candidate = candidates[0] if candidates else {}
        content = {
            "task": self._value(first_candidate, "task") or self._value(row, "task_key"),
            "owner": self._value(first_candidate, "owner"),
            "responsibility_type": self._value(first_candidate, "responsibility_type") or "unknown",
            "deadline": None,
            "priority": None,
            "status": self._value(row, "consistency_status"),
            "dependency": None,
            "action_owner": self._value(row, "action_owner"),
        }
        return self._context(
            memory_type="responsibility",
            content=content,
            source_event=MemorySourceEvent(
                source_type="responsibility_matrix",
                meeting_id=evidence[0].meeting_id,
                source_id=self._value(row, "task_key"),
                occurred_at=self._first_datetime(evidence),
            ),
            evidence=evidence,
            confidence=self._float_value(self._value(row, "confidence")),
            created_at=created_at,
        )

    def _meeting_memory(
        self,
        *,
        event: Any,
        meeting_id: str | None,
        created_at: datetime,
    ) -> MemoryContext | None:
        text = self._meeting_event_text(event)
        source_text = self._clean_text(self._value(event, "source_text") or self._value(event, "evidence_text"))
        source_id = self._clean_text(
            self._value(event, "source_id")
            or self._value(event, "source_segment_id")
            or self._value(event, "event_id")
            or self._value(event, "id")
        )
        if not text or not source_text:
            return None
        event_meeting_id = self._clean_text(self._value(event, "meeting_id")) or meeting_id
        memory_kind = self._meeting_memory_type(event)
        evidence = [
            MemoryEvidence(
                evidence_id=self._evidence_id(
                    source_type=self._clean_text(self._value(event, "source_type")) or "formal_summary_item",
                    meeting_id=event_meeting_id,
                    source_id=source_id,
                    source_text=source_text,
                    supported_fields=["text", "meeting_memory_type"],
                ),
                source_type=self._clean_text(self._value(event, "source_type")) or "formal_summary_item",
                meeting_id=event_meeting_id,
                source_id=source_id,
                segment_id=self._clean_text(self._value(event, "source_segment_id")),
                source_text=source_text,
                supported_fields=["text", "meeting_memory_type"],
                confidence=self._float_value(self._value(event, "confidence"), default=0.0),
                created_at=created_at,
            )
        ]
        return self._context(
            memory_type="meeting",
            content={
                "meeting_memory_type": memory_kind,
                "text": text,
                "related_entities": self._string_list(self._value(event, "related_entities")),
                "related_responsibilities": self._string_list(self._value(event, "related_responsibilities")),
                "effective_status": self._clean_text(self._value(event, "effective_status")) or "current",
            },
            source_event=MemorySourceEvent(
                source_type=self._clean_text(self._value(event, "source_type")) or "formal_summary_item",
                meeting_id=event_meeting_id,
                source_id=source_id,
                occurred_at=self._datetime_value(self._value(event, "occurred_at")),
            ),
            evidence=evidence,
            confidence=evidence[0].confidence,
            created_at=created_at,
        )

    def _context(
        self,
        *,
        memory_type: MemoryType,
        content: dict[str, Any],
        source_event: MemorySourceEvent,
        evidence: list[MemoryEvidence],
        confidence: float,
        created_at: datetime,
    ) -> MemoryContext:
        memory_id = self._memory_id(memory_type=memory_type, content=content)
        return MemoryContext(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            source_event=source_event,
            evidence=evidence,
            confidence=max(0.0, min(1.0, confidence)),
            created_at=created_at,
            status="candidate",
        )

    def _deduplicate(self, memories: list[MemoryContext]) -> list[MemoryContext]:
        by_id: dict[str, MemoryContext] = {}
        evidence_ids_by_memory: dict[str, set[str]] = {}
        for memory in memories:
            existing = by_id.get(memory.memory_id)
            if existing is None:
                by_id[memory.memory_id] = memory
                evidence_ids_by_memory[memory.memory_id] = {item.evidence_id for item in memory.evidence}
                continue
            known_evidence_ids = evidence_ids_by_memory[memory.memory_id]
            merged_evidence = list(existing.evidence)
            for evidence in memory.evidence:
                if evidence.evidence_id in known_evidence_ids:
                    continue
                merged_evidence.append(evidence)
                known_evidence_ids.add(evidence.evidence_id)
            by_id[memory.memory_id] = existing.model_copy(
                update={
                    "evidence": merged_evidence,
                    "confidence": max(existing.confidence, memory.confidence),
                }
            )
        return list(by_id.values())

    def _speaker_evidence(self, item: Any, *, created_at: datetime) -> MemoryEvidence | None:
        source_type = self._clean_text(self._value(item, "type")) or self._clean_text(self._value(item, "source"))
        if not source_type:
            return None
        meeting_id = self._clean_text(self._value(item, "meeting_id"))
        speaker_id = self._clean_text(self._value(item, "speaker_id"))
        speaker_label = self._clean_text(self._value(item, "speaker_label"))
        supported_fields = [
            field
            for field in ("display_name", "role", "department")
            if self._clean_text(self._value(item, field))
        ]
        if not supported_fields:
            supported_fields = ["display_name"]
        return MemoryEvidence(
            evidence_id=self._evidence_id(
                source_type=source_type,
                meeting_id=meeting_id,
                source_id=speaker_id or speaker_label,
                source_text=self._clean_text(self._value(item, "display_name")),
                supported_fields=supported_fields,
            ),
            source_type=source_type,
            meeting_id=meeting_id,
            source_id=speaker_id or speaker_label,
            speaker_id=speaker_id,
            supported_fields=supported_fields,
            confidence=self._float_value(self._value(item, "confidence"), default=0.0),
            created_at=self._datetime_value(self._value(item, "confirmed_at")) or created_at,
            metadata=dict(self._value(item, "metadata") or {}),
        )

    def _role_evidence(self, item: Any, *, created_at: datetime) -> MemoryEvidence | None:
        source_type = self._clean_text(self._value(item, "type")) or self._clean_text(self._value(item, "source"))
        if not source_type:
            return None
        meeting_id = self._clean_text(self._value(item, "meeting_id"))
        speaker_id = self._clean_text(self._value(item, "speaker_id"))
        speaker_label = self._clean_text(self._value(item, "speaker_label"))
        role_text = self._clean_text(self._value(item, "confirmed_role") or self._value(item, "suggested_role"))
        return MemoryEvidence(
            evidence_id=self._evidence_id(
                source_type=source_type,
                meeting_id=meeting_id,
                source_id=speaker_id or speaker_label,
                source_text=role_text,
                supported_fields=["role"],
            ),
            source_type=source_type,
            meeting_id=meeting_id,
            source_id=speaker_id or speaker_label,
            speaker_id=speaker_id,
            supported_fields=["role"],
            confidence=self._float_value(self._value(item, "confidence"), default=0.0),
            created_at=self._datetime_value(self._value(item, "confirmed_at")) or created_at,
            metadata=dict(self._value(item, "metadata") or {}),
        )

    def _responsibility_evidence(self, item: Any, *, created_at: datetime) -> MemoryEvidence | None:
        source_text = self._clean_text(self._value(item, "source_text"))
        supported_fields = self._string_list(self._value(item, "supported_fields"))
        if not source_text or not supported_fields:
            return None
        meeting_id = self._clean_text(self._value(item, "meeting_id"))
        source_id = self._clean_text(
            self._value(item, "segment_id")
            or self._value(item, "event_id")
            or self._value(item, "utterance_id")
            or self._value(item, "source_id")
        )
        return MemoryEvidence(
            evidence_id=self._evidence_id(
                source_type=self._clean_text(self._value(item, "source_type")) or "responsibility_context",
                meeting_id=meeting_id,
                source_id=source_id,
                source_text=source_text,
                supported_fields=supported_fields,
            ),
            source_type=self._clean_text(self._value(item, "source_type")) or "responsibility_context",
            meeting_id=meeting_id,
            source_id=source_id,
            segment_id=self._clean_text(self._value(item, "segment_id")),
            speaker_id=self._clean_text(self._value(item, "speaker_id")),
            source_text=source_text,
            supported_fields=supported_fields,
            confidence=self._float_value(self._value(item, "confidence"), default=0.0),
            created_at=created_at,
            metadata=dict(self._value(item, "metadata") or {}),
        )

    def _memory_id(self, *, memory_type: MemoryType, content: dict[str, Any]) -> str:
        if memory_type == "entity":
            basis = {
                "speaker_id": content.get("speaker_id"),
                "display_name": self._normalize(content.get("display_name")),
                "role": self._normalize(content.get("role") or content.get("suggested_role")),
            }
        elif memory_type == "responsibility":
            basis = {
                "task": self._normalize(content.get("task")),
                "owner": self._normalize(content.get("owner")),
                "responsibility_type": content.get("responsibility_type"),
            }
        else:
            basis = {
                "meeting_memory_type": content.get("meeting_memory_type"),
                "text": self._normalize(content.get("text")),
            }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return f"mem:{memory_type}:{digest}"

    def _evidence_id(
        self,
        *,
        source_type: str,
        meeting_id: str | None,
        source_id: str | None,
        source_text: str | None,
        supported_fields: list[str],
    ) -> str:
        basis = "|".join(
            [
                source_type,
                meeting_id or "",
                source_id or "",
                self._normalize(source_text),
                ",".join(sorted(supported_fields)),
            ]
        )
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
        return f"ev:{digest}"

    def _meeting_event_text(self, event: Any) -> str | None:
        for key in ("text", "content", "conclusion", "risk", "issue", "item", "task"):
            text = self._clean_text(self._value(event, key))
            if text:
                return text
        nested = self._value(event, "item")
        if isinstance(nested, dict):
            for key in ("content", "text", "conclusion", "risk", "issue", "item"):
                text = self._clean_text(nested.get(key))
                if text:
                    return text
        return None

    def _meeting_memory_type(self, event: Any) -> MeetingMemoryType:
        explicit = self._clean_text(self._value(event, "meeting_memory_type") or self._value(event, "memory_type"))
        if explicit in {
            "decision",
            "risk",
            "unresolved_issue",
            "project_fact",
            "dependency",
            "scope_change",
            "requirement_change",
        }:
            return explicit  # type: ignore[return-value]
        dimension = self._clean_text(self._value(event, "target_dimension") or self._value(event, "dimension"))
        mapping: dict[str, MeetingMemoryType] = {
            "key_conclusions": "decision",
            "risks_and_focus": "risk",
            "unresolved_issues": "unresolved_issue",
            "meeting_summary": "project_fact",
        }
        return mapping.get(dimension or "", "project_fact")

    def _matrix_rows(self, matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None) -> list[Any]:
        if matrix is None:
            return []
        rows = self._value(matrix, "rows")
        if rows is not None:
            return list(rows)
        nested = self._value(matrix, "responsibility_matrix")
        if nested is not None:
            return self._matrix_rows(nested)
        return []

    def _index_by_speaker_id(
        self,
        contexts: dict[str, RoleContext] | list[RoleContext] | None,
    ) -> dict[str, RoleContext]:
        return {
            item.speaker_id: item
            for item in self._iter_values(contexts)
        }

    @staticmethod
    def _iter_values(values: dict[str, Any] | list[Any] | None) -> list[Any]:
        if values is None:
            return []
        if isinstance(values, dict):
            return list(values.values())
        return list(values)

    @staticmethod
    def _value(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @staticmethod
    def _float_value(value: Any, *, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _bounded_max(values: list[float]) -> float:
        return max(0.0, min(1.0, max(values or [0.0])))

    @staticmethod
    def _datetime_value(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _first_datetime(evidence: list[MemoryEvidence]) -> datetime | None:
        for item in evidence:
            if item.created_at is not None:
                return item.created_at
        return None


__all__ = [
    "MemoryContext",
    "MemoryEvidence",
    "MemorySnapshot",
    "MemorySnapshotBuilder",
    "MemorySourceEvent",
    "MemoryStatus",
    "MemoryType",
]
