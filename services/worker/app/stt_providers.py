import base64
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from openai import OpenAI

from app.config import get_settings
from app.secrets import resolve_openai_api_key, resolve_root_env_value
from app.transcription import TranscriptSegmentResult, normalize_transcript_text


class STTProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class STTProviderResult:
    provider: str
    model: str
    segments: list[TranscriptSegmentResult]


def transcribe_with_openai(audio_path: Path, duration_seconds: float | None = None) -> STTProviderResult:
    settings = get_settings()
    api_key = resolve_openai_api_key()
    if not api_key:
        raise STTProviderError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=api_key)
    with audio_path.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=audio_file,
            language=settings.whisper_language or "zh",
            prompt=settings.whisper_initial_prompt or None,
        )

    text = normalize_transcript_text(getattr(transcript, "text", "") or "")
    if not text:
        raise STTProviderError("OpenAI transcription returned empty text.")

    return STTProviderResult(
        provider="openai",
        model=settings.openai_transcription_model,
        segments=[
            TranscriptSegmentResult(
                start_time=0.0,
                end_time=max(duration_seconds or 0.0, 0.1),
                text=text,
                speaker_label=None,
                speaker_gender=None,
            )
        ],
    )


def resolve_volcengine_api_key() -> str | None:
    return resolve_root_env_value("VOLCENGINE_ASR_API_KEY")


def is_volcengine_configured() -> bool:
    return bool(resolve_volcengine_api_key())


def audio_format(audio_path: Path) -> str:
    extension = audio_path.suffix.lower().lstrip(".")
    if extension == "m4a":
        return "mp4"
    if extension in {"mp3", "wav", "aac", "ogg", "webm", "mp4"}:
        return extension
    return "mp4"


def volcengine_headers(
    request_id: str,
    sequence: int = -1,
    task_id: str | None = None,
    resource_id: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    api_key = resolve_volcengine_api_key()
    if not api_key:
        raise STTProviderError("VOLCENGINE_ASR_API_KEY is not configured.")

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id or settings.volcengine_asr_resource_id,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": str(sequence),
    }
    if task_id:
        headers["X-Api-Task-Id"] = task_id
    return headers


def status_from_headers(response: httpx.Response) -> str:
    return response.headers.get("X-Api-Status-Code") or response.headers.get("x-api-status-code") or ""


def message_from_response(response: httpx.Response, payload: dict | None = None) -> str:
    payload = payload or {}
    return (
        response.headers.get("X-Api-Message")
        or response.headers.get("x-api-message")
        or str(payload.get("message") or payload.get("error") or "")
    )


def has_volcengine_transcript(payload: dict) -> bool:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    utterances = result.get("utterances") or result.get("utterance") or payload.get("utterances")
    text = result.get("text") or result.get("transcript") or payload.get("text")
    return bool((isinstance(utterances, list) and utterances) or (isinstance(text, str) and text.strip()))


