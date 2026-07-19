from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.models import ActionItem


class ActionAgent:
    name = "action"

    def run(self, db: Session, meeting_id: str) -> AgentResult:
        action_items = list(
            db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting_id).order_by(ActionItem.created_at)).all()
        )
        open_count = sum(1 for item in action_items if item.status == "open")
        return AgentResult(
            agent=self.name,
            status="completed",
            data={
                "action_item_count": len(action_items),
                "open_action_item_count": open_count,
            },
        )
