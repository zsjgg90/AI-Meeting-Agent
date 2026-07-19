from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class SearchProjectKnowledgeTool(AgentTool):
    def __init__(
        self,
        *,
        retriever_factory: Callable[[], Any] | None = None,
        policy: ToolPolicy | None = None,
    ) -> None:
        super().__init__(
            name="search_project_knowledge",
            policy=policy
            or ToolPolicy(
                timeout_seconds=15,
                max_calls_per_run=5,
                retry_count=1,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.retriever_factory = retriever_factory
        self._retriever: Any | None = None

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        top_k = max(1, min(int(payload.get("top_k") or 5), 20))
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}

        retriever = self._get_retriever()
        context_payload = retriever.build_context_payload(query=query, top_k=top_k)
        chunks = [
            {
                "chunk_id": chunk.get("chunk_id"),
                "title": chunk.get("title"),
                "section": chunk.get("section"),
                "knowledge_type": chunk.get("knowledge_type"),
                "distance": chunk.get("distance"),
                "dataset_version": chunk.get("dataset_version"),
                "chunk_schema_version": chunk.get("chunk_schema_version"),
                "content": str(chunk.get("content") or "")[:1200],
            }
            for chunk in context_payload.chunks
        ]
        return {
            "query": query,
            "top_k": top_k,
            "filters": filters,
            "context_text": context_payload.text,
            "chunks": chunks,
            "chunk_ids": context_payload.chunk_ids,
            "collection_name": context_payload.collection_name,
            "embedding_model": context_payload.embedding_model,
            "dataset_version": context_payload.dataset_version,
            "chunk_schema_version": context_payload.chunk_schema_version,
            "_result_source": "rag",
        }

    def _get_retriever(self) -> Any:
        if self._retriever is None:
            if self.retriever_factory is not None:
                self._retriever = self.retriever_factory()
            else:
                from app.rag_retriever import RagRetriever

                self._retriever = RagRetriever()
        return self._retriever


__all__ = ["SearchProjectKnowledgeTool"]
