from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import subprocess
import tempfile

from faster_whisper import WhisperModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AudioFile, Meeting, TranscriptSegment


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptSegmentResult:
    start_time: float
    end_time: float
    text: str
    speaker_label: str | None = None
    speaker_gender: str | None = None


_SIMPLIFIED_FALLBACK_MAP = str.maketrans(
    {
        "臺": "台",
        "裡": "里",
        "裏": "里",
        "與": "与",
        "會": "会",
        "議": "议",
        "錄": "录",
        "轉": "转",
        "識": "识",
        "別": "别",
        "聲": "声",
        "發": "发",
        "說": "说",
        "聽": "听",
        "計": "计",
        "劃": "划",
        "項": "项",
        "負": "负",
        "責": "责",
        "務": "务",
        "風": "风",
        "險": "险",
        "決": "决",
        "點": "点",
        "總": "总",
        "結": "结",
        "應": "应",
        "後": "后",
        "進": "进",
        "優": "优",
        "級": "级",
        "數": "数",
        "據": "据",
        "產": "产",
        "品": "品",
        "開": "开",
        "關": "关",
        "聯": "联",
        "繫": "系",
        "實": "实",
        "時": "时",
        "標": "标",
        "題": "题",
        "測": "测",
        "試": "试",
        "報": "报",
        "單": "单",
        "將": "将",
        "為": "为",
        "這": "这",
        "個": "个",
        "們": "们",
        "嗎": "吗",
    }
)


@lru_cache(maxsize=1)
def get_opencc_converter():
    try:
        from opencc import OpenCC
    except Exception:
        return None
    return OpenCC("t2s")


def normalize_transcript_text(text: str) -> str:
    normalized = " ".join(text.strip().split())
    converter = get_opencc_converter()
    if converter is not None:
        normalized = converter.convert(normalized)
    else:
        normalized = normalized.translate(_SIMPLIFIED_FALLBACK_MAP)
    return normalized


def resolve_audio_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if path.exists():
        return path

    normalized = stored_path.replace("\\", "/")
    marker = "/meetings/"
    if marker in normalized:
        relative_path = normalized.split(marker, maxsplit=1)[1]
        candidate = Path(get_settings().storage_dir) / "meetings" / relative_path
        if candidate.exists():
            return candidate

    raise TranscriptionError(f"Audio file does not exist: {stored_path}")


def latest_audio_file(db: Session, meeting_id: str) -> AudioFile:
    audio_file = db.scalars(
        select(AudioFile).where(AudioFile.meeting_id == meeting_id).order_by(AudioFile.uploaded_at.desc())
    ).first()
    if audio_file is None:
        raise TranscriptionError(f"No uploaded audio file found for meeting {meeting_id}.")
    return audio_file


@lru_cache(maxsize=4)
def get_whisper_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe_audio_file(audio_path: Path, realtime: bool = False, chunk_mode: bool = False) -> list[TranscriptSegmentResult]:
    settings = get_settings()
    model_size = settings.realtime_whisper_model_size if realtime else settings.whisper_model_size
    model = get_whisper_model(
        model_size,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    language = settings.whisper_language or None
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        task="transcribe",
        initial_prompt=settings.whisper_initial_prompt or None,
        vad_filter=not realtime,
        beam_size=3 if realtime else 5,
        best_of=3 if realtime else 5,
        temperature=0.0,
        no_speech_threshold=0.35 if realtime else 0.45,
        condition_on_previous_text=not realtime and not chunk_mode,
    )

    results: list[TranscriptSegmentResult] = []
    for segment in segments:
        text = normalize_transcript_text(segment.text)
        if not text:
            continue
        results.append(
            TranscriptSegmentResult(
                start_time=float(segment.start),
                end_time=float(segment.end),
                text=text,
                speaker_label=None,
                speaker_gender=None,
            )
        )
    return results


def audio_files_for_meeting(db: Session, meeting_id: str) -> list[AudioFile]:
    return list(
        db.scalars(
            select(AudioFile).where(AudioFile.meeting_id == meeting_id).order_by(AudioFile.uploaded_at.asc())
        ).all()
    )


def existing_audio_offsets(db: Session, meeting_id: str) -> dict[str, float]:
    rows = db.execute(
        select(TranscriptSegment.audio_file_id, func.min(TranscriptSegment.start_time))
        .where(TranscriptSegment.meeting_id == meeting_id, TranscriptSegment.audio_file_id.is_not(None))
        .group_by(TranscriptSegment.audio_file_id)
    ).all()
    return {str(audio_file_id): float(start_time or 0.0) for audio_file_id, start_time in rows if audio_file_id}


def merge_audio_files_for_meeting(meeting_id: str, audio_files: list[AudioFile]) -> Path | None:
    if len(audio_files) <= 1:
        return None

    paths = [resolve_audio_path(audio_file.path) for audio_file in audio_files]
    output_path = paths[-1].parent / f"{meeting_id}_merged_for_transcription.wav"
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
        return output_path if output_path.exists() else None
    except Exception:
        return None
    finally:
        if list_file_path and list_file_path.exists():
            list_file_path.unlink(missing_ok=True)


