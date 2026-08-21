from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.memory_snapshot_builder import MemoryContext, MemoryEvidence, MemorySnapshot, MemoryStatus, MemoryType


RetrievedMemoryEvidence = dict[str, Any]
NOISE_TERMS = {
    "active",
    "candidate",
    "confirmed",
    "current",
    "effective_status",
    "meeting",
    "meeting_id",
    "meeting_memory_type",
    "memory",
    "project_fact",
    "status",
    "summary",
    "text",
    "title",
}


class CurrentMeetingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: str | None = None
    meeting_type: str | None = None
    title: str | None = None
    agenda: list[str] = Field(default_factory=list)
    summary: str | None = None
    transcript_excerpt: str | None = None
    focus_terms: list[str] = Field(default_factory=list)


class RetrievedMemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    memory_type: MemoryType
    content: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = Field(ge=0.0, le=1.0)
    evidence: list[RetrievedMemoryEvidence] = Field(default_factory=list)
    token_cost: int = Field(ge=0)


class RetrievedMemoryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    source_snapshot_as_of: datetime | None = None
    current_meeting_id: str | None = None
    retrieved_at: datetime
    token_budget: int
    token_cost: int
    memories: list[RetrievedMemoryItem] = Field(default_factory=list)


class MemoryRetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_types: set[MemoryType] | None = None
    allowed_statuses: set[MemoryStatus] = Field(default_factory=lambda: {"active", "confirmed", "candidate"})
    min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    min_relevance_score: float = Field(default=0.12, ge=0.0, le=1.0)
    token_budget: int = Field(default=1200, ge=0)
    max_evidence_items: int = Field(default=2, ge=0)
    max_evidence_chars: int = Field(default=160, ge=0)


