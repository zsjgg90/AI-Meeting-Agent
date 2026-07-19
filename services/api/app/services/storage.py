from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

ALLOWED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".mp4", ".mpeg", ".mpga", ".webm", ".ogg"}
ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/aac",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
    "audio/x-mp4",
    "audio/mpeg",
    "audio/mp3",
    "audio/x-mp3",
    "audio/mpeg3",
    "audio/x-mpeg-3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/vnd.wave",
    "audio/webm",
    "audio/ogg",
    "video/mp4",
    "video/webm",
    "application/octet-stream",
}


class AudioStorageError(RuntimeError):
    pass


class UnsupportedAudioFileError(ValueError):
    pass


def meeting_storage_dir(meeting_id: str) -> Path:
    base_dir = Path(get_settings().storage_dir)
    path = base_dir / "meetings" / meeting_id / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str) -> str:
    clean_name = Path(filename).name.replace(" ", "_")
    if not clean_name or clean_name in {".", ".."}:
        raise UnsupportedAudioFileError("Audio filename is required.")
    return clean_name


def validate_audio_file(upload: UploadFile) -> str:
    filename = safe_filename(upload.filename or "meeting-audio.m4a")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_AUDIO_EXTENSIONS))
        raise UnsupportedAudioFileError(f"Unsupported audio file type. Allowed types: {allowed}.")

    content_type = (upload.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if content_type and content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise UnsupportedAudioFileError(f"Unsupported audio content type: {upload.content_type}.")

    return filename


def save_upload_file(meeting_id: str, upload: UploadFile) -> tuple[Path, int]:
    filename = validate_audio_file(upload)
    destination = meeting_storage_dir(meeting_id) / filename
    suffix = destination.suffix
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = destination.with_name(f"{stem}_{counter}{suffix}")
        counter += 1

    file_size_bytes = 0
    try:
        with destination.open("wb") as out_file:
            while chunk := upload.file.read(1024 * 1024):
                file_size_bytes += len(chunk)
                out_file.write(chunk)
    except OSError as exc:
        raise AudioStorageError("Failed to save uploaded audio file.") from exc

    if file_size_bytes == 0:
        destination.unlink(missing_ok=True)
        raise UnsupportedAudioFileError("Uploaded audio file is empty.")

    return destination, file_size_bytes
