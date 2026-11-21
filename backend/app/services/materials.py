import asyncio
from dataclasses import dataclass, field
import json
import os
import sys

from ..config import ROOT
from .errors import LearningError

PDF_SLOTS = asyncio.Semaphore(2)


@dataclass
class MaterialContext:
    status: str = "no_material"
    message: str = "학습 자료 없이 질문을 바탕으로 설명해요. 예제는 f(x)=x², a=1로 제한합니다."
    pages: list[dict] = field(default_factory=list)
    page_count: int = 0
    empty_pages: list[int] = field(default_factory=list)
    truncated: bool = False
    extracted_characters: int = 0

    def public(self):
        return {"status": self.status, "message": self.message, "page_count": self.page_count,
                "empty_pages": self.empty_pages, "truncated": self.truncated,
                "extracted_characters": self.extracted_characters}


async def analyze_material(data: bytes | None, mime: str | None) -> MaterialContext:
    if data is None:
        return MaterialContext()
    if mime != "application/pdf":
        return MaterialContext(status="image_unsupported", message="이미지 OCR은 아직 지원하지 않아요. 이미지 내용은 분석·전송하지 않고 질문만 사용해요. 텍스트가 있는 PDF나 질문을 입력해 주세요.")
    process = None
    try:
        async with asyncio.timeout(2):
            await PDF_SLOTS.acquire()
    except TimeoutError:
        raise LearningError("pdf_busy", "자료 분석 요청이 많아요. 잠시 후 다시 시도해 주세요.", 503) from None
    try:
        # Child receives no API secrets and cannot hang the ASGI event loop.
        environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG") if key in os.environ}
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "backend.app.services.pdf_worker", cwd=ROOT, env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(8):
                stdout, _ = await process.communicate(data)
        except TimeoutError:
            raise LearningError("pdf_timeout", "PDF 분석 시간이 초과됐어요. 더 짧은 자료를 사용하거나 기본 예제를 열어 주세요.", 422) from None
        if process.returncode != 0:
            raise LearningError("pdf_complexity", "PDF가 너무 복잡해 읽지 못했어요. 더 간단한 PDF를 사용해 주세요.", 422)
        result = json.loads(stdout)
        errors = {
            "encrypted_pdf": "암호화된 PDF는 지원하지 않아요. 암호가 없는 PDF를 사용해 주세요.",
            "pdf_page_limit": "PDF는 1–20쪽까지 분석할 수 있어요. 필요한 부분만 올려 주세요.",
            "pdf_complexity": "PDF 내부 데이터가 너무 복잡하거나 커서 분석하지 못했어요.",
            "invalid_pdf": "PDF를 읽지 못했어요. 손상 여부를 확인하거나 다른 PDF를 사용해 주세요.",
        }
        if result.get("error"):
            code = result["error"]
            raise LearningError(code, errors.get(code, errors["invalid_pdf"]), 422)
        status = "text_extracted" if result["pages"] else "no_extractable_text"
        message = (f"PDF {result['page_count']}쪽에서 {result['extracted_characters']:,}자를 추출했어요. 수식·표·읽기 순서는 정확하지 않을 수 있어요."
                   if result["pages"] else "추출 가능한 텍스트가 없어요. 스캔·이미지 PDF이거나 빈 문서일 수 있어요. OCR은 지원하지 않아 질문만 사용해요.")
        if result["pages"] and result["empty_pages"]:
            message += " 텍스트가 없는 쪽은 읽지 못했어요: " + ", ".join(map(str, result["empty_pages"])) + "."
        if result["truncated"]:
            message += " 12,000자 제한으로 이후 내용은 분석에서 제외했어요."
        return MaterialContext(status=status, message=message, **result)
    except (json.JSONDecodeError, OSError):
        raise LearningError("pdf_unavailable", "PDF 분석기를 실행하지 못했어요. 서버 설정을 확인해 주세요.", 503) from None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.communicate()
        PDF_SLOTS.release()
