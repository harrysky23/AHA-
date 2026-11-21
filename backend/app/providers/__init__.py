"""AI providers share a data-only lesson contract; Elice intentionally has no HTTP implementation."""
from ..config import Settings
from .base import AIProvider
from .elice import EliceProvider
from .gemini import GeminiProvider
from .mock import MockProvider


def get_provider(settings: Settings) -> AIProvider:
    return {"mock": MockProvider, "gemini": GeminiProvider, "elice": EliceProvider}[settings.mode](settings)
