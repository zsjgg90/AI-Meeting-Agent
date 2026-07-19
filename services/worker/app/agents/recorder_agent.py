from pathlib import Path
import subprocess
import tempfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.models import AudioFile, Meeting
from app.transcription import TranscriptionError, resolve_audio_path


class RecorderAgent:
    name = "recorder"

    def run(self, db: Session, meeting_id: str) -> tuple[AudioFile, Path, AgentResult]:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise TranscriptionError(f"Meeting not found: {meeting_id}")

        audio_files = list(
            db.scalars(
                select(AudioFile).where(AudioFile.meeting_id == meeting_id).order_by(AudioFile.uploaded_at.asc())
            ).all()
        )
        if not audio_files:
            raise TranscriptionError(f"No uploaded audio file found for meeting {meeting_id}.")

        audio_file = audio_files[-1]
        audio_path = resolve_audio_path(audio_file.path)
        diarization_audio_path = self.resolve_diarization_audio_path(meeting_id, audio_files, audio_path)
        return (
            audio_file,
            diarization_audio_path,
            AgentResult(
                agent=self.name,
                status="completed",
                data={
                    "audio_file_id": audio_file.id,
                    "path": str(diarization_audio_path),
                    "source_audio_file_count": len(audio_files),
                    "file_size_bytes": audio_file.file_size_bytes,
                    "content_type": audio_file.content_type,
                },
            ),
        )

    @staticmethod
    def resolve_diarization_audio_path(meeting_id: str, audio_files: list[AudioFile], fallback_path: Path) -> Path:
        if len(audio_files) <= 1:
            return fallback_path

        paths = [resolve_audio_path(audio_file.path) for audio_file in audio_files]
        output_dir = paths[-1].parent
        output_path = output_dir / f"{meeting_id}_merged_for_diarization.wav"
        list_file_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as list_file:
                list_file_path = Path(list_file.name)
                for path in paths:
                    escaped = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
                    list_file.write(f"file '{escaped}'\n")

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_file_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(output_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if output_path.exists():
                return output_path
        except Exception:
            return fallback_path
        finally:
            if list_file_path and list_file_path.exists():
                list_file_path.unlink(missing_ok=True)

        return fallback_path
