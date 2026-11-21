from dataclasses import dataclass, field
from typing import Protocol

from ..schemas import LessonSpec
from ..storyboard_schema import StoryboardSpec
from ..services.materials import MaterialContext


@dataclass
class GenerationInput:
    concept: str
    question: str
    material: MaterialContext


@dataclass
class ProviderResult:
    spec: LessonSpec
    model: str
    usage: dict = field(default_factory=dict)


@dataclass
class StoryboardInput(GenerationInput):
    target_duration_seconds: int = 45
    student_level: str = "high_school"


@dataclass
class StoryboardResult:
    spec: StoryboardSpec
    model: str
    usage: dict = field(default_factory=dict)


class AIProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult: ...

    async def generate_storyboard(self, request: StoryboardInput, request_id: str) -> StoryboardResult: ...
