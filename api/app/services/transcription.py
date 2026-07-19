from pathlib import Path

from openai import OpenAI

from app.config import get_settings


class OpenAIConfigurationError(RuntimeError):
    pass


def transcribe_audio(audio_path: str | Path) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=settings.openai_api_key)
    with Path(audio_path).open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=audio_file,
        )

    text = getattr(transcript, "text", None)
    if not text:
        raise RuntimeError("OpenAI transcription response did not include text.")
    return text
