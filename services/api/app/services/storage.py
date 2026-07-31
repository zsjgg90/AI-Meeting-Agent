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
ALLOWED_TASK_ATTACHMENT_EXTENSIONS = {
    ".doc",
    ".docx",
    ".jpeg",
    ".jpg",
    ".md",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
}
ALLOWED_TASK_ATTACHMENT_CONTENT_TYPES = {
    "application/msword",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "text/markdown",
    "text/plain",
}


class AudioStorageError(RuntimeError):
    pass


class UnsupportedAudioFileError(ValueError):
    pass


class TaskAttachmentStorageError(RuntimeError):
    pass


class UnsupportedTaskAttachmentError(ValueError):
    pass


def meeting_storage_dir(meeting_id: str) -> Path:
    base_dir = Path(get_settings().storage_dir)
    path = base_dir / "meetings" / meeting_id / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_attachment_storage_dir(task_id: str) -> Path:
    base_dir = Path(get_settings().storage_dir)
    path = base_dir / "tasks" / task_id / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str) -> str:
    clean_name = Path(filename).name.replace(" ", "_")
    if not clean_name or clean_name in {".", ".."}:
        raise UnsupportedAudioFileError("Audio filename is required.")
    return clean_name


def safe_task_attachment_filename(filename: str) -> str:
    clean_name = Path(filename).name.replace(" ", "_")
    if not clean_name or clean_name in {".", ".."}:
        raise UnsupportedTaskAttachmentError("Attachment filename is required.")
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


def validate_task_attachment(upload: UploadFile) -> str:
    filename = safe_task_attachment_filename(upload.filename or "task-attachment")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_TASK_ATTACHMENT_EXTENSIONS:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_TASK_ATTACHMENT_EXTENSIONS))
        raise UnsupportedTaskAttachmentError(f"Unsupported task attachment file type. Allowed types: {allowed}.")

    content_type = (upload.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if content_type and content_type not in ALLOWED_TASK_ATTACHMENT_CONTENT_TYPES:
        raise UnsupportedTaskAttachmentError(f"Unsupported task attachment content type: {upload.content_type}.")

    return filename


def unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    suffix = destination.suffix
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = destination.with_name(f"{stem}_{counter}{suffix}")
        counter += 1
    return destination


def save_upload_file(meeting_id: str, upload: UploadFile) -> tuple[Path, int]:
    filename = validate_audio_file(upload)
    destination = unique_destination(meeting_storage_dir(meeting_id), filename)

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


def save_task_attachment_file(task_id: str, upload: UploadFile) -> tuple[Path, int]:
    filename = validate_task_attachment(upload)
    destination = unique_destination(task_attachment_storage_dir(task_id), filename)

    file_size_bytes = 0
    try:
        with destination.open("wb") as out_file:
            while chunk := upload.file.read(1024 * 1024):
                file_size_bytes += len(chunk)
                out_file.write(chunk)
    except OSError as exc:
        raise TaskAttachmentStorageError("Failed to save uploaded task attachment.") from exc

    if file_size_bytes == 0:
        destination.unlink(missing_ok=True)
        raise UnsupportedTaskAttachmentError("Uploaded task attachment file is empty.")

    return destination, file_size_bytes
