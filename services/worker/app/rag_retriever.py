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


@dataclass(frozen=True)
class RagContext:
    text: str
    chunks: list[dict]
    chunk_ids: list[str]
    collection_name: str
    embedding_model: str
    dataset_version: str
    chunk_schema_version: str

    retrieval_strategy: str = "legacy_top_k"
    retrieval_buckets: dict[str, list[str]] = field(
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
            f"layered={self.layered_retrieval_enabled}"
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
    ) -> RetrievalResult:
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
        )

        return result.chunks

    def build_context_payload(
        self,
        query: str,
        top_k: int | None = None,
        *,
        transcript: str | None = None,
        meeting_type: str | None = None,
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
            retrieval_strategy=(
                result.strategy
            ),
            retrieval_buckets=(
                result.buckets
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
    ) -> str:
        return self.build_context_payload(
            query=query,
            top_k=top_k,
            transcript=transcript,
            meeting_type=meeting_type,
        ).text