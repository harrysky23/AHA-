"""Shared multipart validation; extraction/generation happens after admission."""
import re

from fastapi import HTTPException

from .errors import LearningError
from .uploads import read_upload


async def read_storyboard_input(request, settings, *, claude=False):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        raise HTTPException(415, "multipart/form-data 형식으로 제출해 주세요.")
    async with request.form(max_files=1, max_fields=7 if claude else 6, max_part_size=48_000 if claude else 16_384) as form:
        allowed = {"concept", "question", "format", "file", "consent", "target_duration_seconds", "student_level"}
        if claude:
            allowed.add("material_text")
        if set(form)-allowed or any(len(form.getlist(key)) != 1 for key in form):
            raise HTTPException(422, "중복되거나 지원하지 않는 입력 항목이 있어요.")
        fields = {}
        for name, limit, default in [("concept",200,""),("question",2000,""),("format",20,"storyboard"),
                                    ("target_duration_seconds",2,"45"),("student_level",20,"high_school")]:
            value = form.get(name, default)
            if not isinstance(value, str) or len(value.strip()) > limit:
                raise HTTPException(422, f"{name} 입력 형식을 확인해 주세요.")
            fields[name] = value.strip()
        if not fields["concept"] and not fields["question"]:
            raise HTTPException(422, "어려운 개념 또는 질문을 입력해 주세요.")
        if fields["format"] not in {"storyboard", "shorts"}:
            raise HTTPException(422, "이 API는 storyboard 또는 shorts 입력을 받아요. HTML은 /api/learn을 사용해 주세요.")
        if not re.fullmatch(r"[0-9]{2}", fields["target_duration_seconds"]) or not 30 <= int(fields["target_duration_seconds"]) <= 60:
            raise HTTPException(422, "목표 길이는 30–60 사이의 정수 초로 입력해 주세요.")
        if fields["student_level"] not in {"foundation", "high_school", "advanced"}:
            raise HTTPException(422, "학생 수준은 foundation, high_school, advanced 중 하나로 입력해 주세요.")
        if claude and form.get("consent") != "true":
            raise LearningError("chatkhu_consent_required", "ChatKHU 자료 전송 및 생성 크레딧 안내를 확인해 주세요.", 428, False)
        if not claude and settings.mode == "gemini" and form.get("consent") != "true":
            raise LearningError("consent_required", "Gemini 전송 안내를 확인해 주세요. 질문과 PDF 추출 텍스트가 Google에 전송될 수 있어요. 무료 티어에는 개인정보·민감정보를 보내지 마세요.", 428, False)
        material, data = await read_upload(form.get("file"), allow_text=claude)
        result = dict(concept=fields["concept"], question=fields["question"], material=material, file_data=data,
                    target_duration_seconds=int(fields["target_duration_seconds"]), student_level=fields["student_level"])
        if claude:
            value = form.get("material_text", "")
            if not isinstance(value, str) or len(value) > 12000:
                raise HTTPException(422, "참고 텍스트는 12,000자까지 입력할 수 있어요.")
            result["material_text"] = value.strip()
        return result
