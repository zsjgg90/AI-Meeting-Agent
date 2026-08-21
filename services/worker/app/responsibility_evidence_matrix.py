from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.responsibility_extractor import ResponsibilityContext, ResponsibilityEvidence, ResponsibilityType


ConsistencyStatus = Literal[
    "confirmed_match",
    "owner_missing",
    "owner_conflict",
    "responsibility_only",
    "unknown",
]


class ResponsibilityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsibility_id: str
    responsibility_type: ResponsibilityType
    task: str
    owner: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool = False


class ResponsibilityEvidenceMatrixRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str
    action_owner: str | None = None
    responsibility_candidates: list[ResponsibilityCandidate] = Field(default_factory=list)
    evidence: list[ResponsibilityEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    consistency_status: ConsistencyStatus


class ResponsibilityEvidenceMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ResponsibilityEvidenceMatrixRow] = Field(default_factory=list)


class ResponsibilityEvidenceMatrixBuilder:
    def build(
        self,
        *,
        action_items: list[Any],
        responsibility_contexts: list[ResponsibilityContext],
    ) -> ResponsibilityEvidenceMatrix:
        rows: list[ResponsibilityEvidenceMatrixRow] = []
        matched_context_ids: set[str] = set()

        contexts_by_task = self._contexts_by_task(responsibility_contexts)
        contexts_by_segment = self._contexts_by_segment(responsibility_contexts)

        for action_item in action_items:
            action_task = self._action_task(action_item)
            action_owner = self._clean_text(
                self._value(action_item, "owner_name")
                or self._value(action_item, "owner")
            )
            matched_contexts = self._matching_contexts(
                action_item=action_item,
                action_task=action_task,
                contexts_by_task=contexts_by_task,
                contexts_by_segment=contexts_by_segment,
            )
            matched_context_ids.update(context.responsibility_id for context in matched_contexts)
            rows.append(
                self._row(
                    task_key=self._task_key(action_task),
                    action_owner=action_owner,
                    contexts=matched_contexts,
                    fallback_confidence=self._confidence(action_item),
                    no_action=False,
                )
            )

        for context in responsibility_contexts:
            if context.responsibility_id in matched_context_ids:
                continue
            rows.append(
                self._row(
                    task_key=self._task_key(context.task),
                    action_owner=None,
                    contexts=[context],
                    fallback_confidence=0.0,
                    no_action=True,
                )
            )

        return ResponsibilityEvidenceMatrix(rows=rows)

    def _row(
        self,
        *,
        task_key: str,
        action_owner: str | None,
        contexts: list[ResponsibilityContext],
        fallback_confidence: float,
        no_action: bool,
    ) -> ResponsibilityEvidenceMatrixRow:
        candidates = [self._candidate(context) for context in contexts]
        evidence = [item for context in contexts for item in context.evidence]
        confidence = max([context.confidence for context in contexts] or [fallback_confidence])
        status = self._status(action_owner=action_owner, contexts=contexts, no_action=no_action)
        return ResponsibilityEvidenceMatrixRow(
            task_key=task_key,
            action_owner=action_owner,
            responsibility_candidates=candidates,
            evidence=evidence,
            confidence=confidence,
            consistency_status=status,
        )

    def _status(
        self,
        *,
        action_owner: str | None,
        contexts: list[ResponsibilityContext],
        no_action: bool,
    ) -> ConsistencyStatus:
        candidate_owners = [context.owner for context in contexts if context.owner]
        if no_action:
            return "responsibility_only" if candidate_owners else "unknown"
        if not contexts or not candidate_owners:
            return "unknown"
        if not action_owner:
            return "owner_missing"
        normalized_action_owner = self._normalize(action_owner)
        if any(self._normalize(owner) == normalized_action_owner for owner in candidate_owners):
            return "confirmed_match"
        return "owner_conflict"

    def _matching_contexts(
        self,
        *,
        action_item: Any,
        action_task: str,
        contexts_by_task: dict[str, list[ResponsibilityContext]],
        contexts_by_segment: dict[str, list[ResponsibilityContext]],
    ) -> list[ResponsibilityContext]:
        matched: dict[str, ResponsibilityContext] = {}
        source_segment_id = self._clean_text(self._value(action_item, "source_segment_id"))
        if source_segment_id:
            for context in contexts_by_segment.get(source_segment_id, []):
                matched[context.responsibility_id] = context
        for context in contexts_by_task.get(self._normalize(action_task), []):
            matched[context.responsibility_id] = context
        return list(matched.values())

    def _contexts_by_task(self, contexts: list[ResponsibilityContext]) -> dict[str, list[ResponsibilityContext]]:
        by_task: dict[str, list[ResponsibilityContext]] = {}
        for context in contexts:
            by_task.setdefault(self._normalize(context.task), []).append(context)
        return by_task

    def _contexts_by_segment(self, contexts: list[ResponsibilityContext]) -> dict[str, list[ResponsibilityContext]]:
        by_segment: dict[str, list[ResponsibilityContext]] = {}
        for context in contexts:
            for evidence in context.evidence:
                if evidence.segment_id:
                    by_segment.setdefault(evidence.segment_id, []).append(context)
        return by_segment

    def _candidate(self, context: ResponsibilityContext) -> ResponsibilityCandidate:
        return ResponsibilityCandidate(
            responsibility_id=context.responsibility_id,
            responsibility_type=context.responsibility_type,
            task=context.task,
            owner=context.owner,
            confidence=context.confidence,
            requires_confirmation=any(item.requires_confirmation for item in context.evidence),
        )

    def _action_task(self, action_item: Any) -> str:
        return (
            self._clean_text(self._value(action_item, "task"))
            or self._clean_text(self._value(action_item, "content"))
            or self._clean_text(self._value(action_item, "title"))
            or "unknown task"
        )

    def _confidence(self, action_item: Any) -> float:
        try:
            value = float(self._value(action_item, "confidence"))
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, value))

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
    def _normalize(value: str | None) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", " ", text)

    def _task_key(self, task: str) -> str:
        normalized = self._normalize(task)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        return f"task:{digest}"


__all__ = [
    "ConsistencyStatus",
    "ResponsibilityCandidate",
    "ResponsibilityEvidenceMatrix",
    "ResponsibilityEvidenceMatrixBuilder",
    "ResponsibilityEvidenceMatrixRow",
]
