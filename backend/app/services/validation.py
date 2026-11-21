"""Provider-independent strict JSON, scope, known-math and source-quote validation."""
import json

from pydantic import ValidationError

from ..schemas import LessonSpec, verify_grounding
from .errors import LearningError
from .materials import MaterialContext


def reject_constants(value):
    raise ValueError("Non-finite JSON number")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def load_json(content):
    return json.loads(content, parse_constant=reject_constants, object_pairs_hook=unique_object)


def parse_spec(content: str, material: MaterialContext) -> LessonSpec:
    try:
        raw = load_json(content)
        spec = LessonSpec.model_validate(raw)
        if spec.scope == "unsupported":
            raise LearningError("unsupported_scope", "현재는 f(x)=x², a=1의 미분계수·할선→접선만 지원해요. 기본 예제로 학습할 수 있어요.", 422)
        verify_grounding(spec, material.pages)
        return spec
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise LearningError("invalid_lesson_spec", "AI 학습 명세의 형식·수학값·자료 인용을 확인하지 못했어요. 다시 시도하거나 기본 예제를 열어 주세요.") from None
