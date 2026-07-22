from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.observability import log_event, safe_error
from app.routers import agent_commands, agent_ops, agent_proposals, feedback, meetings, tasks
from app.services.meeting_task_recovery import recover_stale_meeting_tasks_on_startup


def create_app(session_factory: Callable[[], Session] | None = None) -> FastAPI:
    settings = get_settings()
    task_recovery_session_factory = session_factory or SessionLocal

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        recover_stale_meeting_tasks_on_startup(task_recovery_session_factory)
        yield

    app = FastAPI(title="Meeting Voiceprint AI Agent API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        checks: dict[str, dict] = {}

        db = SessionLocal()
        try:
            db.execute(text("select 1"))
            checks["database"] = {"status": "ok"}
        except Exception as exc:
            checks["database"] = {"status": "error", "detail": exc.__class__.__name__}
            log_event("ready.database.failed", level="error", error_message=safe_error(exc))
        finally:
            db.close()

        try:
            worker_response = httpx.get(f"{settings.worker_url.rstrip('/')}/health", timeout=3)
            worker_response.raise_for_status()
            checks["worker"] = {"status": "ok", "url": settings.worker_url}
        except Exception as exc:
            checks["worker"] = {"status": "error", "url": settings.worker_url, "detail": exc.__class__.__name__}
            log_event("ready.worker.failed", level="error", error_message=safe_error(exc))

        status = "ok" if all(item["status"] == "ok" for item in checks.values()) else "error"
        return {"status": status, "checks": checks}

    app.include_router(meetings.router)
    app.include_router(tasks.router)
    app.include_router(feedback.router)
    app.include_router(agent_proposals.router)
    app.include_router(agent_commands.router)
    app.include_router(agent_ops.router)
    return app


app = create_app()
