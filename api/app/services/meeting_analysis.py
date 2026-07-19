import json
from typing import Any

from openai import OpenAI

from app.config import get_settings
from app.services.transcription import OpenAIConfigurationError


MEETING_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "speaker_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speaker": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["speaker", "text"],
            },
        },
        "summary": {"type": "string"},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["task", "owner", "due_date", "source"],
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "decision": {"type": "string"},
                    "reason": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["decision", "reason", "source"],
            },
        },
        "rag_chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speaker": {"type": "string"},
                    "content": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "kind": {"type": "string"},
                        },
                        "required": ["kind"],
                    },
                },
                "required": ["speaker", "content", "metadata"],
            },
        },
    },
    "required": ["speaker_segments", "summary", "action_items", "decisions", "rag_chunks"],
}


def analyze_meeting(transcript: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_analysis_model,
        input=[
            {
                "role": "system",
                "content": (
                    "You analyze meeting transcripts for an MVP meeting AI agent. "
                    "Infer speaker turns as Speaker A, Speaker B, Speaker C, etc. "
                    "Do not invent names. If owner or due date is unknown, use empty string. "
                    "Return concise Chinese output unless the transcript is clearly in another language."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Analyze this meeting transcript. Generate speaker segments, summary, "
                    "action items, decisions, and RAG-ready chunks.\n\n"
                    f"Transcript:\n{transcript}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "meeting_analysis",
                "schema": MEETING_ANALYSIS_SCHEMA,
                "strict": True,
            }
        },
    )

    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("OpenAI analysis response did not include output_text.")
    return json.loads(output_text)
