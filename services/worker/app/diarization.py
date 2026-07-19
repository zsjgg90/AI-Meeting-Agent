from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


class DiarizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiarizationSegment:
    start_time: float
    end_time: float
    speaker_label: str


def speaker_label_for_index(index: int) -> str:
    alphabet_size = 26
    quotient, remainder = divmod(index, alphabet_size)
    suffix = chr(ord("A") + remainder)
    if quotient == 0:
        return f"Speaker {suffix}"
    return f"Speaker {suffix}{quotient + 1}"


def run_diarization(audio_path: Path) -> list[DiarizationSegment]:
    settings = get_settings()
    if not settings.huggingface_token:
        raise DiarizationError("HUGGINGFACE_TOKEN is not configured for pyannote.audio diarization.")

    try:
        from pyannote.audio import Pipeline
    except Exception as exc:
        raise DiarizationError(f"pyannote.audio diarization is unavailable: {exc}") from exc

    pipeline = Pipeline.from_pretrained(
        settings.pyannote_pipeline,
        use_auth_token=settings.huggingface_token,
    )
    diarization_kwargs: dict[str, int] = {}
    if settings.pyannote_num_speakers is not None:
        diarization_kwargs["num_speakers"] = settings.pyannote_num_speakers
    if settings.pyannote_min_speakers is not None:
        diarization_kwargs["min_speakers"] = settings.pyannote_min_speakers
    if settings.pyannote_max_speakers is not None:
        diarization_kwargs["max_speakers"] = settings.pyannote_max_speakers

    diarization = pipeline(str(audio_path), **diarization_kwargs)
    raw_speaker_to_label: dict[str, str] = {}
    results: list[DiarizationSegment] = []

    for turn, _track, raw_speaker in diarization.itertracks(yield_label=True):
        if raw_speaker not in raw_speaker_to_label:
            raw_speaker_to_label[raw_speaker] = speaker_label_for_index(len(raw_speaker_to_label))
        results.append(
            DiarizationSegment(
                start_time=float(turn.start),
                end_time=float(turn.end),
                speaker_label=raw_speaker_to_label[raw_speaker],
            )
        )

    return sorted(results, key=lambda segment: (segment.start_time, segment.end_time))


def overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))
