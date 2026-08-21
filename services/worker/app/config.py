from functools import lru_cache
import os
import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_local_database_url(value: str) -> str:
    if os.name != "nt" or os.path.exists("/.dockerenv"):
        return value

    return re.sub(
        r"@(?:db|postgres|database):5432/",
        "@127.0.0.1:5432/",
        value,
        count=1,
    )


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://"
        "meeting_agent:meeting_agent@localhost:5432/meeting_agent"
    )
    storage_dir: str = "../storage"

    whisper_model_size: str = "small"
    realtime_whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = "zh"
    whisper_initial_prompt: str | None = (
        "以下是普通话会议录音，请准确转写为简体中文，"
        "保留人名、项目名、数字和专业术语。"
    )

    transcript_provider: str = "auto"
    openai_transcription_model: str = "gpt-4o-transcribe"

    volcengine_asr_submit_url: str = (
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    )
    volcengine_asr_query_url: str = (
        "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    )
    volcengine_asr_resource_id: str = "volc.seedasr.auc"
    volcengine_realtime_asr_resource_id: str = (
        "volc.seedasr.sauc.duration"
    )
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

    # Meeting Analyst RAG
    rag_enabled: bool = True
    rag_chroma_db_dir: str | None = r"D:\codex_work\会议声纹识别\data\vector_db\gate_b1_v34_2"
    rag_collection_name: str = "meeting_analyst_rules_gate_b_v3_4_2_bge_m3_dense_v1"
    rag_embedding_model: str = r"D:\model_cache\bge-m3"
    rag_embedding_local_files_only: bool = True
    rag_top_k: int = 8
    rag_distance_threshold: float | None = None
    rag_max_context_chars: int = 12000
    rag_dataset_version: str = "meeting_analyst_rag_v2_1_1"
    rag_chunk_schema_version: str = "rag-chunk-v2.1.1"
    rag_scenario_taxonomy_version: str | None = None
    rag_retrieval_version: str | None = None

    # RAG v3.2.0 retrieval. Default off to preserve current production behavior.
    rag_v3_retrieval_enabled: bool = False
    rag_v3_final_k: int = 6
    rag_v3_fixed_policy_k: int = 1
    rag_v3_vector_candidate_multiplier: int = 4
    rag_v3_scenario_boost: float = 0.15
    rag_v3_global_scenario_boost: float = 0.05
    rag_v3_meeting_scenario_min_confidence: float = 0.7
    rag_reranker_enabled: bool = False

    # Layered RAG retrieval
    # 默认关闭，确保旧版统一 Top-K 行为保持不变。
    rag_layered_retrieval_enabled: bool = False
    rag_layered_fallback_enabled: bool = True
    rag_layered_global_fixed_ids: str = "boundary_rule_012"
    rag_layered_policy_k: int = 2
    rag_layered_dynamic_k: int = 3
    rag_layered_scenario_k: int = 2
    rag_layered_query_transcript_chars: int = 3000

    # Diagnostics
    action_validator_trace_enabled: bool = False
    action_validator_trace_dir: str | None = None

    # MeetMind Agent rollout guardrails
    agent_mode_enabled: bool = False
    agent_shadow_mode: bool = True
    agent_actions_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator(
        "database_url",
        mode="before",
    )
    @classmethod
    def normalize_database_url_for_windows_local(
        cls,
        value: object,
    ) -> object:
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
        "rag_scenario_taxonomy_version",
        "rag_retrieval_version",
        "action_validator_trace_dir",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(
        cls,
        value: object,
    ) -> object:
        if value == "":
            return None

        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
