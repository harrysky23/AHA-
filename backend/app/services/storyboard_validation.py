from ..providers.base import StoryboardInput
from ..storyboard_schema import StoryboardSpec, verify_storyboard_sources
from .errors import LearningError
from .validation import load_json


def validate_storyboard(spec: StoryboardSpec, request: StoryboardInput) -> StoryboardSpec:
    try:
        # Revalidate provider data, not merely the JSON parser path.
        checked = StoryboardSpec.model_validate(spec.model_dump())
        if checked.duration_seconds != request.target_duration_seconds or checked.student_level != request.student_level:
            raise ValueError("Output duration or student level differs from request")
        verify_storyboard_sources(checked, request.material.pages)
        return checked
    except (ValueError, TypeError, AttributeError):
        raise LearningError("invalid_storyboard_spec", "스토리보드의 장면 시간·시각화 파라미터·참조 ID·자료 인용 또는 요청 조건 검증을 통과하지 못했어요. 다시 시도하거나 mock 예제를 이용해 주세요.", 502) from None


def parse_storyboard(content: str, request: StoryboardInput) -> StoryboardSpec:
    try:
        spec = StoryboardSpec.model_validate(load_json(content))
    except (ValueError, TypeError, RecursionError):
        raise LearningError("invalid_storyboard_spec", "스토리보드 JSON의 형식·장면 시간·시각화 제약을 확인하지 못했어요. 실행 가능한 코드나 임의 파라미터는 허용하지 않아요.", 502) from None
    return validate_storyboard(spec, request)
