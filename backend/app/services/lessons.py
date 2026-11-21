"""Preserved sample-video response plus the validated Phase 2 lesson pipeline."""
import logging
from uuid import uuid4

from ..config import Settings
from ..providers import get_provider
from ..providers.base import GenerationInput
from ..schemas import verify_grounding
from .cache import lesson_cache
from .errors import LearningError
from .materials import analyze_material
from .prompts import PROMPT_VERSION

logger = logging.getLogger("aha.generation")


async def create_learning(settings: Settings, concept: str, question: str, material: dict | None,
                          file_data: bytes | None) -> dict:
    request_id = uuid4().hex
    logger.info("request_id=%s mode=%s event=start", request_id, settings.mode)
    try:
        context = await analyze_material(file_data, material["content_type"] if material else None)
        provider = get_provider(settings)
        request = GenerationInput(concept,question,context)

        async def generate_validated():
            result = await provider.generate(request,request_id)
            # Revalidate every provider, including future implementations, before caching.
            from ..schemas import LessonSpec
            try:
                spec = LessonSpec.model_validate(result.spec.model_dump())
                verify_grounding(spec, context.pages)
            except (ValueError, TypeError, AttributeError):
                raise LearningError("invalid_lesson_spec", "학습 명세의 구조·수학값·자료 인용을 확인하지 못했어요. 기본 예제를 열 수 있어요.") from None
            if spec.scope != "supported":
                raise LearningError("unsupported_scope", "현재는 f(x)=x², a=1의 할선→접선만 지원해요.", 422)
            result.spec = spec
            return result

        key = lesson_cache.key(provider.name,provider.model,settings,request)
        result, cache_status = await lesson_cache.get_or_create(key,generate_validated,settings.cache_ttl_seconds,settings.cache_max_entries)
        spec = result.spec
        generation = {"provider":provider.name, "model":result.model, "usage":{} if cache_status == "hit" else result.usage,
                      "request_id":request_id, "status":"validated", "external_ai":settings.mode == "gemini",
                      "cached":cache_status == "hit", "cache_status":cache_status, "prompt_version":PROMPT_VERSION}
        logger.info("request_id=%s mode=%s event=validated", request_id, settings.mode)
    except LearningError as exc:
        logger.warning("request_id=%s mode=%s event=failed code=%s", request_id, settings.mode, exc.code)
        raise
    if material:
        material = {**material, "text_extracted":bool(context.pages),
                    "analyzed":bool(context.pages) and settings.mode == "gemini",
                    "sent_to_provider":bool(context.pages) and settings.mode == "gemini" and cache_status != "hit"}
    return {
        "mode":settings.mode, "format":"html", "title":spec.title,
        "request":{"concept":concept, "question":question}, "material":material,
        "grounding":context.public(), "generation":generation,
        "notice": (("저장된 Gemini 학습 명세를 재사용했어요. 이번 요청에서는 모델을 다시 호출하지 않았어요. " if cache_status == "hit" else "Gemini가 질문과 추출 가능한 자료 텍스트로 설명을 구성했어요. ") + "설명 수준은 질문에서 추정한 것이며 성취도 진단은 아니에요."
                   if settings.mode == "gemini" else "mock 모드입니다. 질문에 관계없이 동일한 수학 II 고정 예제를 사용해요. 실제 AI 분석 결과가 아니에요."),
        "verification":{"numeric_checks":"passed", "source_quotes":"matched" if context.pages else "not_available",
                        "scope":"f(x)=x², a=1", "notice":"수치 예제·정답·자료 인용의 일치만 확인했어요. 자연어 설명 전체의 정확성은 보장하지 않아요."},
        "lesson":{"id":"secant-tangent", "viewer_url":"/lessons/secant-tangent", "function":"f(x)=x²",
                  "point":[1,1], "tangent_slope":2, "secant_formula":"2+h (h≠0)", "spec":spec.model_dump()},
        "video":None,
    }


def build_sample_video(concept: str, question: str, material: dict | None) -> dict:
    return {
        "mode": "local_demo",
        "format": "shorts",
        "title": "수학 II · 할선에서 접선으로",
        "request": {"concept": concept, "question": question},
        "material": material,
        "grounding": {
            "status": "not_analyzed" if material else "no_material",
            "message": (
                "기존 영상 보기에서는 자료 내용을 분석하거나 모델에 전송하지 않아요."
                if material else "학습 자료 없이 기존 예시 영상을 봐요."
            ),
        },
        "notice": "기존 예시 영상을 그대로 제공해요. 질문이나 자료로 새로 생성한 영상이 아닙니다.",
        "lesson": None,
        "video": {
            "url": "/static/media/derivative-explainer.mp4",
            "label": "기존 미분계수 예시 영상",
            "generated": False,
            "notice": "원본 시안에 포함된 가로형 예시 영상입니다. 요청한 자료로 새로 만든 9:16 숏츠가 아니며, 실제 숏츠 생성은 향후 연결합니다.",
        },
    }
