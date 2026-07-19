from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TranscriptionTask
from app.schemas import TranscriptionTaskRead

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TranscriptionTaskRead)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TranscriptionTask:
    task = db.get(TranscriptionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task