class MemoryRetriever:
    def retrieve(
        self,
        *,
        snapshot: MemorySnapshot,
        current_context: CurrentMeetingContext | dict[str, Any] | str,
        policy: MemoryRetrievalPolicy | None = None,
        retrieved_at: datetime | None = None,
    ) -> RetrievedMemoryContext:
        resolved_policy = policy or MemoryRetrievalPolicy()
        resolved_retrieved_at = retrieved_at or datetime.now(UTC)
        context = self._context_text(current_context)
        query_terms = self._terms(context)
        scored: list[tuple[float, MemoryContext, list[RetrievedMemoryEvidence], int]] = []

        for memory in snapshot.memories:
            if not self._passes_filters(memory, resolved_policy):
                continue
            relevance_score = self._relevance(memory, query_terms=query_terms)
            if query_terms and relevance_score < resolved_policy.min_relevance_score:
                continue
            evidence = self._compress_evidence(memory.evidence, policy=resolved_policy)
            if not evidence:
                continue
            token_cost = self._token_cost(memory.content, evidence)
            scored.append((relevance_score, memory, evidence, token_cost))

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].confidence,
                self._status_weight(item[1].status),
                item[1].created_at,
            ),
            reverse=True,
        )

        selected: list[RetrievedMemoryItem] = []
        total_cost = 0
        for relevance_score, memory, evidence, token_cost in scored:
            if total_cost + token_cost > resolved_policy.token_budget:
                continue
            selected.append(
                RetrievedMemoryItem(
                    memory_id=memory.memory_id,
                    memory_type=memory.memory_type,
                    content=memory.content,
                    relevance_score=round(relevance_score, 4),
                    evidence=evidence,
                    token_cost=token_cost,
                )
            )
            total_cost += token_cost

        return RetrievedMemoryContext(
            as_of=resolved_retrieved_at,
            source_snapshot_as_of=snapshot.as_of,
            current_meeting_id=self._context_meeting_id(current_context),
            retrieved_at=resolved_retrieved_at,
            token_budget=resolved_policy.token_budget,
            token_cost=total_cost,
            memories=selected,
        )

    def _passes_filters(self, memory: MemoryContext, policy: MemoryRetrievalPolicy) -> bool:
        if policy.memory_types is not None and memory.memory_type not in policy.memory_types:
            return False
        if memory.status not in policy.allowed_statuses:
            return False
        if memory.confidence < policy.min_confidence:
            return False
        if not memory.evidence:
            return False
        return True

    def _relevance(self, memory: MemoryContext, *, query_terms: set[str]) -> float:
        if not query_terms:
            return min(1.0, 0.45 + memory.confidence * 0.45 + self._status_weight(memory.status) * 0.1)
        content_terms = self._terms(self._text_values(memory.content))
        evidence_terms = self._terms(" ".join(item.source_text or "" for item in memory.evidence))
        content_overlap = self._overlap_ratio(query_terms, content_terms)
        evidence_overlap = self._overlap_ratio(query_terms, evidence_terms)
        lexical_score = content_overlap * 0.7 + evidence_overlap * 0.3
        if lexical_score == 0.0:
            return 0.0
        raw_score = (
            content_overlap * 0.55
            + evidence_overlap * 0.25
            + memory.confidence * 0.15
            + self._status_weight(memory.status) * 0.05
        )
        return max(0.0, min(1.0, raw_score))

    def _compress_evidence(
        self,
        evidence: list[MemoryEvidence],
        *,
        policy: MemoryRetrievalPolicy,
    ) -> list[RetrievedMemoryEvidence]:
        compressed: list[RetrievedMemoryEvidence] = []
        for item in sorted(evidence, key=lambda value: value.confidence, reverse=True)[: policy.max_evidence_items]:
            compressed_item: RetrievedMemoryEvidence = {
                "evidence_id": item.evidence_id,
                "source_type": item.source_type,
                "meeting_id": item.meeting_id,
                "source_id": item.source_id,
                "segment_id": item.segment_id,
                "supported_fields": item.supported_fields,
                "confidence": item.confidence,
            }
            source_text = self._truncate(item.source_text, policy.max_evidence_chars)
            if source_text:
                compressed_item["source_text"] = source_text
            compressed.append({key: value for key, value in compressed_item.items() if value not in (None, [], {})})
        return compressed

    def _token_cost(self, content: dict[str, Any], evidence: list[RetrievedMemoryEvidence]) -> int:
        payload = json.dumps({"content": content, "evidence": evidence}, ensure_ascii=False, sort_keys=True)
        return max(1, math.ceil(len(payload) / 4))

    def _context_text(self, current_context: CurrentMeetingContext | dict[str, Any] | str) -> str:
        if isinstance(current_context, str):
            return current_context
        if isinstance(current_context, CurrentMeetingContext):
            values = current_context.model_dump()
        else:
            values = current_context
        return self._text_values(values)

    def _context_meeting_id(self, current_context: CurrentMeetingContext | dict[str, Any] | str) -> str | None:
        if isinstance(current_context, str):
            return None
        if isinstance(current_context, CurrentMeetingContext):
            return current_context.meeting_id
        value = current_context.get("meeting_id")
        return str(value) if value else None

    def _terms(self, text: str) -> set[str]:
        normalized = text.lower()
        terms = set(re.findall(r"[a-z0-9_]{2,}", normalized))
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
        terms.update(cjk_chars)
        terms.update("".join(pair) for pair in zip(cjk_chars, cjk_chars[1:]))
        return {term for term in terms if term not in NOISE_TERMS}

    def _text_values(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            return " ".join(self._text_values(item) for item in value.values())
        if isinstance(value, list | tuple | set):
            return " ".join(self._text_values(item) for item in value)
        return str(value)

    @staticmethod
    def _overlap_ratio(query_terms: set[str], candidate_terms: set[str]) -> float:
        if not query_terms or not candidate_terms:
            return 0.0
        return len(query_terms & candidate_terms) / len(query_terms)

    @staticmethod
    def _status_weight(status: MemoryStatus) -> float:
        weights: dict[MemoryStatus, float] = {
            "confirmed": 1.0,
            "active": 0.9,
            "candidate": 0.65,
            "needs_review": 0.45,
            "conflicted": 0.35,
            "superseded": 0.2,
            "expired": 0.1,
            "rejected": 0.0,
        }
        return weights.get(status, 0.0)

    @staticmethod
    def _truncate(value: str | None, max_chars: int) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."


__all__ = [
    "CurrentMeetingContext",
    "MemoryRetrievalPolicy",
    "MemoryRetriever",
    "RetrievedMemoryContext",
    "RetrievedMemoryItem",
]
