from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.memory_retriever import RetrievedMemoryContext, RetrievedMemoryItem
from app.reasoning_evidence_graph import EvidenceNode, ReasoningEvidenceGraph, ReasoningEvidenceGraphBuilder
from app.responsibility_evidence_matrix import ResponsibilityEvidenceMatrix, ResponsibilityEvidenceMatrixRow


ReasoningType = Literal["risk_assessment", "decision_support", "responsibility_analysis", "trend_detection"]
ReasoningSupportLevel = Literal["supports", "weakens", "conflicts", "context_only"]
EvidenceStatus = Literal[
    "confirmed",
    "active",
    "candidate",
    "needs_review",
    "shadow_only",
    "conflicted",
    "expired",
    "unknown",
]
NextStepType = Literal[
    "human_review",
    "ask_for_confirmation",
    "request_clarification",
    "prepare_action_proposal",
    "flag_for_audit",
    "monitor_in_next_meeting",
    "compare_with_prior_memory",
    "no_action",
]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    meeting_id: str | None = None
    memory_id: str | None = None
    semantic_event_id: str | None = None
    responsibility_id: str | None = None
    supported_claim_parts: list[str] = Field(default_factory=list)
    support_level: ReasoningSupportLevel
    source_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_status: EvidenceStatus = "unknown"

    @model_validator(mode="after")
    def require_claim_part_support(self) -> "EvidenceRef":
        if not self.supported_claim_parts:
            raise ValueError("reasoning evidence ref requires supported_claim_parts")
        return self


class ImpactScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    meeting_ids: list[str] = Field(default_factory=list)
    affected_entities: list[str] = Field(default_factory=list)
    affected_responsibilities: list[str] = Field(default_factory=list)
    affected_decisions: list[str] = Field(default_factory=list)
    affected_risks: list[str] = Field(default_factory=list)
    time_horizon: str = "unknown"


class SuggestedNextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_type: NextStepType
    text: str
    target_refs: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)


class ReasoningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_id: str = Field(min_length=1)
    reasoning_type: ReasoningType
    claim: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    impact_scope: ImpactScope
    requires_confirmation: bool
    suggested_next_step: SuggestedNextStep

    @model_validator(mode="after")
    def require_supporting_evidence(self) -> "ReasoningContext":
        if not self.evidence_refs:
            raise ValueError("reasoning context requires evidence")
        if not any(item.support_level == "supports" for item in self.evidence_refs):
            raise ValueError("reasoning context requires supporting evidence")
        if any(item.support_level == "conflicts" for item in self.evidence_refs) and not self.requires_confirmation:
            raise ValueError("conflicting reasoning evidence requires confirmation")
        return self


