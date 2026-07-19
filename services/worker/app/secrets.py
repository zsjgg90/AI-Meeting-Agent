from pathlib import Path

from app.config import get_settings


def read_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            clean_line = line.strip()
            if not clean_line or clean_line.startswith("#") or "=" not in clean_line:
                continue
            name, value = clean_line.split("=", maxsplit=1)
            if name.strip() == key:
                clean_value = value.strip().strip('"').strip("'")
                return clean_value or None
    except OSError:
        return None
    return None


def resolve_openai_api_key() -> str | None:
    settings = get_settings()
    if settings.openai_api_key:
        return settings.openai_api_key

    return resolve_root_env_value("OPENAI_API_KEY")


def resolve_root_env_value(key: str) -> str | None:
    # The local dev root .env also contains Docker-only values. Read only the
    # secret needed by OpenAI callers so local DB/storage defaults remain intact.
    root_env = Path(__file__).resolve().parents[3] / ".env"
    return read_env_value(root_env, key)
