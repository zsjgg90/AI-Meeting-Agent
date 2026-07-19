from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.agents.semantic_agent import SemanticEvent
from app.models import MeetingChunk, TranscriptSegment


class MemoryAgent:
    name = "memory"

    def run(
        self,
        db: Session,
        meeting_id: str,
        segments: list[TranscriptSegment],
        semantic_events: list[SemanticEvent],
    ) -> AgentResult:
        db.execute(delete(MeetingChunk).where(MeetingChunk.meeting_id == meeting_id))

        chunks: list[MeetingChunk] = []
        for segment in segments:
            chunks.append(
                MeetingChunk(
                    meeting_id=meeting_id,
                    speaker=segment.speaker_label,
                    content=segment.text,
                    metadata_={
                        "source": "transcript",
                        "segment_id": segment.id,
                        "start_time": segment.start_time,
                        "end_time": segment.end_time,
                    },
                )
            )

        for index, event in enumerate(semantic_events):
            chunks.append(
                MeetingChunk(
                    meeting_id=meeting_id,
                    speaker=event.speaker_label,
                    content=event.text,
                    metadata_={
                        "source": "semantic_event",
                        "event_index": index,
                        "event_type": event.event_type,
                        "confidence": event.confidence,
                        "start_time": event.start_time,
                        "end_time": event.end_time,
                    },
                )
            )

        db.add_all(chunks)
        db.commit()
        return AgentResult(
            agent=self.name,
            status="completed",
            data={"memory_chunk_count": len(chunks)},
        )
