from ..config import Settings
from ..services.mock import generate_mock
from .base import GenerationInput, ProviderResult


class MockProvider:
    name = "mock"
    model = "secant-tangent-fixed-v1"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult:
        return ProviderResult(generate_mock(request.concept, request.question, request.material), self.model)
