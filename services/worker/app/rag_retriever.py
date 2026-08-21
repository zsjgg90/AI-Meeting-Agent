from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.rag_meeting_type_router import route_rag_meeting_type


_CURRENT_FILE = Path(__file__).resolve()

if os.getenv("MEETMIND_PROJECT_ROOT"):
    PROJECT_ROOT = Path(
        os.environ["MEETMIND_PROJECT_ROOT"]
    ).resolve()
elif _CURRENT_FILE.as_posix().startswith("/app/"):
    PROJECT_ROOT = Path("/app")
else:
    PROJECT_ROOT = _CURRENT_FILE.parents[3]

DEFAULT_DB_DIR = PROJECT_ROOT / "data" / "vector_db"

V3_DIMENSION_ROUTES: dict[str, list[str]] = {
    "action": [
        "action_items",
        "cross_dimension",
        "evidence",
    ],
    "action_items": [
        "action_items",
        "cross_dimension",
        "evidence",
    ],
    "decision": [
        "key_conclusions",
        "cross_dimension",
        "evidence",
    ],
    "key_conclusions": [
        "key_conclusions",
        "cross_dimension",
        "evidence",
    ],
    "unresolved": [
        "unresolved_issues",
        "cross_dimension",
        "evidence",
    ],
    "unresolved_issues": [
        "unresolved_issues",
        "cross_dimension",
        "evidence",
    ],
    "risk": [
        "risks_and_focus",
        "cross_dimension",
        "evidence",
    ],
    "risks_and_focus": [
        "risks_and_focus",
        "cross_dimension",
        "evidence",
    ],
}

V3_VECTOR_RETRIEVAL_POOLS = [
    "dynamic_boundary",
    "scenario_example",
    "reasoning_pattern",
]

MEETING_SCENARIO_ALIASES = {
    "cross_department": "cross_team_coordination",
    "incident_review": "technical_incident",
}


@dataclass(frozen=True)
class RagContext:
    text: str
    chunks: list[dict]
    chunk_ids: list[str]
    collection_name: str
    embedding_model: str
    dataset_version: str
    chunk_schema_version: str
    retrieved_chunk_ids: list[str] = field(
        default_factory=list
    )
    retrieval_version: str | None = None
    scenario_taxonomy_version: str | None = None

    retrieval_strategy: str = "legacy_top_k"
    retrieval_buckets: dict[str, list[str]] = field(
        default_factory=dict
    )
    retrieval_trace: dict[str, Any] = field(
        default_factory=dict
    )
    routed_meeting_type: str | None = None
    routed_scenario: str | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[dict]
    strategy: str
    buckets: dict[str, list[str]]
    trace: dict[str, Any] = field(
        default_factory=dict
    )
    routed_meeting_type: str | None = None
    routed_scenario: str | None = None
    fallback_reason: str | None = None


def _normalize(value: object) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).strip().split()
    )


def _parse_csv_values(value: str) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def build_context_text(
    chunks: list[dict],
    *,
    max_chars: int | None = None,
) -> str:
    context_parts: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        distance = chunk.get("distance")

        if distance is None:
            distance_text = "fixed"
        else:
            distance_text = str(distance)

        retrieval_bucket = _normalize(
            chunk.get("retrieval_bucket")
        )

        bucket_line = (
            f"\n召回分组：{retrieval_bucket}"
            if retrieval_bucket
            else ""
        )

        context_parts.append(
            (
                f"【RAG规则 {index}】\n"
                f"标题：{chunk.get('title', '')}\n"
                f"章节：{chunk.get('section', '')}\n"
                f"知识类型："
                f"{chunk.get('knowledge_type', '')}\n"
                f"距离：{distance_text}"
                f"{bucket_line}\n\n"
                f"{chunk.get('content', '')}"
            ).strip()
        )

    context = "\n\n".join(context_parts)

    if max_chars is not None and max_chars > 0:
        return context[:max_chars]

    return context


