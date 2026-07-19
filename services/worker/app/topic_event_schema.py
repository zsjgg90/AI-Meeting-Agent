from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.semantic_event_schema import SemanticEvent


class TopicEventGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    topic_id: str
    title: str
    event_ids: list[str]
    events: list[SemanticEvent]
    start_time: float | None
    end_time: float | None
    status: str