def transcribe_audio_files(
    db: Session,
    meeting_id: str,
    audio_files: list[AudioFile],
    meeting: Meeting | None = None,
) -> list[tuple[AudioFile, TranscriptSegmentResult]]:
    settings = get_settings()
    number_of_speakers = number_of_speakers_for_meeting(meeting)
    merged_audio_path = merge_audio_files_for_meeting(meeting_id, audio_files)
    if merged_audio_path is not None:
        merged_segments = transcribe_audio_with_provider(
            merged_audio_path,
            duration_seconds=None,
            chunk_mode=False,
            number_of_speakers=number_of_speakers,
        )
        return [(audio_files[-1], segment) for segment in merged_segments]

    offsets = existing_audio_offsets(db, meeting_id)
    results: list[tuple[AudioFile, TranscriptSegmentResult]] = []
    cumulative_offset = 0.0
    chunk_mode = len(audio_files) > 1
    ordered_offsets = sorted(offsets.items(), key=lambda item: item[1])

    for audio_index, audio_file in enumerate(audio_files):
        audio_path = resolve_audio_path(audio_file.path)
        start_offset = offsets.get(audio_file.id, cumulative_offset)
        duration_seconds = None
        for offset_audio_id, offset_seconds in ordered_offsets:
            if offset_audio_id != audio_file.id and offset_seconds > start_offset:
                duration_seconds = offset_seconds - start_offset
                break

        segment_results = transcribe_audio_with_provider(
            audio_path,
            duration_seconds=duration_seconds,
            chunk_mode=chunk_mode,
            number_of_speakers=number_of_speakers,
        )

        max_end_time = start_offset
        for segment in segment_results:
            shifted_segment = TranscriptSegmentResult(
                start_time=start_offset + segment.start_time,
                end_time=start_offset + segment.end_time,
                text=segment.text,
                speaker_label=segment.speaker_label,
                speaker_gender=segment.speaker_gender,
            )
            results.append((audio_file, shifted_segment))
            max_end_time = max(max_end_time, shifted_segment.end_time)

        if duration_seconds and max_end_time <= start_offset:
            max_end_time = start_offset + duration_seconds
        elif audio_index < len(audio_files) - 1 and max_end_time <= start_offset:
            max_end_time = start_offset + 0.1

        cumulative_offset = max(cumulative_offset, max_end_time)

    return results


def transcribe_audio_with_provider(
    audio_path: Path,
    duration_seconds: float | None,
    chunk_mode: bool,
    number_of_speakers: int = 0,
) -> list[TranscriptSegmentResult]:
    settings = get_settings()
    provider = settings.transcript_provider.lower().strip()

    if provider in {"volcengine", "doubao"}:
        try:
            from app.stt_providers import transcribe_with_volcengine

            return transcribe_with_volcengine(
                audio_path,
                duration_seconds=duration_seconds,
                number_of_speakers=number_of_speakers,
            ).segments
        except Exception as exc:
            raise TranscriptionError(f"Volcengine ASR failed: {exc}") from exc

    if provider == "openai":
        try:
            from app.stt_providers import transcribe_with_openai

            return transcribe_with_openai(audio_path, duration_seconds=duration_seconds).segments
        except Exception as exc:
            raise TranscriptionError(f"OpenAI transcription failed: {exc}") from exc

    if provider in {"faster_whisper", "faster-whisper", "local"}:
        return transcribe_audio_file(audio_path, realtime=False, chunk_mode=chunk_mode)

    if provider != "auto":
        raise TranscriptionError(f"Unsupported transcript provider: {settings.transcript_provider}")

    try:
        from app.stt_providers import is_volcengine_configured, transcribe_with_openai, transcribe_with_volcengine

        if is_volcengine_configured():
            return transcribe_with_volcengine(
                audio_path,
                duration_seconds=duration_seconds,
                number_of_speakers=number_of_speakers,
            ).segments
        return transcribe_with_openai(audio_path, duration_seconds=duration_seconds).segments
    except Exception:
        return transcribe_audio_file(audio_path, realtime=False, chunk_mode=chunk_mode)


def transcribe_realtime_audio_with_provider(audio_path: Path) -> list[TranscriptSegmentResult]:
    settings = get_settings()
    provider = settings.transcript_provider.lower().strip()

    if provider in {"volcengine", "doubao", "auto"}:
        try:
            from app.stt_providers import is_volcengine_configured, transcribe_with_volcengine

            if is_volcengine_configured():
                return transcribe_with_volcengine(
                    audio_path,
                    resource_id=settings.volcengine_realtime_asr_resource_id,
                ).segments
        except Exception:
            if provider in {"volcengine", "doubao"}:
                raise

    return transcribe_audio_file(audio_path, realtime=True, chunk_mode=True)


def number_of_speakers_for_meeting(meeting: Meeting | None) -> int:
    if meeting is None:
        return 0
    raw_count = (
        getattr(meeting, "participant_count", None)
        or getattr(meeting, "participants_count", None)
        or getattr(meeting, "attendee_count", None)
    )
    try:
        count = int(raw_count) if raw_count is not None else 0
    except (TypeError, ValueError):
        return 0
    if 1 <= count <= 10:
        return count
    if count > 10:
        print(f"[ASR] NumberOfSpeaker warning: participant count {count} exceeds 10, using 0")
    return 0


