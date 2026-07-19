from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.models import MeetingSummary
from app.summary_agent import summarize_meeting


class SummaryAgent:
    name = "summary"

    def run(self, db: Session, meeting_id: str) -> tuple[MeetingSummary, AgentResult]:
        summary = summarize_meeting(db, meeting_id)
        return (
            summary,
            AgentResult(
                agent=self.name,
                status="completed",
                data={"summary_id": summary.id},
            ),
        )
