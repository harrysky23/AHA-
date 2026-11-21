from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile

from ..services.lessons import build_lesson

router = APIRouter(prefix="/api")
MAX_FILE_BYTES = 5 * 1024 * 1024
FILE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def has_signature(data: bytes, mime: str) -> bool:
    return {
        "application/pdf": data.startswith(b"%PDF-"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }.get(mime, False)


@router.get("/health")
async def health():
    return {"status": "ok", "mode": "local_demo", "external_ai": False}


@router.post("/learn")
async def learn(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        raise HTTPException(415, "multipart/form-data 형식으로 제출해 주세요.")
    async with request.form(max_files=1, max_fields=3, max_part_size=16_384) as form:
        allowed = {"concept", "question", "format", "file"}
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
        material = None
        upload = form.get("file")
        if upload is not None:
            if not isinstance(upload, UploadFile) or not upload.filename:
                raise HTTPException(422, "파일을 다시 선택해 주세요.")
            filename = PurePosixPath(upload.filename.replace("\\", "/")).name
            if len(filename) > 200:
                raise HTTPException(422, "파일 이름을 200자 이하로 줄여 주세요.")
            mime = FILE_TYPES.get(PurePosixPath(filename).suffix.lower())
            if not mime or upload.content_type != mime:
                raise HTTPException(415, "PDF, PNG, JPEG, WebP 파일만 업로드할 수 있어요.")
            data = await upload.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, "파일은 5MB 이하로 올려 주세요.")
            if not data or not has_signature(data, mime):
                raise HTTPException(415, "파일 내용과 형식이 맞지 않아요. 올바른 파일을 선택해 주세요.")
            material = {"filename": filename, "size_bytes": len(data), "content_type": mime, "analyzed": False}
        return build_lesson(fields["concept"], fields["question"], fields["format"], material)