class RagRetriever:
    def __init__(
        self,
        db_dir: Path | str | None = None,
        collection_name: str | None = None,
        embedding_model_name: str | None = None,
        distance_threshold: float | None = None,
        max_context_chars: int | None = None,
    ):
        settings = get_settings()

        configured_db_dir = (
            db_dir
            or settings.rag_chroma_db_dir
            or DEFAULT_DB_DIR
        )

        self.db_dir = Path(configured_db_dir)

        self.collection_name = (
            collection_name
            or settings.rag_collection_name
        )

        self.embedding_model_name = (
            embedding_model_name
            or settings.rag_embedding_model
        )

        self.distance_threshold = (
            settings.rag_distance_threshold
            if distance_threshold is None
            else distance_threshold
        )

        self.max_context_chars = (
            settings.rag_max_context_chars
            if max_context_chars is None
            else max_context_chars
        )

        self.dataset_version = (
            settings.rag_dataset_version
        )

        self.chunk_schema_version = (
            settings.rag_chunk_schema_version
        )

        self.scenario_taxonomy_version = (
            settings.rag_scenario_taxonomy_version
        )

        self.retrieval_version = (
            settings.rag_retrieval_version
        )

        self.v3_retrieval_enabled = (
            settings.rag_v3_retrieval_enabled
        )

        self.v3_final_k = (
            settings.rag_v3_final_k
        )

        self.v3_fixed_policy_k = (
            settings.rag_v3_fixed_policy_k
        )

        self.v3_vector_candidate_multiplier = (
            settings.rag_v3_vector_candidate_multiplier
        )

        self.v3_scenario_boost = (
            settings.rag_v3_scenario_boost
        )

        self.v3_global_scenario_boost = (
            settings.rag_v3_global_scenario_boost
        )

        self.v3_meeting_scenario_min_confidence = (
            settings.rag_v3_meeting_scenario_min_confidence
        )

        self.reranker_enabled = (
            settings.rag_reranker_enabled
        )

        self.layered_retrieval_enabled = (
            settings.rag_layered_retrieval_enabled
        )

        self.layered_fallback_enabled = (
            settings.rag_layered_fallback_enabled
        )

        self.global_fixed_ids = _parse_csv_values(
            settings.rag_layered_global_fixed_ids
        )

        self.layered_policy_k = (
            settings.rag_layered_policy_k
        )

        self.layered_dynamic_k = (
            settings.rag_layered_dynamic_k
        )

        self.layered_scenario_k = (
            settings.rag_layered_scenario_k
        )

        self.layered_query_transcript_chars = (
            settings.rag_layered_query_transcript_chars
        )

        print(
            "[RAG] Loading embedding model..."
            f" local_files_only="
            f"{settings.rag_embedding_local_files_only}"
        )

        self.embedding_model = SentenceTransformer(
            self.embedding_model_name,
            local_files_only=(
                settings.rag_embedding_local_files_only
            ),
        )

        print("[RAG] Opening Chroma database...")

        self.client = chromadb.PersistentClient(
            path=str(self.db_dir)
        )

        self.collection = self.client.get_collection(
            name=self.collection_name
        )

        print(
            "[RAG] Collection loaded: "
            f"{self.collection_name}, "
            f"count={self.collection.count()}, "
            f"layered={self.layered_retrieval_enabled}, "
            f"v3={self.v3_retrieval_enabled}"
        )

    def _encode_query(
        self,
        query: str,
    ) -> list[float]:
        return self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
        ).tolist()[0]

    def _build_chunk(
        self,
        *,
        chunk_id: str,
        document: str,
        metadata: dict[str, Any] | None,
        distance: float | None,
        retrieval_bucket: str | None = None,
        score: float | None = None,
        fallback_reason: str | None = None,
    ) -> dict:
        resolved_metadata = metadata or {}

        rounded_distance: float | None

        if distance is None:
            rounded_distance = None
        else:
            rounded_distance = round(
                float(distance),
                4,
            )

        return {
            "chunk_id": str(
                resolved_metadata.get("chunk_id")
                or chunk_id
            ),
            "title": resolved_metadata.get(
                "title",
                "",
            ),
            "section": resolved_metadata.get(
                "section",
                resolved_metadata.get("layer", ""),
            ),
            "knowledge_type": resolved_metadata.get(
                "knowledge_type",
                "",
            ),
            "content": document,
            "distance": rounded_distance,
            "dataset_version": resolved_metadata.get(
                "dataset_version",
                self.dataset_version,
            ),
            "chunk_schema_version": (
                resolved_metadata.get(
                    "chunk_schema_version",
                    self.chunk_schema_version,
                )
            ),
            "runtime_layer": resolved_metadata.get(
                "runtime_layer",
                "",
            ),
            "layer": resolved_metadata.get(
                "layer",
                "",
            ),
            "scenario": resolved_metadata.get(
                "scenario",
                "",
            ),
            "dimension": resolved_metadata.get(
                "dimension",
                "",
            ),
            "priority": resolved_metadata.get(
                "priority",
                "",
            ),
            "retrieval_pool": resolved_metadata.get(
                "retrieval_pool",
                "",
            ),
            "speech_act": resolved_metadata.get(
                "speech_act",
                "",
            ),
            "subtype": resolved_metadata.get(
                "subtype",
                "",
            ),
            "confusable_with": resolved_metadata.get(
                "confusable_with",
                "",
            ),
            "semantic_state": resolved_metadata.get(
                "state",
                resolved_metadata.get(
                    "semantic_state",
                    "",
                ),
            ),
            "retrieval_version": resolved_metadata.get(
                "retrieval_version",
                self.retrieval_version or "",
            ),
            "scenario_taxonomy_version": resolved_metadata.get(
                "scenario_taxonomy_version",
                self.scenario_taxonomy_version or "",
            ),
            "score": score,
            "fallback_reason": fallback_reason or "",
            "retrieval_bucket": (
                retrieval_bucket or ""
            ),
        }

    def _search_legacy(
        self,
        query: str,
        top_k: int,
    ) -> list[dict]:
        query_embedding = self._encode_query(query)

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        chunks: list[dict] = []

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        for index, chunk_id in enumerate(ids):
            distance = float(distances[index])

            if (
                self.distance_threshold is not None
                and distance > self.distance_threshold
            ):
                continue

            chunks.append(
                self._build_chunk(
                    chunk_id=str(chunk_id),
                    document=documents[index],
                    metadata=metadatas[index],
                    distance=distance,
                    retrieval_bucket="LEGACY_TOP_K",
                )
            )

        return chunks

    @staticmethod
    def _build_where_filter(
        runtime_layer: str,
        scenario: str | None = None,
    ) -> dict[str, Any]:
        if scenario:
            return {
                "$and": [
                    {
                        "runtime_layer":
                        runtime_layer
                    },
                    {
                        "scenario":
                        scenario
                    },
                ]
            }

        return {
            "runtime_layer": runtime_layer
        }

    @staticmethod
    def _normalize_meeting_scenario(
        meeting_type: str | None,
    ) -> str | None:
        scenario = _normalize(meeting_type)
        if not scenario:
            return None

        return MEETING_SCENARIO_ALIASES.get(
            scenario,
            scenario,
        )

    @staticmethod
    def _normalize_target_dimension(
        target_dimension: str | None,
    ) -> str | None:
        dimension = _normalize(
            target_dimension
        ).lower()

        if not dimension:
            return None

        return dimension

    @staticmethod
    def _build_v3_where_filter(
        *,
        dimensions: list[str] | None = None,
        retrieval_pools: list[str] | None = None,
        exclude_fixed_policy: bool = False,
    ) -> dict[str, Any] | None:
        filters: list[dict[str, Any]] = []

        if dimensions:
            filters.append(
                {
                    "dimension": {
                        "$in": dimensions
                    }
                }
            )

        if retrieval_pools:
            filters.append(
                {
                    "retrieval_pool": {
                        "$in": retrieval_pools
                    }
                }
            )
        elif exclude_fixed_policy:
            filters.append(
                {
                    "retrieval_pool": {
                        "$ne": "fixed_policy"
                    }
                }
            )

        if not filters:
            return None

        if len(filters) == 1:
            return filters[0]

        return {
            "$and": filters
        }

    @staticmethod
    def _base_score(
        distance: float | None,
    ) -> float:
        if distance is None:
            return 1.0

        return 1.0 / (
            1.0 + max(float(distance), 0.0)
        )

    def _score_v3_chunk(
        self,
        *,
        distance: float | None,
        scenario: str,
        meeting_scenario: str | None,
    ) -> tuple[float, list[str]]:
        score = self._base_score(distance)
        reasons: list[str] = []

        normalized_scenario = _normalize(
            scenario
        )

        normalized_meeting_scenario = (
            self._normalize_meeting_scenario(
                meeting_scenario
            )
        )

        if (
            normalized_meeting_scenario
            and normalized_scenario
            == normalized_meeting_scenario
        ):
            score += self.v3_scenario_boost
            reasons.append("scenario_soft_boost")
        elif normalized_scenario == "all":
            score += self.v3_global_scenario_boost
            reasons.append("all_global_fallback_boost")
        elif normalized_meeting_scenario:
            reasons.append("scenario_not_filtered")
        else:
            reasons.append("unknown_scenario_global_fallback")

        return round(score, 6), reasons

    @staticmethod
    def _trace_candidate(
        chunk: dict,
        *,
        reasons: list[str] | None = None,
        selected: bool = False,
    ) -> dict[str, Any]:
        return {
            "chunk_id": str(
                chunk.get("chunk_id", "")
            ),
            "score": chunk.get("score"),
            "distance": chunk.get("distance"),
            "retrieval_pool": chunk.get(
                "retrieval_pool",
                "",
            ),
            "scenario": chunk.get(
                "scenario",
                "",
            ),
            "dimension": chunk.get(
                "dimension",
                "",
            ),
            "knowledge_type": chunk.get(
                "knowledge_type",
                "",
            ),
            "reasons": reasons or [],
            "selected": selected,
        }

    @staticmethod
    def _v3_rerank_profile(
        query: str,
        target_dimension: str | None,
    ) -> dict[str, Any]:
        text = query.lower()
        dimension = (
            RagRetriever._normalize_target_dimension(
                target_dimension
            )
            or ""
        )

        profile: dict[str, Any] = {
            "preferred_knowledge_types": set(),
            "preferred_speech_acts": set(),
            "preferred_states": set(),
            "preferred_subtype_terms": set(),
            "penalized_knowledge_types": set(),
        }

        if dimension in {
            "action",
            "action_items",
        }:
            profile["preferred_speech_acts"].update(
                {
                    "action",
                    "assignment",
                    "commitment",
                }
            )
            profile[
                "preferred_knowledge_types"
            ].update(
                {
                    "positive_example",
                    "definition",
                    "owner_resolution",
                    "deadline_rule",
                    "boundary_rule",
                }
            )
            profile["preferred_states"].add("open")
            profile["preferred_subtype_terms"].update(
                {
                    "action",
                    "assignment",
                    "owner",
                    "deadline",
                }
            )

            if any(
                term in text
                for term in [
                    "progress",
                    "completed",
                    "already",
                    "进展",
                    "已经",
                    "完成",
                ]
            ):
                profile[
                    "preferred_knowledge_types"
                ].update(
                    {
                        "negative_example",
                        "boundary_rule",
                    }
                )
                profile[
                    "preferred_speech_acts"
                ].add("progress_update")
                profile[
                    "preferred_states"
                ].update(
                    {
                        "unconfirmed",
                        "negative_example",
                    }
                )
                profile[
                    "preferred_subtype_terms"
                ].add("progress")
                profile[
                    "penalized_knowledge_types"
                ].add("positive_example")

            if any(
                term in text
                for term in [
                    "quoted",
                    "example",
                    "引用",
                    "示例",
                    "例子",
                ]
            ):
                profile[
                    "preferred_knowledge_types"
                ].update(
                    {
                        "negative_example",
                        "boundary_rule",
                    }
                )
                profile[
                    "preferred_speech_acts"
                ].update(
                    {
                        "quoted_example",
                        "evidence_rule",
                    }
                )
                profile[
                    "preferred_states"
                ].update(
                    {
                        "unconfirmed",
                        "negative_example",
                    }
                )
                profile[
                    "preferred_subtype_terms"
                ].update(
                    {
                        "quoted",
                        "evidence",
                    }
                )
                profile[
                    "penalized_knowledge_types"
                ].update(
                    {
                        "positive_example",
                        "deadline_rule",
                        "owner_resolution",
                    }
                )

        elif dimension in {
            "decision",
            "key_conclusions",
        }:
            profile["preferred_speech_acts"].update(
                {
                    "decision",
                    "decision_candidate",
                    "boundary_rule",
                }
            )
            profile[
                "preferred_knowledge_types"
            ].update(
                {
                    "positive_example",
                    "negative_example",
                    "boundary_rule",
                    "definition",
                    "reasoning_pattern",
                }
            )
            if any(
                term in text
                for term in [
                    "proposal",
                    "suggest",
                    "建议",
                    "提议",
                ]
            ):
                profile["preferred_speech_acts"].add(
                    "proposal"
                )
                profile["preferred_states"].update(
                    {
                        "unconfirmed",
                        "negative_example",
                    }
                )
                profile[
                    "preferred_subtype_terms"
                ].add("proposal")
            if any(
                term in text
                for term in [
                    "defer",
                    "postpone",
                    "暂缓",
                    "推迟",
                    "先放",
                ]
            ):
                profile["preferred_states"].add(
                    "deferred"
                )
                profile[
                    "preferred_subtype_terms"
                ].add("defer")

        elif dimension in {
            "unresolved",
            "unresolved_issues",
        }:
            profile["preferred_speech_acts"].update(
                {
                    "open_issue",
                    "question",
                }
            )
            profile[
                "preferred_knowledge_types"
            ].update(
                {
                    "positive_example",
                    "negative_example",
                    "boundary_rule",
                    "definition",
                    "reasoning_pattern",
                }
            )
            profile["preferred_states"].update(
                {
                    "open",
                    "waiting_external",
                    "waiting_decision",
                    "blocked",
                }
            )
            profile["preferred_subtype_terms"].update(
                {
                    "open",
                    "issue",
                    "external",
                    "blocked",
                }
            )
            if any(
                term in text
                for term in [
                    "resolved",
                    "answered",
                    "已解决",
                    "已经回答",
                    "确定",
                ]
            ):
                profile["preferred_states"].update(
                    {
                        "resolved",
                        "negative_example",
                    }
                )
                profile[
                    "preferred_knowledge_types"
                ].update(
                    {
                        "negative_example",
                        "boundary_rule",
                    }
                )
                profile[
                    "penalized_knowledge_types"
                ].add("positive_example")

        elif dimension in {
            "risk",
            "risks_and_focus",
        }:
            profile["preferred_speech_acts"].update(
                {
                    "risk_warning",
                    "boundary_reasoning",
                }
            )
            profile[
                "preferred_knowledge_types"
            ].update(
                {
                    "positive_example",
                    "negative_example",
                    "boundary_rule",
                    "definition",
                    "reasoning_pattern",
                }
            )
            profile["preferred_states"].add("potential")
            profile["preferred_subtype_terms"].update(
                {
                    "risk",
                    "future",
                    "current",
                    "boundary",
                }
            )
            if any(
                term in text
                for term in [
                    "current",
                    "not future",
                    "当前",
                    "现存",
                ]
            ):
                profile["preferred_states"].add(
                    "negative_example"
                )
                profile[
                    "penalized_knowledge_types"
                ].add("positive_example")

        return profile

    def _score_v3_rerank_chunk(
        self,
        *,
        chunk: dict,
        query: str,
        target_dimension: str | None,
        meeting_scenario: str | None,
        dense_rank: int,
    ) -> tuple[float, list[str]]:
        profile = self._v3_rerank_profile(
            query,
            target_dimension,
        )
        score = float(chunk.get("score") or 0.0)
        score += max(0.0, 0.2 - dense_rank * 0.01)
        reasons = [
            "dense_score",
            "dense_rank_prior",
        ]

        dimension = _normalize(
            chunk.get("dimension")
        )
        knowledge_type = _normalize(
            chunk.get("knowledge_type")
        )
        speech_act = _normalize(
            chunk.get("speech_act")
        )
        subtype = _normalize(
            chunk.get("subtype")
        )
        semantic_state = _normalize(
            chunk.get("semantic_state")
        )
        scenario = _normalize(
            chunk.get("scenario")
        )
        expected_dimensions = V3_DIMENSION_ROUTES.get(
            self._normalize_target_dimension(
                target_dimension
            )
            or "",
            [],
        )

        if expected_dimensions and dimension == expected_dimensions[0]:
            score += 0.35
            reasons.append("target_dimension_match")
        elif dimension in {
            "cross_dimension",
            "evidence",
        }:
            score += 0.12
            reasons.append("allowed_boundary_dimension")

        normalized_meeting_scenario = (
            self._normalize_meeting_scenario(
                meeting_scenario
            )
        )
        if (
            normalized_meeting_scenario
            and scenario == normalized_meeting_scenario
        ):
            score += 0.12
            reasons.append("scenario_match")
        elif scenario == "all":
            score += 0.05
            reasons.append("global_rule")

        if knowledge_type in profile[
            "preferred_knowledge_types"
        ]:
            score += 0.2
            reasons.append("knowledge_type_match")
        if speech_act in profile[
            "preferred_speech_acts"
        ]:
            score += 0.35
            reasons.append("speech_act_match")
        if (
            semantic_state
            and semantic_state != "n/a"
            and semantic_state
            in profile["preferred_states"]
        ):
            score += 0.25
            reasons.append("semantic_state_match")
        if any(
            term in subtype
            for term in profile[
                "preferred_subtype_terms"
            ]
        ):
            score += 0.3
            reasons.append("subtype_match")
        if knowledge_type in profile[
            "penalized_knowledge_types"
        ]:
            score -= 0.35
            reasons.append("penalized_knowledge_type")

        return round(score, 6), reasons

    def _rerank_v3_vector_chunks(
        self,
        *,
        chunks: list[dict],
        query: str,
        target_dimension: str | None,
        meeting_scenario: str | None,
    ) -> tuple[list[dict], dict[str, Any]]:
        reranked: list[dict] = []

        for dense_rank, chunk in enumerate(
            chunks,
            start=1,
        ):
            rerank_score, reasons = (
                self._score_v3_rerank_chunk(
                    chunk=chunk,
                    query=query,
                    target_dimension=target_dimension,
                    meeting_scenario=meeting_scenario,
                    dense_rank=dense_rank,
                )
            )
            reranked.append(
                {
                    **chunk,
                    "dense_original_rank": dense_rank,
                    "dense_score": chunk.get("score"),
                    "rerank_score": rerank_score,
                    "rerank_reasons": reasons,
                }
            )

        reranked.sort(
            key=lambda chunk: (
                -float(
                    chunk.get("rerank_score") or 0.0
                ),
                int(
                    chunk.get("dense_original_rank")
                    or 0
                ),
                str(chunk.get("chunk_id")),
            )
        )

        for final_rank, chunk in enumerate(
            reranked,
            start=1,
        ):
            chunk["rerank_final_rank"] = final_rank

        return reranked, {
            "enabled": True,
            "fallback": False,
            "candidate_count": len(chunks),
        }

    def _query_v3_vector_candidates(
        self,
        *,
        query_embedding: list[float],
        candidate_count: int,
        dimensions: list[str] | None = None,
    ) -> list[dict]:
        where_filter = self._build_v3_where_filter(
            dimensions=dimensions,
            retrieval_pools=V3_VECTOR_RETRIEVAL_POOLS
            if dimensions
            else None,
            exclude_fixed_policy=not dimensions,
        )

        kwargs: dict[str, Any] = {
            "query_embeddings": [
                query_embedding
            ],
            "n_results": candidate_count,
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }

        if where_filter is not None:
            kwargs["where"] = where_filter

        result = self.collection.query(**kwargs)

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        chunks: list[dict] = []

        for index, chunk_id in enumerate(ids):
            distance = float(distances[index])

            if (
                self.distance_threshold is not None
                and distance > self.distance_threshold
            ):
                continue

            chunks.append(
                self._build_chunk(
                    chunk_id=str(chunk_id),
                    document=documents[index],
                    metadata=metadatas[index],
                    distance=distance,
                    retrieval_bucket="V3_VECTOR",
                )
            )

        return chunks

    def _get_v3_fixed_policy_chunks(
        self,
        *,
        dimensions: list[str],
    ) -> list[dict]:
        if self.v3_fixed_policy_k <= 0:
            return []

        result = self.collection.get(
            where=self._build_v3_where_filter(
                dimensions=dimensions,
                retrieval_pools=[
                    "fixed_policy"
                ],
            ),
            include=[
                "documents",
                "metadatas",
            ],
        )

        chunks: list[dict] = []

        for index, chunk_id in enumerate(
            result["ids"]
        ):
            metadata = result["metadatas"][index]
            score, _reasons = self._score_v3_chunk(
                distance=None,
                scenario=str(
                    metadata.get("scenario", "")
                ),
                meeting_scenario=None,
            )
            chunks.append(
                self._build_chunk(
                    chunk_id=str(chunk_id),
                    document=result["documents"][index],
                    metadata=metadata,
                    distance=None,
                    retrieval_bucket="V3_FIXED_POLICY",
                    score=score,
                )
            )

        chunks.sort(
            key=lambda chunk: (
                str(chunk.get("dimension"))
                != dimensions[0],
                str(chunk.get("priority"))
                != "critical",
                str(chunk.get("chunk_id")),
            )
        )

        return chunks[
            : self.v3_fixed_policy_k
        ]

    def _search_v3(
        self,
        *,
        query: str,
        top_k: int,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> RetrievalResult:
        normalized_dimension = (
            self._normalize_target_dimension(
                target_dimension
            )
        )

        low_confidence_scenario = (
            meeting_type_confidence is not None
            and meeting_type_confidence
            < self.v3_meeting_scenario_min_confidence
        )

        routed_scenario = None
        if not low_confidence_scenario:
            routed_scenario = (
                self._normalize_meeting_scenario(
                    meeting_type
                )
            )
        routed_meeting_type = (
            _normalize(meeting_type)
            if meeting_type
            else None
        )

        fallback_reason: str | None = None

        if (
            routed_scenario is None
            and not low_confidence_scenario
            and transcript
            and transcript.strip()
        ):
            route = route_rag_meeting_type(
                transcript
            )
            if route is not None:
                routed_meeting_type = (
                    route.meeting_type
                )
                routed_scenario = (
                    self._normalize_meeting_scenario(
                        route.scenario
                    )
                )

        if routed_scenario is None:
            fallback_reason = (
                "meeting_scenario_low_confidence_all_global_fallback"
                if low_confidence_scenario
                else "meeting_scenario_unknown_all_global_fallback"
            )

        dimensions: list[str] | None = None
        if normalized_dimension:
            dimensions = V3_DIMENSION_ROUTES.get(
                normalized_dimension
            )
            if not dimensions:
                fallback_reason = (
                    "target_dimension_not_supported"
                )
                dimensions = None

        query_embedding = self._encode_query(
            query
        )

        final_limit = max(
            1,
            min(top_k, self.v3_final_k),
        )

        fixed_chunks: list[dict] = []
        if dimensions:
            fixed_chunks = (
                self._get_v3_fixed_policy_chunks(
                    dimensions=dimensions
                )
            )

        candidate_count = max(
            final_limit
            * max(
                1,
                self.v3_vector_candidate_multiplier,
            ),
            final_limit + 5,
        )

        vector_chunks = (
            self._query_v3_vector_candidates(
                query_embedding=query_embedding,
                candidate_count=candidate_count,
                dimensions=dimensions,
            )
        )

        candidate_trace: list[dict[str, Any]] = []
        scored_vector_chunks: list[dict] = []

        for chunk in vector_chunks:
            score, reasons = self._score_v3_chunk(
                distance=chunk.get("distance"),
                scenario=str(
                    chunk.get("scenario", "")
                ),
                meeting_scenario=routed_scenario,
            )
            scored = {
                **chunk,
                "score": score,
            }
            scored_vector_chunks.append(scored)
            candidate_trace.append(
                self._trace_candidate(
                    scored,
                    reasons=reasons,
                )
            )

        scored_vector_chunks.sort(
            key=lambda chunk: (
                -float(chunk.get("score") or 0.0),
                str(chunk.get("chunk_id")),
            )
        )

        reranker_trace: dict[str, Any] | None = None
        ranked_vector_chunks = scored_vector_chunks
        if self.reranker_enabled:
            try:
                ranked_vector_chunks, reranker_trace = (
                    self._rerank_v3_vector_chunks(
                        chunks=scored_vector_chunks,
                        query=query,
                        target_dimension=target_dimension,
                        meeting_scenario=routed_scenario,
                    )
                )
            except Exception as exc:
                ranked_vector_chunks = []
                for dense_rank, chunk in enumerate(
                    scored_vector_chunks,
                    start=1,
                ):
                    ranked_vector_chunks.append(
                        {
                            **chunk,
                            "dense_original_rank": dense_rank,
                            "dense_score": chunk.get("score"),
                            "rerank_score": None,
                            "rerank_reasons": [],
                            "rerank_final_rank": dense_rank,
                        }
                    )
                reranker_trace = {
                    "enabled": True,
                    "fallback": True,
                    "fallback_reason": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                    "candidate_count": len(
                        scored_vector_chunks
                    ),
                }

        selected = self._deduplicate(
            fixed_chunks
            + ranked_vector_chunks
        )[:final_limit]

        selected_ids = {
            str(chunk["chunk_id"])
            for chunk in selected
        }

        final_trace = []
        for chunk in selected:
            reasons = []
            if (
                chunk.get("retrieval_pool")
                == "fixed_policy"
            ):
                reasons = [
                    "fixed_policy_injected"
                ]
            elif self.reranker_enabled:
                reasons = list(
                    chunk.get("rerank_reasons") or []
                )

            trace_entry = self._trace_candidate(
                chunk,
                reasons=reasons,
                selected=True,
            )
            if self.reranker_enabled and (
                chunk.get("retrieval_pool")
                != "fixed_policy"
            ):
                trace_entry.update(
                    {
                        "dense_original_rank": chunk.get(
                            "dense_original_rank"
                        ),
                        "dense_score": chunk.get(
                            "dense_score"
                        ),
                        "rerank_score": chunk.get(
                            "rerank_score"
                        ),
                        "rerank_final_rank": chunk.get(
                            "rerank_final_rank"
                        ),
                        "dropped": False,
                    }
                )
            final_trace.append(trace_entry)

        if self.reranker_enabled:
            candidate_trace = []
            for chunk in ranked_vector_chunks:
                chunk_id = str(chunk.get("chunk_id", ""))
                is_selected = chunk_id in selected_ids
                trace_entry = self._trace_candidate(
                    chunk,
                    reasons=list(
                        chunk.get("rerank_reasons")
                        or []
                    ),
                    selected=is_selected,
                )
                trace_entry.update(
                    {
                        "dense_original_rank": chunk.get(
                            "dense_original_rank"
                        ),
                        "dense_score": chunk.get(
                            "dense_score"
                        ),
                        "rerank_score": chunk.get(
                            "rerank_score"
                        ),
                        "rerank_final_rank": chunk.get(
                            "rerank_final_rank"
                        ),
                        "dropped": not is_selected,
                    }
                )
                candidate_trace.append(trace_entry)
        else:
            candidate_trace = [
                {
                    **candidate,
                    "selected": candidate[
                        "chunk_id"
                    ]
                    in selected_ids,
                }
                for candidate in candidate_trace
            ]

        trace = {
            "query": query,
            "target_dimension": target_dimension,
            "resolved_dimensions": dimensions or [],
            "meeting_scenario": routed_scenario
            or "all",
            "candidate_chunks": candidate_trace,
            "final_selected_chunks": final_trace,
            "final_selected_chunk_ids": [
                str(chunk["chunk_id"])
                for chunk in selected
            ],
            "fallback_reason": fallback_reason,
        }
        if reranker_trace is not None:
            trace["reranker"] = reranker_trace

        return RetrievalResult(
            chunks=selected,
            strategy="v3_dimension_pool_routing"
            if dimensions
            else "v3_compatible_top_k",
            buckets=self._build_bucket_map(
                selected
            ),
            trace=trace,
            routed_meeting_type=routed_meeting_type,
            routed_scenario=routed_scenario,
            fallback_reason=fallback_reason,
        )

    def _get_global_fixed_rules(
        self,
    ) -> list[dict]:
        if not self.global_fixed_ids:
            raise RuntimeError(
                "No global fixed RAG rule IDs configured"
            )

        result = self.collection.get(
            ids=self.global_fixed_ids,
            include=[
                "documents",
                "metadatas",
            ],
        )

        by_id: dict[str, dict] = {}

        for index, chunk_id in enumerate(
            result["ids"]
        ):
            chunk = self._build_chunk(
                chunk_id=str(chunk_id),
                document=result["documents"][index],
                metadata=result["metadatas"][index],
                distance=None,
                retrieval_bucket="GLOBAL_FIXED",
            )

            by_id[str(chunk_id)] = chunk

        missing_ids = [
            chunk_id
            for chunk_id in self.global_fixed_ids
            if chunk_id not in by_id
        ]

        if missing_ids:
            raise RuntimeError(
                "Global fixed RAG rules not found: "
                f"{missing_ids}"
            )

        chunks = [
            by_id[chunk_id]
            for chunk_id in self.global_fixed_ids
        ]

        for chunk in chunks:
            runtime_layer = _normalize(
                chunk.get("runtime_layer")
            )

            if runtime_layer != "POLICY_FIXED":
                raise RuntimeError(
                    f"{chunk['chunk_id']} must use "
                    "runtime_layer=POLICY_FIXED, "
                    f"actual={runtime_layer}"
                )

        return chunks

    def _query_layer(
        self,
        *,
        query_embedding: list[float],
        runtime_layer: str,
        count: int,
        scenario: str | None = None,
        exclude_ids: set[str] | None = None,
        retrieval_bucket: str,
    ) -> list[dict]:
        if count <= 0:
            return []

        excluded = exclude_ids or set()

        candidate_count = (
            count
            + len(excluded)
            + 5
        )

        result = self.collection.query(
            query_embeddings=[
                query_embedding
            ],
            n_results=candidate_count,
            where=self._build_where_filter(
                runtime_layer,
                scenario,
            ),
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        chunks: list[dict] = []

        for index, chunk_id in enumerate(ids):
            resolved_id = str(chunk_id)

            if resolved_id in excluded:
                continue

            distance = float(distances[index])

            if (
                self.distance_threshold is not None
                and distance > self.distance_threshold
            ):
                continue

            chunks.append(
                self._build_chunk(
                    chunk_id=resolved_id,
                    document=documents[index],
                    metadata=metadatas[index],
                    distance=distance,
                    retrieval_bucket=(
                        retrieval_bucket
                    ),
                )
            )

            if len(chunks) == count:
                break

        if len(chunks) != count:
            raise RuntimeError(
                "Insufficient layered RAG results: "
                f"runtime_layer={runtime_layer}, "
                f"scenario={scenario}, "
                f"expected={count}, "
                f"actual={len(chunks)}"
            )

        return chunks

    @staticmethod
    def _deduplicate(
        chunks: list[dict],
    ) -> list[dict]:
        seen_ids: set[str] = set()
        result: list[dict] = []

        for chunk in chunks:
            chunk_id = str(chunk["chunk_id"])

            if chunk_id in seen_ids:
                continue

            seen_ids.add(chunk_id)
            result.append(chunk)

        return result

    def _build_layered_query(
        self,
        *,
        query: str,
        transcript: str,
        scenario: str,
    ) -> str:
        transcript_limit = max(
            0,
            self.layered_query_transcript_chars,
        )

        transcript_context = (
            transcript[:transcript_limit]
            if transcript_limit > 0
            else ""
        )

        return (
            f"{query.strip()}\n\n"
            f"会议场景：{scenario}\n\n"
            f"会议转写：\n{transcript_context}"
        ).strip()

    def _search_layered(
        self,
        *,
        query: str,
        transcript: str,
        scenario: str,
    ) -> list[dict]:
        layered_query = self._build_layered_query(
            query=query,
            transcript=transcript,
            scenario=scenario,
        )

        query_embedding = self._encode_query(
            layered_query
        )

        global_chunks = (
            self._get_global_fixed_rules()
        )

        global_ids = {
            str(chunk["chunk_id"])
            for chunk in global_chunks
        }

        policy_chunks = self._query_layer(
            query_embedding=query_embedding,
            runtime_layer="POLICY_FIXED",
            count=self.layered_policy_k,
            exclude_ids=global_ids,
            retrieval_bucket="POLICY_SELECTED",
        )

        used_ids = {
            *global_ids,
            *[
                str(chunk["chunk_id"])
                for chunk in policy_chunks
            ],
        }

        dynamic_chunks = self._query_layer(
            query_embedding=query_embedding,
            runtime_layer="RAG_DYNAMIC",
            count=self.layered_dynamic_k,
            exclude_ids=used_ids,
            retrieval_bucket="RAG_DYNAMIC",
        )

        used_ids.update(
            str(chunk["chunk_id"])
            for chunk in dynamic_chunks
        )

        scenario_chunks = self._query_layer(
            query_embedding=query_embedding,
            runtime_layer="RAG_SCENARIO",
            scenario=scenario,
            count=self.layered_scenario_k,
            exclude_ids=used_ids,
            retrieval_bucket="RAG_SCENARIO",
        )

        chunks = self._deduplicate(
            global_chunks
            + policy_chunks
            + dynamic_chunks
            + scenario_chunks
        )

        expected_count = (
            len(self.global_fixed_ids)
            + self.layered_policy_k
            + self.layered_dynamic_k
            + self.layered_scenario_k
        )

        if len(chunks) != expected_count:
            raise RuntimeError(
                "Layered RAG result count mismatch: "
                f"expected={expected_count}, "
                f"actual={len(chunks)}"
            )

        return chunks

    @staticmethod
    def _build_bucket_map(
        chunks: list[dict],
    ) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {}

        for chunk in chunks:
            bucket = (
                _normalize(
                    chunk.get("retrieval_bucket")
                )
                or "UNKNOWN"
            )

            buckets.setdefault(
                bucket,
                [],
            ).append(
                str(chunk["chunk_id"])
            )

        return buckets

    def _retrieve(
        self,
        *,
        query: str,
        top_k: int,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> RetrievalResult:
        if self.v3_retrieval_enabled:
            return self._search_v3(
                query=query,
                top_k=top_k,
                transcript=transcript,
                meeting_type=meeting_type,
                meeting_type_confidence=meeting_type_confidence,
                target_dimension=target_dimension,
            )

        if not self.layered_retrieval_enabled:
            chunks = self._search_legacy(
                query=query,
                top_k=top_k,
            )

            return RetrievalResult(
                chunks=chunks,
                strategy="legacy_top_k",
                buckets=self._build_bucket_map(
                    chunks
                ),
            )

        resolved_transcript = str(
            transcript or ""
        ).strip()

        routed_meeting_type: str | None = None
        routed_scenario: str | None = None

        if meeting_type and meeting_type.strip():
            routed_meeting_type = (
                meeting_type.strip()
            )
            routed_scenario = (
                meeting_type.strip()
            )
        elif resolved_transcript:
            route = route_rag_meeting_type(
                resolved_transcript
            )

            if route is not None:
                routed_meeting_type = (
                    route.meeting_type
                )
                routed_scenario = (
                    route.scenario
                )

        if not routed_scenario:
            fallback_reason = (
                "meeting_type_route_not_found"
            )

            if not self.layered_fallback_enabled:
                raise RuntimeError(
                    fallback_reason
                )

            chunks = self._search_legacy(
                query=query,
                top_k=top_k,
            )

            return RetrievalResult(
                chunks=chunks,
                strategy="legacy_top_k_fallback",
                buckets=self._build_bucket_map(
                    chunks
                ),
                fallback_reason=fallback_reason,
            )

        try:
            chunks = self._search_layered(
                query=query,
                transcript=resolved_transcript,
                scenario=routed_scenario,
            )

            return RetrievalResult(
                chunks=chunks,
                strategy="layered_1_2_3_2",
                buckets=self._build_bucket_map(
                    chunks
                ),
                routed_meeting_type=(
                    routed_meeting_type
                ),
                routed_scenario=routed_scenario,
            )

        except Exception as exc:
            fallback_reason = (
                f"{type(exc).__name__}: {exc}"
            )

            if not self.layered_fallback_enabled:
                raise

            print(
                "[RAG] Layered retrieval failed; "
                "falling back to legacy Top-K: "
                f"{fallback_reason}"
            )

            chunks = self._search_legacy(
                query=query,
                top_k=top_k,
            )

            return RetrievalResult(
                chunks=chunks,
                strategy="legacy_top_k_fallback",
                buckets=self._build_bucket_map(
                    chunks
                ),
                routed_meeting_type=(
                    routed_meeting_type
                ),
                routed_scenario=routed_scenario,
                fallback_reason=fallback_reason,
            )

    def search(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> list[dict]:
        if not query or not query.strip():
            raise ValueError(
                "RAG query cannot be empty"
            )

        settings = get_settings()

        limit = (
            top_k
            if top_k is not None
            else settings.rag_top_k
        )

        result = self._retrieve(
            query=query,
            top_k=limit,
            transcript=transcript,
            meeting_type=meeting_type,
            meeting_type_confidence=meeting_type_confidence,
            target_dimension=target_dimension,
        )

        return result.chunks

    def build_context_payload(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> RagContext:
        if not query or not query.strip():
            raise ValueError(
                "RAG query cannot be empty"
            )

        settings = get_settings()

        limit = (
            top_k
            if top_k is not None
            else settings.rag_top_k
        )

        result = self._retrieve(
            query=query,
            top_k=limit,
            transcript=transcript,
            meeting_type=meeting_type,
            meeting_type_confidence=meeting_type_confidence,
            target_dimension=target_dimension,
        )

        text = build_context_text(
            result.chunks,
            max_chars=self.max_context_chars,
        )

        return RagContext(
            text=text,
            chunks=result.chunks,
            chunk_ids=[
                str(chunk["chunk_id"])
                for chunk in result.chunks
            ],
            retrieved_chunk_ids=[
                str(chunk["chunk_id"])
                for chunk in result.chunks
            ],
            collection_name=self.collection_name,
            embedding_model=(
                self.embedding_model_name
            ),
            dataset_version=(
                self.dataset_version
            ),
            chunk_schema_version=(
                self.chunk_schema_version
            ),
            retrieval_version=(
                self.retrieval_version
                or (
                    result.chunks[0].get(
                        "retrieval_version"
                    )
                    if result.chunks
                    else None
                )
            ),
            scenario_taxonomy_version=(
                self.scenario_taxonomy_version
                or (
                    result.chunks[0].get(
                        "scenario_taxonomy_version"
                    )
                    if result.chunks
                    else None
                )
            ),
            retrieval_strategy=(
                result.strategy
            ),
            retrieval_buckets=(
                result.buckets
            ),
            retrieval_trace=(
                result.trace
            ),
            routed_meeting_type=(
                result.routed_meeting_type
            ),
            routed_scenario=(
                result.routed_scenario
            ),
            fallback_reason=(
                result.fallback_reason
            ),
        )

    def build_context(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
        meeting_type_confidence: float | None = None,
        target_dimension: str | None = None,
    ) -> str:
        return self.build_context_payload(
            query=query,
            top_k=top_k,
            transcript=transcript,
            meeting_type=meeting_type,
            meeting_type_confidence=meeting_type_confidence,
            target_dimension=target_dimension,
        ).text
