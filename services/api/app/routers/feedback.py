from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserFeedback
from app.schemas import FeedbackCreate, FeedbackRead

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRead)
def create_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)) -> UserFeedback:
    feedback = UserFeedback(
        feedback_type=payload.feedback_type.strip(),
        description=payload.description.strip(),
        contact=payload.contact.strip() if payload.contact else None,
        image_urls=payload.image_urls,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
