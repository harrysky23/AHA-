"""Shared multipart upload validation. Preserve Phase 1/2 limits and errors."""
from pathlib import PurePosixPath

from fastapi import HTTPException
from starlette.datastructures import UploadFile

MAX_FILE_BYTES = 5 * 1024 * 1024
FILE_TYPES = {".pdf":"application/pdf", ".png":"image/png", ".jpg":"image/jpeg",
              ".jpeg":"image/jpeg", ".webp":"image/webp"}


def has_signature(data: bytes, mime: str) -> bool:
    return {"application/pdf":data.startswith(b"%PDF-"),
            "image/png":data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg":data.startswith(b"\xff\xd8\xff"),
            "image/webp":data.startswith(b"RIFF") and data[8:12]==b"WEBP"}.get(mime,False)


async def read_upload(upload) -> tuple[dict | None, bytes | None]:
    if upload is None:
        return None, None
    if not isinstance(upload, UploadFile) or not upload.filename:
        raise HTTPException(422,"파일을 다시 선택해 주세요.")
    filename = PurePosixPath(upload.filename.replace("\\","/")).name
    if len(filename)>200:
        raise HTTPException(422,"파일 이름을 200자 이하로 줄여 주세요.")
    mime = FILE_TYPES.get(PurePosixPath(filename).suffix.lower())
    if not mime or upload.content_type != mime:
        raise HTTPException(415,"PDF, PNG, JPEG, WebP 파일만 업로드할 수 있어요.")
    data = await upload.read(MAX_FILE_BYTES+1)
    if len(data)>MAX_FILE_BYTES:
        raise HTTPException(413,"파일은 5MB 이하로 올려 주세요.")
    if not data or not has_signature(data,mime):
        raise HTTPException(415,"파일 내용과 형식이 맞지 않아요. 올바른 파일을 선택해 주세요.")
    return {"filename":filename,"size_bytes":len(data),"content_type":mime,"analyzed":False}, data
