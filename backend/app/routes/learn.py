from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import ConfigurationError, Settings, get_settings
from ..services.errors import LearningError
from ..services.lessons import build_sample_video, create_learning
from ..services.uploads import FILE_TYPES, MAX_FILE_BYTES, has_signature, read_upload
import math

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)):
    configured = settings.mode == "mock"
    if settings.mode == "gemini":
        try:
            settings.validate_gemini()
            configured = True
        except (ConfigurationError, ValueError):
            pass
    return {"status":"ok", "mode":settings.mode, "external_ai":settings.mode == "gemini",
            "ai_configured":configured, "request_timeout_seconds":math.ceil(settings.timeout_seconds)+15,
            "cache_enabled":settings.cache_ttl_seconds > 0}


@router.post("/learn")
async def learn(request: Request, settings: Settings = Depends(get_settings)):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        raise HTTPException(415, "multipart/form-data 형식으로 제출해 주세요.")
    async with request.form(max_files=1, max_fields=4, max_part_size=16_384) as form:
        allowed = {"concept", "question", "format", "file", "consent"}
        if set(form) - allowed or any(len(form.getlist(key)) != 1 for key in form):
            raise HTTPException(422, "중복되거나 지원하지 않는 입력 항목이 있어요.")
        fields = {}
        for name, limit in [("concept", 200), ("question", 2000), ("format", 20)]:
            value = form.get(name, "")
            if not isinstance(value, str):
                raise HTTPException(422, "개념·질문·학습 방식은 텍스트로 입력해 주세요.")
            fields[name] = value.strip()
            if len(fields[name]) > limit:
                raise HTTPException(422, f"{name} 입력은 {limit}자 이하로 입력해 주세요.")
        if not fields["concept"] and not fields["question"]:
            raise HTTPException(422, "어려운 개념 또는 질문을 입력해 주세요.")
        if fields["format"] not in {"html", "shorts"}:
            raise HTTPException(422, "학습 방식을 선택해 주세요: html 또는 shorts.")
        if settings.mode == "gemini" and fields["format"] == "html" and form.get("consent") != "true":
            raise LearningError("consent_required", "Gemini 전송 안내를 확인해 주세요. 질문과 PDF 추출 텍스트가 Google Gemini에 전송될 수 있어요. 무료 티어에는 개인정보·민감정보를 보내지 마세요.", 428, False)
        material, data = await read_upload(form.get("file"))
        if fields["format"] == "shorts":
            # Phase 3 remains unimplemented: never call AI for an existing video.
            return build_sample_video(fields["concept"], fields["question"], material)
        return await create_learning(settings, fields["concept"], fields["question"], material, data)
