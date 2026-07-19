from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://meeting_agent:meeting_agent@localhost:5432/meeting_agent"
    storage_dir: str = "../storage"
    openai_api_key: str | None = None
    openai_transcription_model: str = "gpt-4o-transcribe"
    openai_analysis_model: str = "gpt-4.1-mini"
    api_cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        if self.api_cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
