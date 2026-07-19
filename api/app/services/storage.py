from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings


def meeting_storage_dir(meeting_id: str) -> Path:
    base_dir = Path(get_settings().storage_dir)
    path = base_dir / "meetings" / meeting_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(filename: str) -> str:
    return Path(filename).name.replace(" ", "_")


def save_upload_file(meeting_id: str, upload: UploadFile) -> Path:
    filename = safe_filename(upload.filename or "meeting-audio.m4a")
    destination = meeting_storage_dir(meeting_id) / filename
    suffix = destination.suffix
    stem = destination.stem
    counter = 1
    while destination.exists():
        destination = destination.with_name(f"{stem}_{counter}{suffix}")
        counter += 1

    with destination.open("wb") as out_file:
        while chunk := upload.file.read(1024 * 1024):
            out_file.write(chunk)

    return destination
