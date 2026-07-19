from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.agent_tools.base import AgentTool, ToolExecutionContext, ToolPolicy


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


class GetMeetingContextTool(AgentTool):
    def __init__(
        self,
        *,
        db_provider: Callable[[], Any],
        policy: ToolPolicy | None = None,
    ) -> None:
        super().__init__(
            name="get_meeting_context",
            policy=policy
            or ToolPolicy(
                timeout_seconds=5,
                max_calls_per_run=3,
                retry_count=0,
                read_only=True,
                has_side_effects=False,
                requires_confirmation=False,
            ),
        )
        self.db_provider = db_provider

    def _execute(self, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_id = str(payload.get("meeting_id") or context.meeting_id or "").strip()
        if not meeting_id:
            raise ValueError("meeting_id is required")
        include_transcript = bool(payload.get("include_transcript", True))
        include_summary_metadata = bool(payload.get("include_summary_metadata", True))

        db = self.db_provider()
        try:
            if hasattr(db, "get_meeting_context"):
                data = db.get_meeting_context(
                    meeting_id=meeting_id,
                    include_transcript=include_transcript,
                    include_summary_metadata=include_summary_metadata,
                )
                if data is None:
                    raise LookupError(f"Meeting not found: {meeting_id}")
                if isinstance(data.get("transcript_segments"), list):
                    data["transcript_segments"] = sorted(
                        data["transcript_segments"],
                        key=lambda item: (
                            item.get("start_time", 0.0) if isinstance(item, dict) else 0.0,
                            item.get("segment_index", 0) if isinstance(item, dict) else 0,
                        ),
                    )
                data["_result_source"] = "postgresql"
                return data

            from app.models import Meeting, MeetingSummary, TranscriptSegment

            meeting = db.get(Meeting, meeting_id)
            if meeting is None:
                raise LookupError(f"Meeting not found: {meeting_id}")

            transcript_segments: list[dict[str, Any]] = []
            if include_transcript:
                segments = list(
                    db.scalars(
                        select(TranscriptSegment)
                        .where(TranscriptSegment.meeting_id == meeting_id)
                        .order_by(TranscriptSegment.start_time.asc(), TranscriptSegment.segment_index.asc())
                    ).all()
                )
                transcript_segments = [self._segment_dict(segment) for segment in segments]

            summary_metadata: dict[str, Any] = {}
            if include_summary_metadata:
                summary = db.scalars(
                    select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)
                ).first()
                if summary is not None:
                    summary_metadata = self._summary_metadata(summary)

            return {
                "meeting": self._meeting_dict(meeting),
                "transcript_segments": transcript_segments,
                "summary_metadata": summary_metadata,
                "_result_source": "postgresql",
            }
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()

    def _meeting_dict(self, meeting: Any) -> dict[str, Any]:
        return {
            "id": meeting.id,
            "title": meeting.title,
            "status": meeting.status,
            "created_at": _iso(getattr(meeting, "created_at", None)),
            "updated_at": _iso(getattr(meeting, "updated_at", None)),
        }

    def _segment_dict(self, segment: Any) -> dict[str, Any]:
        return {
            "id": segment.id,
            "meeting_id": segment.meeting_id,
            "audio_file_id": getattr(segment, "audio_file_id", None),
            "segment_index": segment.segment_index,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text,
            "speaker_label": getattr(segment, "speaker_label", None),
            "speaker_name": getattr(segment, "speaker_name", None),
            "speaker_gender": getattr(segment, "speaker_gender", None),
            "semantic_label": getattr(segment, "semantic_label", None),
        }

    def _summary_metadata(self, summary: Any) -> dict[str, Any]:
        result_source = "legacy_qwen_rag" if getattr(summary, "model_name", None) and "+rag" in summary.model_name else "unknown"
        return {
            "summary_id": summary.id,
            "model_name": getattr(summary, "model_name", None),
            "prompt_version": getattr(summary, "prompt_version", None),
            "rag_chunk_ids": getattr(summary, "rag_chunk_ids", []) or [],
            "rag_dataset_version": getattr(summary, "rag_dataset_version", None),
            "rag_chunk_schema_version": getattr(summary, "rag_chunk_schema_version", None),
            "rag_collection_name": getattr(summary, "rag_collection_name", None),
            "rag_embedding_model": getattr(summary, "rag_embedding_model", None),
            "confidence_score": getattr(summary, "confidence_score", None),
            "result_source": result_source,
        }


__all__ = ["GetMeetingContextTool"]
