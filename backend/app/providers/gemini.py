"""Google Gemini Developer API: documented generateContent REST, data-only output."""
import asyncio
import logging
import math

import httpx

from ..config import ConfigurationError, Settings
from ..schemas import LessonSpec
from ..services.errors import LearningError
from ..services.prompts import build_messages
from ..services.validation import load_json, parse_spec
from .base import GenerationInput, ProviderResult, StoryboardInput, StoryboardResult

logger = logging.getLogger("aha.generation")
API_SLOTS = asyncio.Semaphore(2)
MAX_RESPONSE_BYTES = 96 * 1024
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def response_schema(source: dict | None = None) -> dict:
    """Use the documented schema subset; enforce all omitted constraints locally."""
    source = source if source is not None else LessonSpec.model_json_schema()
    definitions = source.get("$defs", {})
    allowed = {"type", "description", "enum", "minimum", "maximum", "required", "additionalProperties", "minItems", "maxItems"}

    def convert(node):
        if "$ref" in node:
            return convert(definitions[node["$ref"].split("/")[-1]])
        result = {key: value for key, value in node.items() if key in allowed}
        if "const" in node:
            result["enum"] = [node["const"]]
        if "properties" in node:
            result["properties"] = {key: convert(value) for key, value in node["properties"].items()}
        if "items" in node:
            result["items"] = convert(node["items"])
        if "anyOf" in node or "oneOf" in node:
            options = node.get("anyOf", node.get("oneOf"))
            if len(options) == 2 and any(item.get("type") == "null" for item in options):
                result = convert(next(item for item in options if item.get("type") != "null"))
                result["type"] = [result["type"], "null"]
            else:
                # Storyboard types carry disjoint literal tags, so anyOf retains the union.
                result["anyOf"] = [convert(option) for option in options]
        return result

    return convert(source)


def retry_seconds(headers: httpx.Headers, envelope: dict) -> int | None:
    value = headers.get("retry-after", "")
    try:
        number = float(value)
        return math.ceil(number) if 0 <= number <= 86400 else None
    except ValueError:
        return None


def http_error(status: int, envelope: dict, headers: httpx.Headers) -> LearningError:
    error = envelope.get("error")
    error = error if isinstance(error, dict) else {}
    state = error.get("status")
    reasons = [item.get("reason") for item in error.get("details", []) if isinstance(item, dict)] if isinstance(error.get("details", []), list) else []
    if status in {401,403} or "API_KEY_INVALID" in reasons or state == "UNAUTHENTICATED":
        return LearningError("gemini_auth", "Gemini API 키·프로젝트 권한·사용 가능 지역을 확인해 주세요.", 503)
    if status == 429:
        retry = retry_seconds(headers, envelope)
        message = "Gemini의 무료 할당량 또는 요청·토큰 한도에 도달했어요. AI Studio의 프로젝트 한도를 확인하거나 기본 예제를 열어 주세요."
        if retry is not None:
            message += f" 서버가 안내한 재시도 대기 시간은 {retry}초예요. 자동 재시도하지 않아요."
        return LearningError("gemini_quota_exceeded", message, 429, retry_after=retry)
    if status == 404:
        return LearningError("gemini_model_unavailable", "설정한 Gemini 모델을 사용할 수 없어요. AI Studio에서 모델 ID와 프로젝트 접근 가능 여부를 확인해 주세요.", 503)
    if status == 400 and state == "FAILED_PRECONDITION":
        return LearningError("gemini_free_tier_unavailable", "현재 지역·프로젝트의 Gemini 무료 티어 조건을 충족하지 못했어요. AI Studio에서 확인해 주세요. 앱은 유료 전환을 자동으로 진행하지 않아요.", 503)
    if status == 400:
        return LearningError("gemini_request_invalid", "Gemini가 요청 형식이나 모델 설정을 거절했어요. 서버 설정과 모델의 JSON 출력 지원을 확인해 주세요.")
    if status == 504:
        return LearningError("gemini_timeout", "Gemini 서버의 응답 제한 시간이 초과됐어요. 기본 예제를 열거나 나중에 다시 시도해 주세요.", 504)
    if status == 503:
        message = str(error.get("message", "")).lower()
        if "high demand" in message or "overloaded" in message:
            return LearningError("gemini_overloaded", "Gemini가 요청 폭주로 일시적인 서비스 부하(HTTP 503)를 응답했어요. 무료 한도 초과(429)와 다른 오류예요. 기본 예제를 열거나 나중에 다시 시도해 주세요.", 503)
    return LearningError("gemini_unavailable", "Gemini 서비스가 요청을 처리하지 못했어요. 기본 예제를 열거나 나중에 다시 시도해 주세요.", 503)


