from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from sqlalchemy import text

from app.agents import OrchestratorAgent
from app.database import SessionLocal
from app.diarization import DiarizationError
from app.summary_agent import SummaryAgentError, summarize_meeting
from app.config import get_settings
from app.errors import classify_exception
from app.observability import log_event
from app.prompt_registry import get_meeting_analyst_prompt_spec
from app.transcription import TranscriptionError, get_whisper_model, transcribe_audio_chunk


class ProcessResult(BaseModel):
    meeting_id: str
    status: str
    transcript_segment_count: int
    summary_id: str
    agents: list[dict]


class AnalyzeResult(BaseModel):
    meeting_id: str
    status: str
    summary_id: str


class ChunkTranscriptionRequest(BaseModel):
    audio_file_id: str
    start_offset_seconds: float = 0.0


class ChunkTranscriptionResult(BaseModel):
    meeting_id: str
    audio_file_id: str
    transcript_segment_count: int


app = FastAPI(title="Meeting Worker", version="1.0.0")


def _error_detail(exc: BaseException, stage: str, *, error_code: str | None = None) -> dict[str, str]:
    info = classify_exception(exc, stage)
    return {
        "error_code": error_code or info.error_code,
        "error_stage": info.pipeline_stage,
        "error_message": info.safe_message,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    settings = get_settings()
    checks: dict[str, dict] = {}

    db = SessionLocal()
    try:
        db.execute(text("select 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": exc.__class__.__name__}
    finally:
        db.close()

    try:
        prompt_spec = get_meeting_analyst_prompt_spec()
        checks["prompt"] = {
            "status": "ok" if prompt_spec.path.exists() else "error",
            "prompt_version": prompt_spec.prompt_version,
            "schema_version": prompt_spec.schema_version,
        }
    except Exception as exc:
        checks["prompt"] = {"status": "error", "detail": exc.__class__.__name__}

    try:
        ollama_url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
        response = requests.get(ollama_url, timeout=3)
        response.raise_for_status()
        models = [item.get("name") for item in response.json().get("models", [])]
        checks["ollama"] = {
            "status": "ok" if settings.ollama_model in models else "warning",
            "model": settings.ollama_model,
            "model_available": settings.ollama_model in models,
        }
    except Exception as exc:
        checks["ollama"] = {"status": "error", "model": settings.ollama_model, "detail": exc.__class__.__name__}

    try:
        import chromadb
        from app.rag_retriever import DEFAULT_DB_DIR

        db_dir = settings.rag_chroma_db_dir or str(DEFAULT_DB_DIR)
        client = chromadb.PersistentClient(path=db_dir)
        collection = client.get_collection(name=settings.rag_collection_name)
        checks["rag"] = {
            "status": "ok",
            "collection_name": settings.rag_collection_name,
            "count": collection.count(),
            "dataset_version": settings.rag_dataset_version,
            "chunk_schema_version": settings.rag_chunk_schema_version,
            "embedding_model": settings.rag_embedding_model,
        }
    except Exception as exc:
        checks["rag"] = {
            "status": "warning",
            "collection_name": settings.rag_collection_name,
            "detail": exc.__class__.__name__,
        }

    status = "ok" if all(item["status"] in {"ok", "warning"} for item in checks.values()) else "error"
    return {"status": status, "checks": checks}


@app.post("/warmup")
def warmup() -> dict[str, str]:
    settings = get_settings()
    get_whisper_model(
        settings.realtime_whisper_model_size,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    return {"status": "ok", "model": settings.realtime_whisper_model_size}


@app.post("/meetings/{meeting_id}/process", response_model=ProcessResult)
def process_meeting(meeting_id: str) -> ProcessResult:
    db = SessionLocal()
    try:
        result = OrchestratorAgent().run(db, meeting_id)
        return ProcessResult(
            meeting_id=meeting_id,
            status=result.status,
            transcript_segment_count=result.transcript_segment_count,
            summary_id=result.summary.id,
            agents=[
                {
                    "agent": agent_result.agent,
                    "status": agent_result.status,
                    "data": agent_result.data,
                }
                for agent_result in result.agent_results
            ],
        )
    except TranscriptionError as exc:
        detail = _error_detail(exc, "transcription")
        log_event("worker.process.failed", level="error", meeting_id=meeting_id, **detail)
        raise HTTPException(status_code=400, detail=detail) from exc
    except DiarizationError as exc:
        detail = _error_detail(exc, "diarization")
        log_event("worker.process.failed", level="error", meeting_id=meeting_id, **detail)
        raise HTTPException(status_code=400, detail=detail) from exc
    except SummaryAgentError as exc:
        detail = _error_detail(exc, "summary")
        log_event("worker.process.failed", level="error", meeting_id=meeting_id, **detail)
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        detail = _error_detail(exc, "process", error_code="unknown_worker_error")
        log_event(
            "worker.process.failed",
            level="error",
            meeting_id=meeting_id,
            error_type=exc.__class__.__name__,
            **detail,
        )
        raise HTTPException(status_code=500, detail=detail) from exc
    finally:
        db.close()


@app.post("/meetings/{meeting_id}/analyze", response_model=AnalyzeResult)
def analyze_meeting(meeting_id: str) -> AnalyzeResult:
    db = SessionLocal()
    try:
        summary = summarize_meeting(db, meeting_id)
        return AnalyzeResult(meeting_id=meeting_id, status="completed", summary_id=summary.id)
    except SummaryAgentError as exc:
        detail = _error_detail(exc, "summary")
        log_event("worker.analyze.failed", level="error", meeting_id=meeting_id, **detail)
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        detail = _error_detail(exc, "summary", error_code="unknown_worker_error")
        log_event(
            "worker.analyze.failed",
            level="error",
            meeting_id=meeting_id,
            error_type=exc.__class__.__name__,
            **detail,
        )
        raise HTTPException(status_code=500, detail=detail) from exc
    finally:
        db.close()


@app.post("/meetings/{meeting_id}/transcribe-chunk", response_model=ChunkTranscriptionResult)
def transcribe_chunk(meeting_id: str, payload: ChunkTranscriptionRequest) -> ChunkTranscriptionResult:
    db = SessionLocal()
    try:
        segments = transcribe_audio_chunk(
            db,
            meeting_id=meeting_id,
            audio_file_id=payload.audio_file_id,
            start_offset_seconds=payload.start_offset_seconds,
        )
        return ChunkTranscriptionResult(
            meeting_id=meeting_id,
            audio_file_id=payload.audio_file_id,
            transcript_segment_count=len(segments),
        )
    except TranscriptionError as exc:
        info = classify_exception(exc, "transcription")
        log_event("worker.transcribe_chunk.failed", level="error", meeting_id=meeting_id, **info.__dict__)
        raise HTTPException(status_code=400, detail=info.safe_message) from exc
    finally:
        db.close()
