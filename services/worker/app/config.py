from functools import lru_cache
import os
import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_local_database_url(value: str) -> str:
    if os.name != "nt" or os.path.exists("/.dockerenv"):
        return value
    return re.sub(r"@(?:db|postgres|database):5432/", "@127.0.0.1:5432/", value, count=1)


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://meeting_agent:meeting_agent@localhost:5432/meeting_agent"
    storage_dir: str = "../storage"
    whisper_model_size: str = "small"
    realtime_whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = "zh"
    whisper_initial_prompt: str | None = "以下是普通话会议录音，请准确转写为简体中文，保留人名、项目名、数字和专业术语。"
    transcript_provider: str = "auto"
    openai_transcription_model: str = "gpt-4o-transcribe"
    volcengine_asr_submit_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    volcengine_asr_query_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    volcengine_asr_resource_id: str = "volc.seedasr.auc"
    volcengine_realtime_asr_resource_id: str = "volc.seedasr.sauc.duration"
    volcengine_enable_speaker_info: bool = True
    volcengine_enable_gender_detection: bool = True
    volcengine_asr_poll_interval_seconds: float = 5.0
    volcengine_asr_timeout_seconds: float = 600.0
    huggingface_token: str | None = None
    pyannote_pipeline: str = "pyannote/speaker-diarization-3.1"
    pyannote_num_speakers: int | None = None
    pyannote_min_speakers: int | None = None
    pyannote_max_speakers: int | None = None
    openai_api_key: str | None = None
    openai_summary_model: str = "gpt-4.1-mini"
    ollama_model: str = "qwen3:14b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_temperature: float = 0.0
    ollama_top_p: float = 0.2
    ollama_seed: int | None = 42
    ollama_format: str | None = "json"
    ollama_context: int = 8192
    ollama_timeout_seconds: float = 600.0
    rag_enabled: bool = True
    rag_chroma_db_dir: str | None = None
    rag_collection_name: str = "meeting_analyst_rules"
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_embedding_local_files_only: bool = True
    rag_top_k: int = 8
    rag_distance_threshold: float | None = None
    rag_max_context_chars: int = 12000
    rag_dataset_version: str = "meeting_analyst_rag_v1"
    rag_chunk_schema_version: str = "rag-chunk-v1"
    agent_mode_enabled: bool = False
    agent_shadow_mode: bool = True
    agent_actions_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "database_url",
        mode="before",
    )
    @classmethod
    def normalize_database_url_for_windows_local(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_local_database_url(value)
        return value

    @field_validator(
        "whisper_language",
        "whisper_initial_prompt",
        "transcript_provider",
        "openai_transcription_model",
        "volcengine_asr_submit_url",
        "volcengine_asr_query_url",
        "volcengine_asr_resource_id",
        "volcengine_realtime_asr_resource_id",
        "huggingface_token",
        "openai_api_key",
        "pyannote_num_speakers",
        "pyannote_min_speakers",
        "pyannote_max_speakers",
        "ollama_model",
        "ollama_base_url",
        "ollama_seed",
        "ollama_format",
        "rag_chroma_db_dir",
        "rag_distance_threshold",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
