from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.analysis_contract import ANALYSIS_SCHEMA_VERSION


MEETING_ANALYST_PROMPT_ID = "meeting-analyst"
MEETING_ANALYST_PROMPT_VERSION = "meeting-analyst-v1"


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    prompt_version: str
    schema_version: str
    path: Path
    description: str


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


MEETING_ANALYST_PROMPT = PromptSpec(
    prompt_id=MEETING_ANALYST_PROMPT_ID,
    prompt_version=MEETING_ANALYST_PROMPT_VERSION,
    schema_version=ANALYSIS_SCHEMA_VERSION,
    path=PROMPT_DIR / "meeting_analyst_qwen3.md",
    description="Formal Qwen3 + RAG six-dimension meeting analysis prompt.",
)


@lru_cache
def load_prompt_template(prompt_version: str) -> str:
    if prompt_version != MEETING_ANALYST_PROMPT.prompt_version:
        raise ValueError(f"Unknown prompt version: {prompt_version}")
    return MEETING_ANALYST_PROMPT.path.read_text(encoding="utf-8")


def get_meeting_analyst_prompt_spec() -> PromptSpec:
    return MEETING_ANALYST_PROMPT
