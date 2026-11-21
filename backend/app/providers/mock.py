from ..config import Settings
from ..services.mock import generate_mock
from .base import GenerationInput, ProviderResult, StoryboardInput, StoryboardResult


class MockProvider:
    name = "mock"
    model = "secant-tangent-fixed-v1"
    storyboard_model = "storyboard-templates-v1"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult:
        return ProviderResult(generate_mock(request.concept, request.question, request.material), self.model)

    async def generate_storyboard(self, request: StoryboardInput, request_id: str) -> StoryboardResult:
        from ..services.storyboard_mock import generate_mock_storyboard
        return StoryboardResult(generate_mock_storyboard(request), self.storyboard_model)
