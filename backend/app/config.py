"""Server-side configuration. Never serialize this object into an API response."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    mode: str = "mock"
    api_key: str = field(default="", repr=False)
    model: str = "gemini-3.5-flash-lite"
    max_output_tokens: int = 4096
    timeout_seconds: float = 45
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 64

    def validate_gemini(self):
        if not self.api_key:
            raise ConfigurationError("서버 .env에 GEMINI_API_KEY를 설정해 주세요.")
        if not re.fullmatch(r"gemini-[a-zA-Z0-9._-]{1,100}", self.model):
            raise ConfigurationError("GEMINI_MODEL에는 공식 모델 ID를 설정해 주세요.")


def get_settings() -> Settings:
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    # AHA_AI_MODE is a backwards-compatible alias. Explicit conflicts fail closed.
    provider, legacy = values.get("AHA_AI_PROVIDER"), values.get("AHA_AI_MODE")
    if provider and legacy and provider != legacy:
        raise ConfigurationError("AHA_AI_PROVIDER와 기존 AHA_AI_MODE 설정이 달라요. 한 항목만 사용하거나 같은 값으로 설정해 주세요.")
    mode = provider or legacy or "mock"
    if mode not in {"mock", "gemini", "elice"}:
        raise ConfigurationError("AHA_AI_PROVIDER는 mock, gemini 또는 elice로 설정해 주세요.")
    try:
        tokens = int(values.get("GEMINI_MAX_OUTPUT_TOKENS", "4096"))
        timeout = float(values.get("AI_TIMEOUT_SECONDS", "45"))
        ttl = int(values.get("AHA_CACHE_TTL_SECONDS", "300"))
        entries = int(values.get("AHA_CACHE_MAX_ENTRIES", "64"))
        if not 500 <= tokens <= 8192 or not 1 <= timeout <= 90 or not 0 <= ttl <= 3600 or not 1 <= entries <= 128:
            raise ValueError
    except (ValueError, TypeError):
        raise ConfigurationError("출력 토큰 500–8192, 제한 시간 1–90초, 캐시 TTL 0–3600초·개수 1–128로 설정해 주세요.") from None
    return Settings(mode=mode, api_key=values.get("GEMINI_API_KEY", "") or "",
                    model=values.get("GEMINI_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite",
                    max_output_tokens=tokens, timeout_seconds=timeout,
                    cache_ttl_seconds=ttl, cache_max_entries=entries)
