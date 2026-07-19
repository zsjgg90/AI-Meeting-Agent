import argparse
import json

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import ActionItem
from app.rag_retriever import COLLECTION_NAME
from app.summary_agent import SummaryAgentError, summarize_meeting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a structured meeting summary from transcript segments.")
    parser.add_argument("meeting_id", help="Meeting ID to summarize.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    db = SessionLocal()
    try:
        settings = get_settings()
        summary = summarize_meeting(db, args.meeting_id)
        action_items = list(
            db.scalars(select(ActionItem).where(ActionItem.summary_id == summary.id).order_by(ActionItem.created_at)).all()
        )
        print(
            json.dumps(
                {
                    "meeting_id": args.meeting_id,
                    "summary_id": summary.id,
                    "meeting_agenda": summary.meeting_agenda,
                    "meeting_summary": summary.meeting_summary or summary.overview,
                    "key_conclusions": summary.key_conclusions,
                    "topics": summary.topics,
                    "action_items": [
                        {
                            "task": item.task,
                            "owner_name": item.owner_name or item.owner,
                            "deadline": item.deadline or item.due_date,
                            "priority": item.priority,
                            "status": item.status,
                            "source_text": item.source_text or item.source,
                            "source_segment_id": item.source_segment_id,
                            "confidence": item.confidence,
                        }
                        for item in action_items
                    ],
                    "unresolved_issues": summary.unresolved_issues,
                    "risks_and_focus": summary.risks_and_focus,
                    "metadata": {
                        "model": (summary.model_name or "").replace("+rag", ""),
                        "model_name": summary.model_name,
                        "temperature": settings.ollama_temperature,
                        "rag_enabled": bool(summary.model_name and "+rag" in summary.model_name),
                        "rag_collection": COLLECTION_NAME,
                        "confidence_score": summary.confidence_score,
                        "generated_at": summary.updated_at.isoformat(),
                    },
                },
                ensure_ascii=False,
            )
        )
    except SummaryAgentError as exc:
        parser.exit(status=1, message=f"{exc}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
