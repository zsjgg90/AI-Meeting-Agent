from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EvidenceNodeType = Literal["evidence", "memory", "responsibility", "claim"]
EvidenceEdgeType = Literal["supports", "weakens", "conflicts", "relates_to"]


class EvidenceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    node_type: EvidenceNodeType
    source_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node_id: str = Field(min_length=1)
    to_node_id: str = Field(min_length=1)
    edge_type: EvidenceEdgeType
    confidence: float = Field(ge=0.0, le=1.0)


class ReasoningEvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: str = Field(min_length=1)
    claim_node_id: str = Field(min_length=1)
    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_confirmation: bool
    confirmation_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_claim_with_supporting_evidence(self) -> "ReasoningEvidenceGraph":
        node_ids = {node.node_id for node in self.nodes}
        if self.claim_node_id not in node_ids:
            raise ValueError("reasoning evidence graph requires a claim node")
        if not any(edge.to_node_id == self.claim_node_id and edge.edge_type == "supports" for edge in self.edges):
            raise ValueError("reasoning claim requires supporting evidence")
        for edge in self.edges:
            if edge.from_node_id not in node_ids or edge.to_node_id not in node_ids:
                raise ValueError("reasoning evidence edge references unknown node")
        return self


class ReasoningEvidenceGraphBuilder:
    def build_claim_graph(
        self,
        *,
        claim: str,
        supporting_nodes: list[EvidenceNode | dict[str, Any]] | None = None,
        weakening_nodes: list[EvidenceNode | dict[str, Any]] | None = None,
        conflicting_nodes: list[EvidenceNode | dict[str, Any]] | None = None,
        related_nodes: list[EvidenceNode | dict[str, Any]] | None = None,
        claim_source_id: str = "reasoning_claim",
        claim_confidence: float | None = None,
    ) -> ReasoningEvidenceGraph | None:
        clean_claim = self._clean_text(claim)
        supports = self._nodes(supporting_nodes)
        if not clean_claim or not supports:
            return None

        weakens = self._nodes(weakening_nodes)
        conflicts = self._nodes(conflicting_nodes)
        related = self._nodes(related_nodes)
        base_confidence = self._claim_confidence(
            supports=supports,
            weakens=weakens,
            conflicts=conflicts,
            explicit=claim_confidence,
        )
        claim_node = EvidenceNode(
            node_id=self._node_id(
                node_type="claim",
                source_id=claim_source_id,
                content=clean_claim,
            ),
            node_type="claim",
            source_id=claim_source_id,
            content=clean_claim,
            confidence=base_confidence,
        )

        nodes = self._deduplicate([claim_node, *supports, *weakens, *conflicts, *related])
        edges = [
            *self._edges(from_nodes=supports, claim_node=claim_node, edge_type="supports"),
            *self._edges(from_nodes=weakens, claim_node=claim_node, edge_type="weakens"),
            *self._edges(from_nodes=conflicts, claim_node=claim_node, edge_type="conflicts"),
            *self._edges(from_nodes=related, claim_node=claim_node, edge_type="relates_to"),
        ]
        confirmation_reasons = self._confirmation_reasons(
            supports=supports,
            weakens=weakens,
            conflicts=conflicts,
        )
        return ReasoningEvidenceGraph(
            graph_id=self._graph_id(claim_node=claim_node, edges=edges),
            claim_node_id=claim_node.node_id,
            nodes=nodes,
            edges=edges,
            confidence=base_confidence,
            requires_confirmation=bool(confirmation_reasons),
            confirmation_reasons=confirmation_reasons,
        )

    def node(
        self,
        *,
        node_type: EvidenceNodeType,
        source_id: str,
        content: str,
        confidence: float,
    ) -> EvidenceNode:
        return EvidenceNode(
            node_id=self._node_id(
                node_type=node_type,
                source_id=source_id,
                content=content,
            ),
            node_type=node_type,
            source_id=source_id,
            content=content.strip(),
            confidence=self._float_value(confidence),
        )

    def _nodes(self, values: list[EvidenceNode | dict[str, Any]] | None) -> list[EvidenceNode]:
        return [self._node(value) for value in values or []]

    def _node(self, value: EvidenceNode | dict[str, Any]) -> EvidenceNode:
        if isinstance(value, EvidenceNode):
            return value
        node_type = value.get("node_type")
        source_id = self._clean_text(value.get("source_id"))
        content = self._clean_text(value.get("content"))
        if not node_type or not source_id or not content:
            raise ValueError("evidence node requires node_type, source_id, and content")
        return EvidenceNode(
            node_id=self._clean_text(value.get("node_id"))
            or self._node_id(node_type=node_type, source_id=source_id, content=content),
            node_type=node_type,
            source_id=source_id,
            content=content,
            confidence=self._float_value(value.get("confidence")),
        )

    def _edges(
        self,
        *,
        from_nodes: list[EvidenceNode],
        claim_node: EvidenceNode,
        edge_type: EvidenceEdgeType,
    ) -> list[EvidenceEdge]:
        return [
            EvidenceEdge(
                from_node_id=node.node_id,
                to_node_id=claim_node.node_id,
                edge_type=edge_type,
                confidence=node.confidence,
            )
            for node in from_nodes
        ]

    def _claim_confidence(
        self,
        *,
        supports: list[EvidenceNode],
        weakens: list[EvidenceNode],
        conflicts: list[EvidenceNode],
        explicit: float | None,
    ) -> float:
        if explicit is not None:
            return self._float_value(explicit)
        support_score = sum(node.confidence for node in supports) / len(supports)
        weaken_penalty = sum(node.confidence for node in weakens) * 0.12
        conflict_penalty = sum(node.confidence for node in conflicts) * 0.24
        multi_evidence_bonus = min(0.08, max(0, len(supports) - 1) * 0.04)
        return self._float_value(support_score + multi_evidence_bonus - weaken_penalty - conflict_penalty)

    def _confirmation_reasons(
        self,
        *,
        supports: list[EvidenceNode],
        weakens: list[EvidenceNode],
        conflicts: list[EvidenceNode],
    ) -> list[str]:
        reasons: list[str] = []
        if conflicts:
            reasons.append("conflicting_evidence")
        if weakens:
            reasons.append("weakening_evidence")
        if any(node.node_type in {"memory", "responsibility"} and node.confidence < 0.75 for node in supports):
            reasons.append("reviewable_context_evidence")
        return reasons

    def _deduplicate(self, nodes: list[EvidenceNode]) -> list[EvidenceNode]:
        by_id: dict[str, EvidenceNode] = {}
        for node in nodes:
            existing = by_id.get(node.node_id)
            if existing is None or node.confidence > existing.confidence:
                by_id[node.node_id] = node
        return list(by_id.values())

    def _graph_id(self, *, claim_node: EvidenceNode, edges: list[EvidenceEdge]) -> str:
        basis = {
            "claim_node_id": claim_node.node_id,
            "edges": [
                {
                    "from": edge.from_node_id,
                    "to": edge.to_node_id,
                    "type": edge.edge_type,
                }
                for edge in edges
            ],
        }
        digest = hashlib.sha1(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
        return f"reg:{digest}"

    def _node_id(self, *, node_type: str, source_id: str, content: str) -> str:
        basis = "|".join([node_type, source_id, self._normalize(content)])
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
        return f"eg:{node_type}:{digest}"

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").strip().lower()
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def _float_value(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, parsed))


__all__ = [
    "EvidenceEdge",
    "EvidenceEdgeType",
    "EvidenceNode",
    "EvidenceNodeType",
    "ReasoningEvidenceGraph",
    "ReasoningEvidenceGraphBuilder",
]
