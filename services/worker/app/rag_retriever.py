from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


def build_context_text(
    chunks: list[dict],
    *,
    max_chars: int | None = None,
) -> str:
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"""
【RAG规则 {index}】
标题：{chunk["title"]}
章节：{chunk["section"]}
知识类型：{chunk["knowledge_type"]}
距离：{chunk["distance"]}

{chunk["content"]}
""".strip()
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
        configured_db_dir = db_dir or settings.rag_chroma_db_dir or DEFAULT_DB_DIR

        self.db_dir = Path(configured_db_dir)
        self.collection_name = collection_name or settings.rag_collection_name
        self.embedding_model_name = embedding_model_name or settings.rag_embedding_model
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
        self.dataset_version = settings.rag_dataset_version
        self.chunk_schema_version = settings.rag_chunk_schema_version

        print(
            "[RAG] Loading embedding model..."
            f" local_files_only={settings.rag_embedding_local_files_only}"
        )

        self.embedding_model = SentenceTransformer(
            self.embedding_model_name,
            local_files_only=settings.rag_embedding_local_files_only,
        )

        print("[RAG] Opening Chroma database...")

        self.client = chromadb.PersistentClient(path=str(self.db_dir))

        self.collection = self.client.get_collection(name=self.collection_name)

        print(
            f"[RAG] Collection loaded: "
            f"{self.collection_name}, "
            f"count={self.collection.count()}"
        )

    def search(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[dict]:
        if not query or not query.strip():
            raise ValueError("RAG query cannot be empty")

        settings = get_settings()
        limit = top_k or settings.rag_top_k

        query_embedding = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
        ).tolist()[0]

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        chunks = []

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        for index in range(len(ids)):
            distance = float(distances[index])
            if self.distance_threshold is not None and distance > self.distance_threshold:
                continue

            metadata = metadatas[index] or {}
            chunk_id = str(metadata.get("chunk_id") or ids[index])

            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "title": metadata.get("title", ""),
                    "section": metadata.get("section", ""),
                    "knowledge_type": metadata.get("knowledge_type", ""),
                    "content": documents[index],
                    "distance": round(distance, 4),
                    "dataset_version": metadata.get("dataset_version", self.dataset_version),
                    "chunk_schema_version": metadata.get(
                        "chunk_schema_version",
                        self.chunk_schema_version,
                    ),
                }
            )

        return chunks

    def build_context_payload(
        self,
        query: str,
        top_k: int | None = None,
    ) -> RagContext:
        chunks = self.search(query=query, top_k=top_k)
        text = build_context_text(chunks, max_chars=self.max_context_chars)
        return RagContext(
            text=text,
            chunks=chunks,
            chunk_ids=[str(chunk["chunk_id"]) for chunk in chunks],
            collection_name=self.collection_name,
            embedding_model=self.embedding_model_name,
            dataset_version=self.dataset_version,
            chunk_schema_version=self.chunk_schema_version,
        )

    def build_context(
        self,
        query: str,
        top_k: int | None = None,
    ) -> str:
        return self.build_context_payload(query=query, top_k=top_k).text
