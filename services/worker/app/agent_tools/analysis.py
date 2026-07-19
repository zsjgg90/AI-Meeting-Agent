from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


class AnalyzeMeetingTool(AgentTool):
    def __init__(
        self,
        *,
        service_factory: Callable[[], Any] | None = None,
        policy: ToolPolicy | None = None,
    ) -> None:
        if policy is None:
            from app.config import get_settings

            timeout_seconds = get_settings().ollama_timeout_seconds
            policy = ToolPolicy(
                timeout_seconds=timeout_seconds,
                max_calls_per_run=1,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            )
        super().__init__(name="analyze_meeting", policy=policy)
        self.service_factory = service_factory

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        transcript = payload.get("transcript")
        transcript_text = self._transcript_text(transcript)
        if not transcript_text:
            raise ValueError("transcript is required")

        service = self._get_service()
        result = service.analyze(transcript_text)
        metadata = result.get("_metadata") if isinstance(result, dict) and isinstance(result.get("_metadata"), dict) else {}
        result_source = str(metadata.get("result_source") or "unknown")
        status = "fallback" if metadata.get("fallback_reason") else "success"
        return {
            "meeting_id": payload.get("meeting_id") or context.meeting_id,
            "analysis": result,
            "context_payload": payload.get("context_payload") if isinstance(payload.get("context_payload"), dict) else {},
            "_result_source": result_source,
            "_tool_status": status,
            "_metadata": {
                "model_name": metadata.get("model_name"),
                "prompt_version": metadata.get("prompt_version"),
                "schema_version": metadata.get("schema_version"),
                "rag_chunk_ids": metadata.get("rag_chunk_ids", []),
                "rag_dataset_version": metadata.get("rag_dataset_version"),
                "rag_chunk_schema_version": metadata.get("rag_chunk_schema_version"),
                "rag_collection_name": metadata.get("rag_collection_name"),
                "rag_embedding_model": metadata.get("rag_embedding_model"),
                "fallback_reason": metadata.get("fallback_reason"),
            },
        }

    def _get_service(self) -> Any:
        if self.service_factory is not None:
            return self.service_factory()
        from app.meeting_analyst_service import get_meeting_analyst_service

        return get_meeting_analyst_service()

    def _transcript_text(self, transcript: Any) -> str:
        if isinstance(transcript, str):
            return transcript.strip()
        if isinstance(transcript, list):
            from app.transcript_builder import build_transcript_text

            return build_transcript_text(transcript)
        return ""


__all__ = ["AnalyzeMeetingTool"]
