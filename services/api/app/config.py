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
    openai_api_key: str | None = None
    openai_transcription_model: str = "gpt-4o-transcribe"
    openai_analysis_model: str = "gpt-4.1-mini"
    api_cors_origins: str = "*"
    worker_url: str = "http://127.0.0.1:8001"
    worker_request_timeout_seconds: float = 600.0
    volcengine_asr_api_key: str | None = None
    volcengine_realtime_asr_url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    volcengine_realtime_asr_resource_id: str = "volc.seedasr.sauc.duration"
    volcengine_enable_speaker_info: bool = True
    volcengine_enable_gender_detection: bool = True
    agent_mode_enabled: bool = False
    agent_shadow_mode: bool = True
    agent_actions_enabled: bool = False
    agent_proposal_auto_generation_enabled: bool = False
    agent_command_execution_enabled: bool = False
    agent_command_dry_run_only: bool = True
    agent_command_pilot_enabled: bool = False
    agent_command_pilot_tenants: str = ""
    agent_command_pilot_projects: str = ""
    agent_rollback_execution_enabled: bool = False
    agent_global_kill_switch: bool = False
    agent_grey_enabled: bool = False
    agent_grey_tenants: str = ""
    agent_grey_projects: str = ""
    agent_grey_users: str = ""
    agent_grey_percentage: int = 0
    agent_grey_project_daily_limit: int = 0
    agent_grey_user_daily_limit: int = 0
    agent_grey_concurrency_limit: int = 0
    agent_grey_window_start: str = ""
    agent_grey_window_end: str = ""
    agent_grey_manual_paused: bool = False
    agent_paused_tenants: str = ""
    agent_paused_projects: str = ""
    agent_circuit_consecutive_failures: int = 0
    agent_circuit_version_conflict_rate: float = 0.0
    agent_circuit_rollback_failures: int = 0
    agent_circuit_recovered_after: str = ""
    agent_local_auth_enabled: bool = False
    agent_local_auth_tenant_id: str = "default-tenant"
    agent_local_auth_project_id: str = "default-project"
    agent_local_auth_token_ttl_hours: int = 24

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

    @property
    def cors_origins(self) -> list[str]:
        if self.api_cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def command_pilot_tenant_set(self) -> set[str]:
        return parse_csv_set(self.agent_command_pilot_tenants)

    @property
    def command_pilot_project_set(self) -> set[str]:
        return parse_csv_set(self.agent_command_pilot_projects)

    @property
    def agent_grey_tenant_set(self) -> set[str]:
        return parse_csv_set(self.agent_grey_tenants)

    @property
    def agent_grey_project_set(self) -> set[str]:
        return parse_csv_set(self.agent_grey_projects)

    @property
    def agent_grey_user_set(self) -> set[str]:
        return parse_csv_set(self.agent_grey_users)

    @property
    def agent_paused_tenant_set(self) -> set[str]:
        return parse_csv_set(self.agent_paused_tenants)

    @property
    def agent_paused_project_set(self) -> set[str]:
        return parse_csv_set(self.agent_paused_projects)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def parse_csv_set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}