def next_speaker_label(existing_labels: set[str]) -> str:
    for index in range(0, 10):
        candidate = f"speaker_{index}"
        if candidate not in existing_labels:
            return candidate
    return f"speaker_{len(existing_labels)}"


def stabilize_realtime_speaker_labels(
    existing_segments: list[TranscriptSegment],
    segment_results: list[TranscriptSegmentResult],
    start_offset_seconds: float,
) -> list[TranscriptSegmentResult]:
    if not segment_results:
        return []

    existing_labels = {segment.speaker_label for segment in existing_segments if segment.speaker_label}
    last_segment = existing_segments[-1] if existing_segments else None
    provider_to_stable: dict[str, str] = {}
    stabilized: list[TranscriptSegmentResult] = []

    for index, segment in enumerate(segment_results):
        provider_label = segment.speaker_label or f"chunk_speaker_{index}"
        stable_label = provider_to_stable.get(provider_label)

        absolute_start = start_offset_seconds + segment.start_time
        if stable_label is None and index == 0 and last_segment and last_segment.speaker_label:
            gap_seconds = absolute_start - last_segment.end_time
            same_or_unknown_gender = (
                not segment.speaker_gender
                or not last_segment.speaker_gender
                or segment.speaker_gender == last_segment.speaker_gender
                or segment.speaker_gender == "unknown"
                or last_segment.speaker_gender == "unknown"
            )
            if -0.25 <= gap_seconds <= 2.5 and same_or_unknown_gender:
                stable_label = last_segment.speaker_label

        if stable_label is None:
            stable_label = next_speaker_label(existing_labels | set(provider_to_stable.values()))

        provider_to_stable[provider_label] = stable_label
        existing_labels.add(stable_label)
        stabilized.append(
            TranscriptSegmentResult(
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=segment.text,
                speaker_label=stable_label,
                speaker_gender=segment.speaker_gender,
            )
        )

    return stabilized


def transcribe_meeting(db: Session, meeting_id: str) -> list[TranscriptSegment]:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise TranscriptionError(f"Meeting not found: {meeting_id}")

    audio_files = audio_files_for_meeting(db, meeting_id)
    if not audio_files:
        raise TranscriptionError(f"No uploaded audio file found for meeting {meeting_id}.")

    meeting.status = "transcribing"
    db.commit()

    try:
        segment_results = transcribe_audio_files(db, meeting_id, audio_files, meeting=meeting)
        db.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id))

        transcript_segments = [
            TranscriptSegment(
                meeting_id=meeting_id,
                audio_file_id=audio_file.id,
                segment_index=index,
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=segment.text,
                speaker_label=segment.speaker_label,
                speaker_gender=segment.speaker_gender,
            )
            for index, (audio_file, segment) in enumerate(segment_results)
        ]
        db.add_all(transcript_segments)
        meeting.status = "transcribed"
        db.commit()
        print(f"[ASR] Transcript segments saved: {len(transcript_segments)}")

        for segment in transcript_segments:
            db.refresh(segment)
        return transcript_segments
    except Exception:
        db.rollback()
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "transcription_failed"
            db.commit()
        raise


def transcribe_audio_chunk(
    db: Session,
    meeting_id: str,
    audio_file_id: str,
    start_offset_seconds: float = 0.0,
) -> list[TranscriptSegment]:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise TranscriptionError(f"Meeting not found: {meeting_id}")

    audio_file = db.scalars(
        select(AudioFile).where(AudioFile.id == audio_file_id, AudioFile.meeting_id == meeting_id)
    ).first()
    if audio_file is None:
        raise TranscriptionError(f"Audio file not found: {audio_file_id}")

    audio_path = resolve_audio_path(audio_file.path)
    meeting.status = "transcribing"
    db.commit()

    try:
        segment_results = transcribe_realtime_audio_with_provider(audio_path)
        existing_segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.meeting_id == meeting_id)
                .order_by(TranscriptSegment.segment_index.asc())
            ).all()
        )
        segment_results = stabilize_realtime_speaker_labels(
            existing_segments,
            segment_results,
            start_offset_seconds,
        )
        last_segment = db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.segment_index.desc())
        ).first()
        next_index = (last_segment.segment_index + 1) if last_segment else 0
        transcript_segments = [
            TranscriptSegment(
                meeting_id=meeting_id,
                audio_file_id=audio_file.id,
                segment_index=next_index + index,
                start_time=start_offset_seconds + segment.start_time,
                end_time=start_offset_seconds + segment.end_time,
                text=segment.text,
                speaker_label=segment.speaker_label,
                speaker_gender=segment.speaker_gender,
            )
            for index, segment in enumerate(segment_results)
        ]
        db.add_all(transcript_segments)
        meeting.status = "transcribing"
        db.commit()

        for segment in transcript_segments:
            db.refresh(segment)
        return transcript_segments
    except Exception:
        db.rollback()
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "transcription_failed"
            db.commit()
        raise
