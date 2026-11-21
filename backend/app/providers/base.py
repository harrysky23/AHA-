from dataclasses import dataclass, field
from typing import Protocol

from ..schemas import LessonSpec
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


class AIProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult: ...
