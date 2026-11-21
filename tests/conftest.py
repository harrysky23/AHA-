import pytest

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.services.cache import lesson_cache
from backend.app.services.storyboard import storyboard_cache


@pytest.fixture(autouse=True)
def isolate_settings():
    # Ordinary tests must never spend tokens, even when a developer has a real .env.
    app.dependency_overrides[get_settings] = lambda: Settings()
    lesson_cache.clear()
    storyboard_cache.clear()
    yield
    app.dependency_overrides.clear()
    lesson_cache.clear()
    storyboard_cache.clear()
