from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.action_agent import ActionAgent
from app.agents.base import AgentResult
from app.agents.memory_agent import MemoryAgent
from app.agents.recorder_agent import RecorderAgent
from app.agents.semantic_agent import SemanticAgent
from app.agents.speaker_agent import SpeakerAgent
from app.agents.summary_agent import SummaryAgent
from app.agents.transcript_agent import TranscriptAgent
from app.models import MeetingSummary


@dataclass(frozen=True)
class OrchestratorResult:
    meeting_id: str
    status: str
    transcript_segment_count: int
    summary: MeetingSummary
    agent_results: list[AgentResult]


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(self) -> None:
        self.recorder_agent = RecorderAgent()
        self.transcript_agent = TranscriptAgent()
        self.speaker_agent = SpeakerAgent()
        self.semantic_agent = SemanticAgent()
        self.summary_agent = SummaryAgent()
        self.action_agent = ActionAgent()
        self.memory_agent = MemoryAgent()

    def run(self, db: Session, meeting_id: str) -> OrchestratorResult:
        agent_results: list[AgentResult] = []

        _audio_file, audio_path, recorder_result = self.recorder_agent.run(db, meeting_id)
        agent_results.append(recorder_result)

        transcript_segments, transcript_result = self.transcript_agent.run(db, meeting_id)
        agent_results.append(transcript_result)

        transcript_segments, speaker_result = self.speaker_agent.run(db, meeting_id, transcript_segments, audio_path)
        agent_results.append(speaker_result)

        semantic_events, semantic_result = self.semantic_agent.run(db, meeting_id, transcript_segments)
        agent_results.append(semantic_result)

        summary, summary_result = self.summary_agent.run(db, meeting_id)
        agent_results.append(summary_result)

        action_result = self.action_agent.run(db, meeting_id)
        agent_results.append(action_result)

        memory_result = self.memory_agent.run(db, meeting_id, transcript_segments, semantic_events)
        agent_results.append(memory_result)

        return OrchestratorResult(
            meeting_id=meeting_id,
            status="completed",
            transcript_segment_count=len(transcript_segments),
            summary=summary,
            agent_results=agent_results,
        )
