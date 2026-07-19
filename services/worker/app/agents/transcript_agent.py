from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.models import TranscriptSegment
from app.transcription import transcribe_meeting


class TranscriptAgent:
    name = "transcript"

    def run(self, db: Session, meeting_id: str) -> tuple[list[TranscriptSegment], AgentResult]:
        segments = transcribe_meeting(db, meeting_id)
        return (
            segments,
            AgentResult(
                agent=self.name,
                status="completed",
                data={
                    "transcript_segment_count": len(segments),
                    "mode": "batch_high_accuracy",
                    "language": "zh",
                    "output_script": "simplified_chinese",
                },
            ),
        )
