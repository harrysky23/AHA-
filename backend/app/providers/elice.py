from ..config import Settings
from ..services.errors import LearningError
from .base import GenerationInput, ProviderResult, StoryboardInput, StoryboardResult


class EliceProvider:
    """Reserved implementation: enabling this mode must never send a network request."""
    name = "elice"
    model = "not-connected"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult:
        raise LearningError("elice_not_implemented", "Elice는 향후 연결 예정이에요. 실제 사용할 공식 API 사양을 확정하기 전에는 호출하지 않아요. mock 또는 gemini 모드를 사용해 주세요.", 503)

    async def generate_storyboard(self, request: StoryboardInput, request_id: str) -> StoryboardResult:
        raise LearningError("elice_not_implemented", "Elice 스토리보드 생성은 아직 연결하지 않았어요. mock 또는 gemini 모드를 사용해 주세요.", 503)