class ReasoningEngine:
    def __init__(self) -> None:
        self._graph_builder = ReasoningEvidenceGraphBuilder()

    def generate(
        self,
        *,
        evidence_graphs: list[ReasoningEvidenceGraph | dict[str, Any]] | None = None,
        retrieved_memory_context: RetrievedMemoryContext | dict[str, Any] | None = None,
        responsibility_matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None = None,
        current_meeting_context: dict[str, Any] | None = None,
    ) -> list[ReasoningContext]:
        current = current_meeting_context or {}
        candidates: list[ReasoningContext] = []

        for graph in self._graphs(evidence_graphs):
            candidate = self._candidate_from_graph(graph=graph, current=current)
            if candidate is not None:
                candidates.append(candidate)

        memories = self._memories(retrieved_memory_context)
        candidates.extend(self._risk_candidates(memories=memories, current=current))
        candidates.extend(self._decision_candidates(memories=memories, current=current))
        candidates.extend(self._responsibility_candidates(matrix=responsibility_matrix, current=current))
        candidates.extend(self._trend_candidates(memories=memories, current=current))

        return self._deduplicate(candidates)

    def _candidate_from_graph(self, *, graph: ReasoningEvidenceGraph, current: dict[str, Any]) -> ReasoningContext | None:
        claim = self._claim_text(graph)
        if not claim:
            return None
        reasoning_type = self._classify_claim(claim)
        refs = self._refs_from_graph(graph)
        return self._context(
            reasoning_type=reasoning_type,
            claim=claim,
            evidence_refs=refs,
            confidence=graph.confidence,
            current=current,
            requires_confirmation=graph.requires_confirmation or self._refs_require_confirmation(refs),
            next_step=self._next_step(reasoning_type=reasoning_type, requires_confirmation=graph.requires_confirmation),
        )

    def _risk_candidates(
        self,
        *,
        memories: list[RetrievedMemoryItem],
        current: dict[str, Any],
    ) -> list[ReasoningContext]:
        candidates: list[ReasoningContext] = []
        for memory in memories:
            content = memory.content
            text = self._clean_text(content.get("text") or content.get("risk") or content.get("issue"))
            if not text:
                continue
            if content.get("meeting_memory_type") != "risk" and not self._has_any(text, {"risk", "block", "blocked", "blocking", "unstable", "slip", "delay"}):
                continue
            refs = self._refs_from_memory(memory, supported_parts=["risk_subject", "impact_scope"])
            if not refs:
                continue
            claim = f"{text} may require risk review."
            candidates.append(
                self._context(
                    reasoning_type="risk_assessment",
                    claim=claim,
                    evidence_refs=refs,
                    confidence=self._avg_ref_confidence(refs),
                    current=current,
                    requires_confirmation=self._refs_require_confirmation(refs),
                    next_step=SuggestedNextStep(
                        step_type="human_review",
                        text="Review the cited risk evidence and confirm whether mitigation planning is needed.",
                        target_refs=[memory.memory_id],
                        blocked_actions=["change_risk_status", "notify_owner", "create_task"],
                    ),
                )
            )
        return candidates

    def _decision_candidates(
        self,
        *,
        memories: list[RetrievedMemoryItem],
        current: dict[str, Any],
    ) -> list[ReasoningContext]:
        candidates: list[ReasoningContext] = []
        for memory in memories:
            content = memory.content
            if content.get("meeting_memory_type") != "decision":
                continue
            text = self._clean_text(content.get("text"))
            if not text:
                continue
            refs = self._refs_from_memory(memory, supported_parts=["decision_signal"])
            if not refs:
                continue
            candidates.append(
                self._context(
                    reasoning_type="decision_support",
                    claim=f"Available evidence supports reviewing this decision context: {text}",
                    evidence_refs=refs,
                    confidence=self._avg_ref_confidence(refs),
                    current=current,
                    requires_confirmation=self._refs_require_confirmation(refs),
                    next_step=SuggestedNextStep(
                        step_type="human_review",
                        text="Review the decision evidence before using it as project context.",
                        target_refs=[memory.memory_id],
                        blocked_actions=["update_summary", "overwrite_decision_memory"],
                    ),
                )
            )
        return candidates

    def _responsibility_candidates(
        self,
        *,
        matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None,
        current: dict[str, Any],
    ) -> list[ReasoningContext]:
        candidates: list[ReasoningContext] = []
        for row in self._matrix_rows(matrix):
            if row.consistency_status not in {"owner_conflict", "owner_missing", "responsibility_only"}:
                continue
            refs = self._refs_from_matrix_row(row)
            if not refs:
                continue
            task = row.responsibility_candidates[0].task if row.responsibility_candidates else row.task_key
            if row.consistency_status == "owner_conflict":
                owners = ", ".join(candidate.owner for candidate in row.responsibility_candidates if candidate.owner)
                claim = f"Responsibility evidence conflicts with the action owner for {task}: action owner is {row.action_owner}, evidence owner candidate is {owners}."
            elif row.consistency_status == "owner_missing":
                owners = ", ".join(candidate.owner for candidate in row.responsibility_candidates if candidate.owner)
                claim = f"Responsibility evidence suggests {task} has an owner candidate ({owners}) while the action owner is missing."
            else:
                claim = f"Responsibility evidence exists for {task}, but no matching action item is present."
            candidates.append(
                self._context(
                    reasoning_type="responsibility_analysis",
                    claim=claim,
                    evidence_refs=refs,
                    confidence=row.confidence,
                    current=current,
                    requires_confirmation=True,
                    next_step=SuggestedNextStep(
                        step_type="ask_for_confirmation",
                        text="Ask a reviewer to confirm the responsibility evidence before any owner or task update.",
                        target_refs=[row.task_key],
                        blocked_actions=["update_task", "assign_owner", "create_task"],
                    ),
                )
            )
        return candidates

    def _trend_candidates(
        self,
        *,
        memories: list[RetrievedMemoryItem],
        current: dict[str, Any],
    ) -> list[ReasoningContext]:
        groups: dict[tuple[str, str], list[RetrievedMemoryItem]] = {}
        for memory in memories:
            text = self._clean_text(memory.content.get("text") or memory.content.get("task"))
            if not text:
                continue
            kind = self._clean_text(memory.content.get("meeting_memory_type")) or memory.memory_type
            topic = self._topic_key(text)
            if not topic:
                continue
            groups.setdefault((kind, topic), []).append(memory)

        candidates: list[ReasoningContext] = []
        for (kind, topic), items in groups.items():
            meeting_ids = {self._meeting_id_from_memory(item) for item in items}
            meeting_ids.discard(None)
            if len(items) < 2 and len(meeting_ids) < 2:
                continue
            refs = [ref for item in items for ref in self._refs_from_memory(item, supported_parts=["trend_signal"])]
            if not refs:
                continue
            claim = f"{kind} context around {topic} appears repeatedly across the available evidence."
            candidates.append(
                self._context(
                    reasoning_type="trend_detection",
                    claim=claim,
                    evidence_refs=refs,
                    confidence=min(0.95, self._avg_ref_confidence(refs) + 0.05),
                    current=current,
                    requires_confirmation=True,
                    next_step=SuggestedNextStep(
                        step_type="compare_with_prior_memory",
                        text="Compare the repeated evidence with prior memory before treating it as a project trend.",
                        target_refs=[item.memory_id for item in items],
                        blocked_actions=["change_risk_status", "close_issue", "update_task"],
                    ),
                )
            )
        return candidates

    def _context(
        self,
        *,
        reasoning_type: ReasoningType,
        claim: str,
        evidence_refs: list[EvidenceRef],
        confidence: float,
        current: dict[str, Any],
        requires_confirmation: bool,
        next_step: SuggestedNextStep,
    ) -> ReasoningContext | None:
        if not evidence_refs or not any(ref.support_level == "supports" for ref in evidence_refs):
            return None
        return ReasoningContext(
            reasoning_id=self._reasoning_id(reasoning_type=reasoning_type, claim=claim, refs=evidence_refs),
            reasoning_type=reasoning_type,
            claim=claim,
            evidence_refs=evidence_refs,
            confidence=self._float_value(confidence),
            impact_scope=self._impact_scope(current=current, refs=evidence_refs),
            requires_confirmation=requires_confirmation
            or any(ref.support_level == "conflicts" for ref in evidence_refs)
            or self._refs_require_confirmation(evidence_refs),
            suggested_next_step=next_step,
        )

    def _refs_from_graph(self, graph: ReasoningEvidenceGraph) -> list[EvidenceRef]:
        nodes = {node.node_id: node for node in graph.nodes}
        refs: list[EvidenceRef] = []
        for edge in graph.edges:
            if edge.to_node_id != graph.claim_node_id or edge.edge_type == "relates_to":
                continue
            node = nodes.get(edge.from_node_id)
            if node is None:
                continue
            refs.append(
                self._evidence_ref(
                    source_type=self._source_type_for_node(node),
                    source_id=node.source_id,
                    supported_claim_parts=["claim"],
                    support_level=edge.edge_type,
                    source_text=node.content,
                    confidence=min(node.confidence, edge.confidence),
                    evidence_status="unknown",
                )
            )
        return refs

    def _refs_from_memory(self, memory: RetrievedMemoryItem, *, supported_parts: list[str]) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []
        for evidence in memory.evidence:
            source_id = self._clean_text(evidence.get("source_id") or evidence.get("evidence_id") or memory.memory_id)
            if not source_id:
                continue
            refs.append(
                self._evidence_ref(
                    source_type=self._clean_text(evidence.get("source_type")) or "memory_context",
                    source_id=source_id,
                    meeting_id=self._clean_text(evidence.get("meeting_id")),
                    memory_id=memory.memory_id,
                    supported_claim_parts=supported_parts,
                    support_level="supports",
                    source_text=self._clean_text(evidence.get("source_text")),
                    confidence=self._float_value(evidence.get("confidence")),
                    evidence_status=self._status_from_memory(memory),
                )
            )
        return refs

    def _refs_from_matrix_row(self, row: ResponsibilityEvidenceMatrixRow) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []
        support_level: ReasoningSupportLevel = "conflicts" if row.consistency_status == "owner_conflict" else "supports"
        for evidence in row.evidence:
            source_id = self._clean_text(evidence.segment_id or getattr(evidence, "event_id", None) or row.task_key) or row.task_key
            refs.append(
                self._evidence_ref(
                    source_type=evidence.source_type,
                    source_id=source_id,
                    meeting_id=evidence.meeting_id,
                    responsibility_id=row.task_key,
                    supported_claim_parts=["task", "owner"],
                    support_level=support_level,
                    source_text=evidence.source_text,
                    confidence=evidence.confidence,
                    evidence_status="shadow_only" if evidence.source_type == "semantic_event" else "unknown",
                )
            )
        if row.consistency_status == "owner_conflict" and row.action_owner:
            refs.append(
                self._evidence_ref(
                    source_type="responsibility_matrix",
                    source_id=row.task_key,
                    responsibility_id=row.task_key,
                    supported_claim_parts=["action_owner"],
                    support_level="supports",
                    source_text=f"Existing action owner: {row.action_owner}",
                    confidence=row.confidence,
                    evidence_status="unknown",
                )
            )
        return refs

    def _evidence_ref(
        self,
        *,
        source_type: str,
        source_id: str,
        supported_claim_parts: list[str],
        support_level: ReasoningSupportLevel,
        confidence: float,
        meeting_id: str | None = None,
        memory_id: str | None = None,
        semantic_event_id: str | None = None,
        responsibility_id: str | None = None,
        source_text: str | None = None,
        evidence_status: EvidenceStatus = "unknown",
    ) -> EvidenceRef:
        basis = {
            "source_type": source_type,
            "source_id": source_id,
            "memory_id": memory_id,
            "responsibility_id": responsibility_id,
            "support_level": support_level,
            "parts": supported_claim_parts,
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return EvidenceRef(
            evidence_ref_id=f"eref:{digest}",
            source_type=source_type,
            source_id=source_id,
            meeting_id=meeting_id,
            memory_id=memory_id,
            semantic_event_id=semantic_event_id,
            responsibility_id=responsibility_id,
            supported_claim_parts=supported_claim_parts,
            support_level=support_level,
            source_text=source_text,
            confidence=self._float_value(confidence),
            evidence_status=evidence_status,
        )

    def _graphs(self, graphs: list[ReasoningEvidenceGraph | dict[str, Any]] | None) -> list[ReasoningEvidenceGraph]:
        return [item if isinstance(item, ReasoningEvidenceGraph) else ReasoningEvidenceGraph.model_validate(item) for item in graphs or []]

    def _memories(self, context: RetrievedMemoryContext | dict[str, Any] | None) -> list[RetrievedMemoryItem]:
        if context is None:
            return []
        retrieved = context if isinstance(context, RetrievedMemoryContext) else RetrievedMemoryContext.model_validate(context)
        return retrieved.memories

    def _matrix_rows(self, matrix: ResponsibilityEvidenceMatrix | dict[str, Any] | None) -> list[ResponsibilityEvidenceMatrixRow]:
        if matrix is None:
            return []
        resolved = matrix if isinstance(matrix, ResponsibilityEvidenceMatrix) else ResponsibilityEvidenceMatrix.model_validate(matrix)
        return resolved.rows

    def _claim_text(self, graph: ReasoningEvidenceGraph) -> str | None:
        for node in graph.nodes:
            if node.node_id == graph.claim_node_id:
                return self._clean_text(node.content)
        return None

    def _classify_claim(self, claim: str) -> ReasoningType:
        text = claim.lower()
        if self._has_any(text, {"owner", "responsib", "assign"}):
            return "responsibility_analysis"
        if self._has_any(text, {"decision", "decided", "approved", "reject"}):
            return "decision_support"
        if self._has_any(text, {"repeat", "trend", "again", "recurring"}):
            return "trend_detection"
        return "risk_assessment"

    def _source_type_for_node(self, node: EvidenceNode) -> str:
        mapping = {
            "evidence": "reasoning_evidence_graph",
            "memory": "memory_context",
            "responsibility": "responsibility_context",
            "claim": "reasoning_claim",
        }
        return mapping[node.node_type]

    def _impact_scope(self, *, current: dict[str, Any], refs: list[EvidenceRef]) -> ImpactScope:
        meeting_ids = [item for item in [self._clean_text(current.get("meeting_id")), *(ref.meeting_id for ref in refs)] if item]
        return ImpactScope(
            project_id=self._clean_text(current.get("project_id")),
            meeting_ids=self._unique(meeting_ids),
            affected_entities=self._string_list(current.get("participants")),
            affected_responsibilities=self._unique([ref.responsibility_id for ref in refs if ref.responsibility_id]),
            affected_decisions=self._unique([ref.memory_id for ref in refs if ref.memory_id and "decision" in ref.memory_id]),
            affected_risks=self._unique([ref.memory_id for ref in refs if ref.memory_id and "risk" in ref.memory_id]),
            time_horizon=self._clean_text(current.get("time_horizon")) or "near_term",
        )

    def _next_step(self, *, reasoning_type: ReasoningType, requires_confirmation: bool) -> SuggestedNextStep:
        if reasoning_type == "decision_support":
            return SuggestedNextStep(
                step_type="human_review" if requires_confirmation else "flag_for_audit",
                text="Review the cited decision evidence before using it as project context.",
                blocked_actions=["update_summary", "overwrite_decision_memory"],
            )
        if reasoning_type == "responsibility_analysis":
            return SuggestedNextStep(
                step_type="ask_for_confirmation",
                text="Confirm the responsibility evidence before any owner or task update.",
                blocked_actions=["update_task", "assign_owner", "create_task"],
            )
        if reasoning_type == "trend_detection":
            return SuggestedNextStep(
                step_type="compare_with_prior_memory",
                text="Compare repeated evidence before treating it as a trend.",
                blocked_actions=["change_risk_status", "close_issue", "update_task"],
            )
        return SuggestedNextStep(
            step_type="human_review" if requires_confirmation else "flag_for_audit",
            text="Review the cited risk evidence before changing any risk or task state.",
            blocked_actions=["change_risk_status", "notify_owner", "create_task"],
        )

    def _status_from_memory(self, memory: RetrievedMemoryItem) -> EvidenceStatus:
        status = self._clean_text(memory.content.get("status") or memory.content.get("effective_status"))
        if status in {"confirmed", "active", "candidate", "needs_review", "conflicted", "expired"}:
            return status  # type: ignore[return-value]
        return "unknown"

    def _refs_require_confirmation(self, refs: list[EvidenceRef]) -> bool:
        review_statuses = {"candidate", "needs_review", "shadow_only", "conflicted", "expired", "unknown"}
        return any(ref.evidence_status in review_statuses or ref.confidence < 0.75 for ref in refs)

    def _meeting_id_from_memory(self, memory: RetrievedMemoryItem) -> str | None:
        for evidence in memory.evidence:
            meeting_id = self._clean_text(evidence.get("meeting_id"))
            if meeting_id:
                return meeting_id
        return None

    def _topic_key(self, text: str) -> str | None:
        words = [word for word in re.findall(r"[a-z0-9_]{3,}", text.lower()) if word not in {"the", "and", "for", "with", "that", "this", "risk", "issue"}]
        if words:
            return " ".join(words[:4])
        cjk = re.findall(r"[\u4e00-\u9fff]", text)
        return "".join(cjk[:8]) if cjk else None

    def _reasoning_id(self, *, reasoning_type: ReasoningType, claim: str, refs: list[EvidenceRef]) -> str:
        basis = {
            "type": reasoning_type,
            "claim": self._normalize(claim),
            "refs": [ref.evidence_ref_id for ref in refs],
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return f"reason:{reasoning_type}:{digest}"

    def _deduplicate(self, candidates: list[ReasoningContext]) -> list[ReasoningContext]:
        by_id: dict[str, ReasoningContext] = {}
        for candidate in candidates:
            existing = by_id.get(candidate.reasoning_id)
            if existing is None or candidate.confidence > existing.confidence:
                by_id[candidate.reasoning_id] = candidate
        return list(by_id.values())

    @staticmethod
    def _avg_ref_confidence(refs: list[EvidenceRef]) -> float:
        if not refs:
            return 0.0
        return max(0.0, min(1.0, sum(ref.confidence for ref in refs) / len(refs)))

    @staticmethod
    def _has_any(text: str, terms: set[str]) -> bool:
        normalized = text.lower()
        return any(term in normalized for term in terms)

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
    def _unique(values: list[str | None]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _float_value(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, parsed))


__all__ = [
    "EvidenceRef",
    "ImpactScope",
    "ReasoningContext",
    "ReasoningEngine",
    "ReasoningType",
    "SuggestedNextStep",
]
