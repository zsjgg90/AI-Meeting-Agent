import requests
import time

from app.config import get_settings
from app.observability import log_event


def build_chat_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/api/chat"):
        return normalized
    return f"{normalized}/api/chat"


def build_ollama_options(
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    num_ctx: int | None = None,
    seed: int | None = None,
) -> dict:
    settings = get_settings()
    resolved_seed = settings.ollama_seed if seed is None else seed
    options = {
        "temperature": settings.ollama_temperature if temperature is None else temperature,
        "top_p": settings.ollama_top_p if top_p is None else top_p,
        "num_ctx": settings.ollama_context if num_ctx is None else num_ctx,
    }
    if resolved_seed is not None:
        options["seed"] = resolved_seed
    return options


def build_ollama_format(response_format: str | None = None) -> str | None:
    settings = get_settings()
    return settings.ollama_format if response_format is None else response_format


class OllamaClient:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        seed: int | None = None,
        response_format: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        self.model = model or settings.ollama_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.url = build_chat_url(self.base_url)
        self.temperature = settings.ollama_temperature if temperature is None else temperature
        self.top_p = settings.ollama_top_p if top_p is None else top_p
        self.num_ctx = settings.ollama_context if num_ctx is None else num_ctx
        self.seed = settings.ollama_seed if seed is None else seed
        self.response_format = settings.ollama_format if response_format is None else response_format
        self.timeout = settings.ollama_timeout_seconds if timeout is None else timeout

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        if not prompt or not prompt.strip():
            raise ValueError(
                "Ollama prompt cannot be empty"
            )

        if system_prompt is None:
            system_prompt = (
                "你是专业 AI Meeting Analyst。"
                "你必须严格输出合法 JSON。"
                "不要输出 Markdown。"
                "不要输出解释或其他多余文本。"
                "所有事实必须来自会议原文。"
            )

        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "options": build_ollama_options(
                temperature=self.temperature,
                top_p=self.top_p,
                num_ctx=self.num_ctx,
                seed=self.seed,
            ),
        }
        if self.response_format:
            payload["format"] = self.response_format

        print(
            f"[OLLAMA] Calling model: {self.model}"
        )
        print(
            f"[OLLAMA] base_url={self.base_url} temperature={self.temperature} top_p={self.top_p} seed={self.seed} format={self.response_format} context={self.num_ctx}"
        )
        log_event(
            "ollama.request",
            model_name=self.model,
            base_url=self.base_url,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
            response_format=self.response_format,
            context=self.num_ctx,
            timeout_seconds=self.timeout,
            prompt=prompt,
        )

        started_at = time.perf_counter()
        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=self.timeout,
            )
        except Exception as exc:
            log_event(
                "ollama.failed",
                level="error",
                model_name=self.model,
                base_url=self.base_url,
                timeout_seconds=self.timeout,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        response.raise_for_status()

        data = response.json()
        log_event(
            "ollama.completed",
            model_name=self.model,
            base_url=self.base_url,
            timeout_seconds=self.timeout,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
            response_format=self.response_format,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

        if "message" not in data:
            raise RuntimeError(
                f"Invalid Ollama response: {data}"
            )

        content = data["message"].get(
            "content",
            "",
        )

        if not content:
            raise RuntimeError(
                "Ollama returned empty content"
            )

        return content