def normalize_speaker_label(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("spk_"):
        suffix = lower.removeprefix("spk_")
        if suffix.isdigit():
            return f"speaker_{int(suffix)}"
    if lower.startswith("speaker_"):
        suffix = lower.removeprefix("speaker_")
        if suffix.isdigit():
            return f"speaker_{int(suffix)}"
    speaker_match = re.match(r"^speaker\s*([0-9]+)$", lower)
    if speaker_match:
        return f"speaker_{int(speaker_match.group(1))}"
    if lower.isdigit():
        return f"speaker_{int(lower)}"
    return raw


def normalize_speaker_label_or_unknown(value: object) -> str:
    return normalize_speaker_label(value) or "speaker_unknown"


def normalize_gender(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in {"male", "man", "m", "男", "男性"}:
        return "male"
    if raw in {"female", "woman", "f", "女", "女性"}:
        return "female"
    if "male" in raw and "female" not in raw:
        return "male"
    if "female" in raw:
        return "female"
    return "unknown"


def task_id_from_response(response: httpx.Response, payload: dict) -> str | None:
    return (
        response.headers.get("X-Api-Task-Id")
        or response.headers.get("x-api-task-id")
        or payload.get("task_id")
        or payload.get("taskId")
        or payload.get("id")
    )


def normalize_number_of_speakers(value: object) -> int:
    try:
        count = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    if 1 <= count <= 10:
        return count
    if count > 10:
        print(f"[ASR] NumberOfSpeaker warning: participant count {count} exceeds 10, using 0")
    return 0


def build_volcengine_submit_payload(audio_path: Path, number_of_speakers: int = 0) -> dict:
    settings = get_settings()
    audio_data = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    normalized_number_of_speakers = normalize_number_of_speakers(number_of_speakers)
    return {
        "user": {"uid": "meeting-agent"},
        "audio": {
            "data": audio_data,
            "format": audio_format(audio_path),
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "enable_speaker_info": settings.volcengine_enable_speaker_info,
            "show_utterances": True,
            "NumberOfSpeaker": normalized_number_of_speakers,
            "enable_gender_detection": settings.volcengine_enable_gender_detection,
        },
    }


def submit_volcengine_task(
    audio_path: Path,
    request_id: str,
    resource_id: str | None = None,
    number_of_speakers: int = 0,
) -> str | None:
    settings = get_settings()
    payload = build_volcengine_submit_payload(audio_path, number_of_speakers=number_of_speakers)
    print("[ASR] Speaker diarization enabled")
    print(f"[ASR] NumberOfSpeaker: {payload['request']['NumberOfSpeaker']}")

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            settings.volcengine_asr_submit_url,
            headers=volcengine_headers(request_id, resource_id=resource_id),
            json=payload,
        )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        status = status_from_headers(response)
        message = message_from_response(response, payload)
        detail = ", ".join(part for part in [f"http_status={response.status_code}", f"api_status={status}" if status else "", message] if part)
        raise STTProviderError(f"Volcengine ASR submit failed: {detail}.")

    task_id = task_id_from_response(response, payload)

    status = status_from_headers(response)
    if status and status not in {"20000000", "20000001", "20000002"}:
        raise STTProviderError(f"Volcengine ASR submit failed with status code {status}.")
    return task_id


def seconds_from_volcengine_time(value: object, duration_seconds: float | None = None, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    if duration_seconds is not None and duration_seconds > 0 and numeric > duration_seconds + 5:
        return numeric / 1000.0
    if duration_seconds is None and numeric > 3600:
        return numeric / 1000.0
    return numeric


def poll_volcengine_task(request_id: str, task_id: str | None = None, resource_id: str | None = None) -> dict:
    settings = get_settings()
    deadline = time.monotonic() + settings.volcengine_asr_timeout_seconds
    with httpx.Client(timeout=60.0) as client:
        while time.monotonic() < deadline:
            response = client.post(
                settings.volcengine_asr_query_url,
                headers=volcengine_headers(request_id, task_id=task_id, resource_id=resource_id),
                json={},
            )
            if response.status_code >= 400:
                raise STTProviderError(f"Volcengine ASR query failed with status {response.status_code}.")

            payload = response.json() if response.content else {}
            status = status_from_headers(response)
            if has_volcengine_transcript(payload):
                return payload
            if status and status not in {"20000001", "20000002"}:
                message = response.headers.get("X-Api-Message") or payload.get("message") or status
                raise STTProviderError(f"Volcengine ASR query failed: {message}.")
            time.sleep(settings.volcengine_asr_poll_interval_seconds)
    raise STTProviderError("Volcengine ASR query timed out.")


def extract_volcengine_segments(payload: dict, duration_seconds: float | None = None) -> list[TranscriptSegmentResult]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    utterances = result.get("utterances") or result.get("utterance") or []
    segments: list[TranscriptSegmentResult] = []

    if isinstance(utterances, list):
        print(f"[ASR] Utterances received: {len(utterances)}")
        for index, item in enumerate(utterances):
            if not isinstance(item, dict):
                continue
            text = normalize_transcript_text(str(item.get("text") or item.get("utterance") or ""))
            if not text:
                continue
            start_value = item.get("start_time") or item.get("start") or item.get("begin_time") or 0
            end_value = item.get("end_time") or item.get("end") or item.get("stop_time") or start_value
            start_time = seconds_from_volcengine_time(start_value, duration_seconds=duration_seconds, fallback=float(index))
            end_time = seconds_from_volcengine_time(end_value, duration_seconds=duration_seconds, fallback=start_time + 1.0)
            additions = item.get("additions") if isinstance(item.get("additions"), dict) else {}
            speaker = (
                additions.get("speaker")
                or item.get("speaker")
                or item.get("speaker_id")
                or item.get("speaker_label")
                or item.get("speaker_info")
            )
            speaker_info = item.get("speaker_info") if isinstance(item.get("speaker_info"), dict) else {}
            gender = (
                additions.get("gender")
                or item.get("gender")
                or item.get("speaker_gender")
                or item.get("gender_label")
                or speaker_info.get("gender")
            )
            segments.append(
                TranscriptSegmentResult(
                    start_time=start_time,
                    end_time=max(end_time, start_time + 0.1),
                    text=text,
                    speaker_label=normalize_speaker_label_or_unknown(speaker),
                    speaker_gender=normalize_gender(gender),
                )
            )

    if segments:
        speaker_labels = {segment.speaker_label for segment in segments if segment.speaker_label and segment.speaker_label != "speaker_unknown"}
        if speaker_labels:
            print(f"[ASR] Detected speakers: {len(speaker_labels)}")
        else:
            print("[ASR] Speaker info missing, falling back to default speaker")
        return segments

    text = normalize_transcript_text(str(result.get("text") or result.get("transcript") or payload.get("text") or ""))
    if not text:
        raise STTProviderError("Volcengine ASR response did not include transcript text.")
    return [
        TranscriptSegmentResult(
            start_time=0.0,
            end_time=max(duration_seconds or 0.0, 0.1),
            text=text,
            speaker_label=None,
            speaker_gender=None,
        )
    ]


def transcribe_with_volcengine(
    audio_path: Path,
    duration_seconds: float | None = None,
    resource_id: str | None = None,
    number_of_speakers: int = 0,
) -> STTProviderResult:
    settings = get_settings()
    active_resource_id = resource_id or settings.volcengine_asr_resource_id
    request_id = str(uuid.uuid4())
    task_id = submit_volcengine_task(
        audio_path,
        request_id,
        resource_id=active_resource_id,
        number_of_speakers=number_of_speakers,
    )
    payload = poll_volcengine_task(request_id, task_id, resource_id=active_resource_id)
    segments = extract_volcengine_segments(payload, duration_seconds=duration_seconds)
    return STTProviderResult(
        provider="volcengine",
        model=active_resource_id,
        segments=segments,
    )
