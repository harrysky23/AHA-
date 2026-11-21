import logging
from uuid import uuid4

from ..config import Settings
from ..providers import get_provider
from ..providers.base import StoryboardInput, StoryboardResult
from ..storyboard_schema import StoryboardSpec
from .cache import LessonCache
from .errors import LearningError
from .materials import analyze_material
from . import storyboard_prompts
from .storyboard_validation import validate_storyboard

logger = logging.getLogger("aha.generation")
storyboard_cache: LessonCache[StoryboardResult] = LessonCache()


def storyboard_cache_key(settings: Settings, provider, request: StoryboardInput) -> str:
    return storyboard_cache.fingerprint({"namespace":"storyboard", "provider":provider.name,
        "model":getattr(provider,"storyboard_model",provider.model),
        "credential":storyboard_cache.fingerprint({"credential":settings.api_key}),
        "prompt_version":storyboard_prompts.STORYBOARD_PROMPT_VERSION,
        "schema":StoryboardSpec.model_json_schema(), "max_output_tokens":settings.storyboard_max_output_tokens,
        "messages":storyboard_prompts.build_storyboard_messages(request)})


async def create_storyboard(settings: Settings, concept: str, question: str, material: dict | None,
                            file_data: bytes | None, target_duration_seconds: int = 45,
                            student_level: str = "high_school", *, on_stage=None) -> dict:
    request_id = uuid4().hex
    logger.info("request_id=%s mode=%s task=storyboard event=start",request_id,settings.mode)
    try:
        if on_stage:
            on_stage("analyzing")
        context = await analyze_material(file_data,material["content_type"] if material else None)
        if on_stage:
            on_stage("storyboard")
        # Keep Phase 2's material response text unchanged; only this endpoint is general.
        if context.status == "no_material":
            context.message = "학습 자료 없이 입력한 개념·질문으로 스토리보드를 구성해요. 자료가 없는 가정은 별도로 표시해요."
        request = StoryboardInput(concept,question,context,target_duration_seconds,student_level)
        provider = get_provider(settings)

        async def generate_validated():
            result = await provider.generate_storyboard(request,request_id)
            result.spec = validate_storyboard(result.spec,request)
            return result

        result, cache_status = await storyboard_cache.get_or_create(
            storyboard_cache_key(settings,provider,request),generate_validated,settings.cache_ttl_seconds,settings.cache_max_entries)
        logger.info("request_id=%s mode=%s task=storyboard event=validated cache=%s",request_id,settings.mode,cache_status)
    except LearningError as exc:
        logger.warning("request_id=%s mode=%s task=storyboard event=failed code=%s",request_id,settings.mode,exc.code)
        raise
    except (ValueError, TypeError, AttributeError, RecursionError):
        logger.warning("request_id=%s mode=%s task=storyboard event=failed code=invalid_storyboard_spec",request_id,settings.mode)
        raise LearningError("invalid_storyboard_spec","스토리보드 명세의 구조·시간·시각화 검증에 실패했어요. mock 예제나 기존 학습 데모를 이용할 수 있어요.",502) from None
    return {"mode":settings.mode,"format":"storyboard","storyboard":result.spec.model_dump(),
        "generation":{"provider":provider.name,"model":result.model,"request_id":request_id,"status":"validated",
            "external_ai":settings.mode=="gemini","cached":cache_status=="hit","cache_status":cache_status,
            "usage":{} if cache_status=="hit" else result.usage,"prompt_version":storyboard_prompts.STORYBOARD_PROMPT_VERSION},
        "grounding":context.public(),"material":({**material,"text_extracted":bool(context.pages),
            "analyzed":settings.mode=="gemini" and bool(context.pages),
            "sent_to_provider":settings.mode=="gemini" and bool(context.pages) and cache_status!="hit"} if material else None),
        "verification":{"schema":"passed","timeline":"passed","references":"passed",
            "source_quotes":"matched" if result.spec.sources else "not_used",
            "notice":"명세·시간·참조·인용 일치 검증이며, 내용 전체의 사실성이나 실제 발화 길이를 검증한 결과는 아니에요."},
        "rendering":{"status":"not_implemented","video_generated":False,"tts_generated":False},
        "notice":"mock 스토리보드 템플릿이며 AI 분석 결과가 아니에요." if settings.mode=="mock" else "Gemini가 작성한 검토용 스토리보드예요. 아직 영상이나 음성은 만들지 않았어요."}
