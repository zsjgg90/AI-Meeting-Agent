from pathlib import Path

from app.config import get_settings


def resolve_root_env_value(key: str) -> str | None:
    root_env = Path(__file__).resolve().parents[3] / ".env"
    if not root_env.exists():
        return None

    for raw_line in root_env.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'") or None
    return None


def resolve_volcengine_api_key() -> str | None:
    settings = get_settings()
    return settings.volcengine_asr_api_key or resolve_root_env_value("VOLCENGINE_ASR_API_KEY")