def diagnostic_error(status: int, envelope: dict, headers: httpx.Headers, api_key: str) -> LearningError:
    failure = http_error(status, envelope, headers)
    failure.upstream_status = status
    error = envelope.get("error", {})
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        failure.upstream_message = error["message"].replace(api_key, "[REDACTED]")[:1500]
    return failure


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.model = settings.model
        self.transport = transport

    async def generate(self, request: GenerationInput, request_id: str) -> ProviderResult:
        messages = build_messages(request.concept, request.question, request.material, include_schema=False)
        envelope = await self.generate_json(messages, response_schema(), self.settings.max_output_tokens, request_id)
        return self.parse_response(envelope, request)

    async def generate_storyboard(self, request: StoryboardInput, request_id: str) -> StoryboardResult:
        from ..services.storyboard_prompts import build_storyboard_messages
        from ..services.storyboard_validation import parse_storyboard
        from ..storyboard_schema import StoryboardSpec
        messages = build_storyboard_messages(request)
        schema = response_schema(StoryboardSpec.model_json_schema())
        envelope = await self.generate_json(messages, schema, self.settings.storyboard_max_output_tokens, request_id)
        text, usage = self.response_text(envelope)
        return StoryboardResult(parse_storyboard(text, request), self.model, usage)

    async def generate_json(self, messages: list[dict], schema: dict, max_output_tokens: int, request_id: str) -> dict:
        try:
            self.settings.validate_gemini()
        except ConfigurationError:
            raise LearningError("gemini_not_configured", "Gemini 설정이 부족해요. 서버 .env의 GEMINI_API_KEY와 GEMINI_MODEL을 확인해 주세요.", 503) from None
        payload = {
            "systemInstruction": {"parts":[{"text":messages[0]["content"]}]},
            "contents":[{"role":"user", "parts":[{"text":messages[1]["content"]}]}],
            "generationConfig":{"responseMimeType":"application/json", "responseJsonSchema":schema,
                                "maxOutputTokens":max_output_tokens},
        }
        try:
            async with asyncio.timeout(2):
                await API_SLOTS.acquire()
        except TimeoutError:
            raise LearningError("gemini_busy", "AI 요청이 많아요. 잠시 후 다시 시도하거나 기본 예제를 열어 주세요.", 503) from None
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.settings.timeout_seconds, connect=10),
                        follow_redirects=False, trust_env=False, transport=self.transport) as client:
                    async with client.stream("POST", f"{API_BASE}/{self.model}:generateContent", json=payload,
                            headers={"x-goog-api-key":self.settings.api_key, "Content-Type":"application/json"}) as response:
                        logger.info("request_id=%s provider=gemini http_status=%s", request_id, response.status_code)
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise LearningError("gemini_response_limit", "Gemini 응답이 너무 커서 표시하지 않았어요. 기본 예제를 열 수 있어요.")
                            chunks.append(chunk)
                        try:
                            envelope = load_json(b"".join(chunks))
                            if not isinstance(envelope, dict):
                                raise ValueError
                        except (ValueError, TypeError, RecursionError):
                            if response.status_code != 200:
                                raise diagnostic_error(response.status_code, {}, response.headers, self.settings.api_key) from None
                            raise LearningError("gemini_invalid_response", "Gemini 응답을 JSON으로 읽지 못했어요. 기본 예제를 열 수 있어요.") from None
                        if response.status_code != 200:
                            raise diagnostic_error(response.status_code, envelope, response.headers, self.settings.api_key)
            return envelope
        except (httpx.TimeoutException, TimeoutError):
            raise LearningError("gemini_timeout", "Gemini 응답 시간이 초과됐어요. 다시 시도하거나 기본 예제를 열어 주세요.", 504) from None
        except httpx.HTTPError:
            raise LearningError("gemini_network", "Gemini에 연결하지 못했어요. 네트워크를 확인하거나 기본 예제를 열어 주세요.", 503) from None
        finally:
            API_SLOTS.release()

    def parse_response(self, envelope: dict, request: GenerationInput) -> ProviderResult:
        text, usage = self.response_text(envelope)
        return ProviderResult(parse_spec(text, request.material), self.model, usage)

    def response_text(self, envelope: dict) -> tuple[str, dict]:
        try:
            feedback = envelope.get("promptFeedback", {})
            if feedback.get("blockReason") not in {None,"BLOCK_REASON_UNSPECIFIED"}:
                raise LearningError("gemini_blocked", "Gemini가 입력의 안전성·콘텐츠 정책에 따라 생성을 차단했어요. 기본 예제를 이용할 수 있어요.", 422)
            candidates = envelope["candidates"]
            if len(candidates) != 1:
                raise ValueError
            candidate = candidates[0]
            reason = candidate.get("finishReason")
            if reason == "MAX_TOKENS":
                raise LearningError("gemini_output_truncated", "출력 토큰 제한으로 Gemini 설명이 끝나기 전에 잘렸어요. 기본 예제를 열거나 서버의 출력 제한을 확인해 주세요.")
            if reason in {"SAFETY","RECITATION","BLOCKLIST","PROHIBITED_CONTENT","SPII","IMAGE_SAFETY"}:
                raise LearningError("gemini_blocked", "Gemini가 안전성·콘텐츠 정책에 따라 응답을 차단했어요. 기본 예제를 이용할 수 있어요.", 422)
            if reason != "STOP":
                raise ValueError
            parts = candidate["content"]["parts"]
            text = []
            for part in parts:
                if part.get("thought") is True:
                    continue
                if not isinstance(part.get("text"), str) or set(part) - {"text","thought","thoughtSignature"}:
                    raise ValueError
                text.append(part["text"])
            raw_usage = envelope.get("usageMetadata") or {}
            usage = {key:value for key,value in raw_usage.items()
                     if key in {"promptTokenCount","candidatesTokenCount","totalTokenCount","thoughtsTokenCount"}
                     and type(value) is int and value >= 0}
            return "".join(text), usage
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
            raise LearningError("gemini_invalid_response", "Gemini 응답이 비어 있거나 완성된 텍스트 명세가 아니에요. 기본 예제를 열 수 있어요.") from None
