"""Bounded documented REST transport. No automatic POST retries or model fallback."""
import json
import math
import re
import time
from threading import Lock
from urllib.parse import quote, urlsplit

import httpx

from ...services.validation import load_json
from .contracts import Approval, ChatKHUError

PATHS = {"image": "/images/generate/", "video": "/video/generation/", "tts": "/audio/speech/"}
MAX_JSON = 32*1024**2
MAX_MEDIA = 100*1024**2


def operation_path(kind, operation_id):
    if kind not in {"image", "video"} or not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,2047}", operation_id):
        raise ChatKHUError("invalid_operation", "비동기 작업 식별자 형식을 확인하지 못했어요.")
    if "//" in operation_id or any(part in {".", ".."} for part in operation_id.split("/")):
        raise ChatKHUError("invalid_operation", "허용되지 않는 작업 식별자예요.")
    return PATHS[kind]+quote(operation_id, safe="/:")+"/"


def numeric(value):
    try:
        return type(value) in {int, float} and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def accounting(body=None, headers=None):
    body, headers = body or {}, headers or {}
    billing = body.get("billing")
    if headers.get("x-billing"):
        try:
            billing = load_json(headers["x-billing"])
        except (ValueError, TypeError):
            billing = None
    actual = body.get("credits_charged")
    result = {"credits_charged": actual if numeric(actual) else None, "billing": None,
              "input_tokens": None, "output_tokens": None}
    if isinstance(billing, dict):
        allowed = {key: value for key, value in billing.items() if key in {
            "cost_usd", "exchange_rate", "cost_krw", "credit_conversion_rate", "payment_fee_rate", "deducted_credit"} and numeric(value)}
        if isinstance(billing.get("vat_included"), bool):
            allowed["vat_included"] = billing["vat_included"]
        date = billing.get("exchange_rate_date")
        if isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            allowed["exchange_rate_date"] = date
        result["billing"] = allowed or None
    for source, target in [("x-input-tokens", "input_tokens"), ("x-output-tokens", "output_tokens")]:
        value = str(headers.get(source, ""))
        if re.fullmatch(r"[0-9]{1,12}", value):
            result[target] = int(value)
    return result


class GatewayClient:
    def __init__(self, settings, *, transport=None, media_transport=None, clock=time.monotonic, sleep=time.sleep, on_event=None):
        settings.validate(require_key=True)
        self.settings, self.clock, self.sleep = settings, clock, sleep
        self.events = []
        self.on_event = on_event
        self.sent = {kind: 0 for kind in PATHS}
        self.generation_lock = Lock()
        self.http = httpx.Client(transport=transport, timeout=settings.request_timeout, follow_redirects=False, trust_env=False,
            headers={"Authorization": "Bearer "+settings.api_key, "User-Agent": "AHA-PoC/phase3d"})
        # Credentials must never be inherited by a CDN request.
        self.media = httpx.Client(transport=media_transport, timeout=settings.request_timeout, follow_redirects=False,
                                  trust_env=False, headers={"User-Agent": "AHA-PoC/phase3d"})

    def close(self):
        self.http.close(); self.media.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def event(self, value):
        self.events.append(value)
        if self.on_event:
            self.on_event(value)

    def _bytes(self, method, path, *, payload=None, params=None, limit=MAX_JSON, media_url=None, headers=None):
        if media_url is None:
            if not path.startswith("/") or ".." in path.split("/") or "?" in path or "#" in path:
                raise ChatKHUError("invalid_path", "허용되지 않는 Gateway 경로예요.")
            url, client = self.settings.base_url.rstrip("/")+path, self.http
        else:
            host = urlsplit(media_url)
            if (host.scheme != "https" or not host.hostname or host.username or host.password or host.port not in {None, 443}
                    or not (host.hostname == "fal.media" or host.hostname.endswith(".fal.media"))):
                raise ChatKHUError("untrusted_media_host", "문서에서 확인하지 않은 외부 미디어 호스트예요. 승인 없이 접근하지 않아요.")
            url, client = media_url, self.media
        deadline = self.clock()+self.settings.request_timeout
        def check_deadline():
            if self.clock() >= deadline:
                raise ChatKHUError("request_timeout", "응답 수신 제한 시간이 끝났어요. 자동으로 요청을 다시 보내지 않아요.")
        try:
            with client.stream(method, url, json=payload, params=params, headers=headers) as response:
                check_deadline()
                if response.is_redirect:
                    raise ChatKHUError("redirect_blocked", "자동 리다이렉트를 차단했어요. 인증 정보가 외부로 전달되지 않아요.", response.status_code)
                if response.status_code >= 400:
                    names = {400:"invalid_request",401:"authentication_failed",402:"credits_unavailable",403:"model_forbidden",
                             404:"model_or_operation_not_found",413:"request_too_large",429:"rate_limited",503:"gateway_unavailable",504:"gateway_timeout"}
                    raise ChatKHUError(names.get(response.status_code,"gateway_error"),
                                      "Gateway가 요청을 거절했어요. 자동 재시도나 모델 전환은 하지 않아요.", response.status_code)
                declared = response.headers.get("content-length")
                if declared and declared.isdecimal() and int(declared) > limit:
                    raise ChatKHUError("response_too_large", "Gateway 결과 파일 크기 제한을 초과했어요.")
                parts, total = [], 0
                for part in response.iter_bytes():
                    check_deadline()
                    total += len(part)
                    if total > limit:
                        raise ChatKHUError("response_too_large", "Gateway 결과 파일 크기 제한을 초과했어요.")
                    parts.append(part)
                return b"".join(parts), response.headers
        except httpx.TimeoutException:
            raise ChatKHUError("request_timeout", "응답 시간이 초과됐어요. 요청이 접수·과금됐을 수 있어 다시 생성하지 말고 대시보드를 확인해 주세요.") from None
        except (httpx.HTTPError, ValueError):
            raise ChatKHUError("connection_failed", "Gateway 연결을 확인하지 못했어요. 생성 요청은 자동 재전송하지 않아요.") from None

    def _json(self, method, path, **kwargs):
        raw, headers = self._bytes(method, path, **kwargs)
        try:
            data = load_json(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data, headers
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ChatKHUError("invalid_response", "Gateway JSON 응답 형식을 확인하지 못했어요.") from None

    def models(self):
        data, _ = self._json("GET", "/models/", params={"type": "image,video,audio"})
        if not isinstance(data.get("data"), list):
            raise ChatKHUError("invalid_response", "모델 목록 응답 형식을 확인하지 못했어요.")
        return data

    def complete_video_code(self, model, messages, *, repair=False):
        kind = "code_repair" if repair else "code"
        with self.generation_lock:
            if self.sent.get(kind):
                raise ChatKHUError("call_limit", "코드 생성과 수정은 각각 작업당 1회만 시도해요.")
            self.sent[kind] = 1
        started = self.clock()
        self.event({"phase": "submission", "kind": kind, "model": model})
        try:
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            conversation = [m for m in messages if m["role"] != "system"]
            data, headers = self._json("POST", "/claude/v1/messages/", payload={
                "model": model, "system": system, "messages": conversation, "max_tokens": 5500,
                "output_config": {"effort": "low"}, "stream": False,
            }, limit=512*1024, headers={"anthropic-version": "2023-06-01"})
            measured = accounting(data, headers)
            usage = data.get("usage")
            if isinstance(usage, dict):
                for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                    if type(usage.get(field)) is int and 0 <= usage[field] < 10**9:
                        measured[field] = usage[field]
            actual = data.get("model")
            if not isinstance(actual, str) or not re.fullmatch(r"[a-zA-Z0-9._/-]{1,100}", actual) or self.settings.api_key in actual:
                actual = None
            stop_reason = data.get("stop_reason")
            known_stops = ("end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal")
            self.event({"phase": "accepted", "kind": kind, "model": model, "actual_model": actual,
                        "stop_reason": stop_reason if stop_reason in known_stops else None,
                        "elapsed_seconds": round(self.clock()-started, 3), **measured})
            if stop_reason == "max_tokens":
                raise ChatKHUError("code_output_limit", "Claude가 출력 토큰 한도에 도달해 코드 응답을 완료하지 못했어요.")
            blocks = data.get("content")
            content = "".join(
                block["text"] for block in blocks
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
            ) if isinstance(blocks, list) else ""
            if stop_reason != "end_turn" or not content.strip():
                raise ChatKHUError("invalid_code_response", "Claude 응답에 완성된 코드 텍스트가 없어요.")
            return content
        except ChatKHUError as exc:
            self.event({"phase": "error", "kind": kind, "model": model, "code": exc.code,
                        "http_status": exc.status, "message": exc.message, "elapsed_seconds": round(self.clock()-started, 3)})
            raise

    def estimate(self, kind, payload):
        if kind not in {"image", "video"}:
            raise ChatKHUError("estimate_unsupported", "공식 견적 API는 TTS를 지원하지 않아요. 출력 토큰 비용은 아직 확인할 수 없어요.")
        body = {key: value for key, value in payload.items() if key not in {"prompt", "input_urls"}}
        data, _ = self._json("POST", "/estimate/", payload={"kind": kind, **body})
        if (data.get("object") != "estimate" or data.get("kind") != kind or data.get("model") != payload["model"]
                or not numeric(data.get("credits")) or data.get("bound") not in {"exact", "minimum", "maximum", "approximate"}):
            raise ChatKHUError("invalid_estimate", "견적 응답을 확인하지 못했어요. 생성 요청을 보내지 않아요.")
        return {"credits": data["credits"], "bound": data["bound"], "source": "gateway_estimate"}

    def generate(self, kind, payload, approval: Approval, cost):
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 24*1024**2:
            raise ChatKHUError("request_too_large", "요청 본문이 로컬 안전 한도를 초과했어요.")
        with self.generation_lock:
            if kind not in PATHS or self.sent[kind] >= 1:
                raise ChatKHUError("call_limit", "종류별 생성 요청은 이 실행에서 최대 1회예요.")
            approval.consume(kind, payload, cost)
            self.sent[kind] += 1
        self.event({"phase":"submission", "kind":kind, "model":payload["model"], "generation_attempts":1, "accounting_status":"unknown_until_response"})
        if kind == "tts":
            raw, headers = self._bytes("POST", PATHS[kind], payload=payload, limit=8*1024**2)
            self.event({"phase":"accepted", "kind":kind, **accounting(headers=headers)})
            if headers.get("content-type", "").split(";")[0].lower() != "audio/pcm":
                raise ChatKHUError("invalid_audio_type", "문서의 audio/pcm 응답이 아니에요.")
            return raw
        data, headers = self._json("POST", PATHS[kind], payload=payload)
        self.event({"phase":"accepted", "kind":kind, **accounting(data, headers)})
        return data

    def poll(self, kind, model, data):
        operation_id = data.get("operation_id")
        if isinstance(operation_id, str) and self.settings.api_key in operation_id:
            raise ChatKHUError("invalid_operation", "작업 식별자를 안전하게 기록할 수 없어요.")
        path = operation_path(kind, operation_id)
        self.event({"phase":"operation", "kind":kind, "model":model, "operation_id":operation_id})
        deadline, polls = self.clock()+self.settings.operation_timeout, 0
        while data.get("status") == "processing":
            if polls >= self.settings.max_polls or self.clock() >= deadline:
                raise ChatKHUError("operation_timeout", "작업이 아직 끝나지 않았어요. 재생성하지 말고 저장한 작업 ID로 조회를 재개해 주세요. 실패 환불 확인을 위해 종료 상태 조회가 필요해요.", operation_id=operation_id)
            self.sleep(min(10 if kind == "video" else 5, max(0, deadline-self.clock())))
            if self.clock() >= deadline:
                raise ChatKHUError("operation_timeout", "상태 조회 제한 시간이 끝났어요. 저장한 작업을 조회만 재개할 수 있어요.", operation_id=operation_id)
            data, headers = self._json("GET", path, params={"model":model})
            polls += 1
            reported_status = data.get("status")
            safe_status = reported_status if reported_status in ("processing", "completed", "failed") else "invalid"
            self.event({"phase":"poll", "kind":kind, "poll_count":polls, "status":safe_status, **accounting(data,headers)})
        if data.get("status") == "failed":
            raise ChatKHUError("generation_failed", "Gateway 작업이 실패했어요. 자동 재생성하지 않아요. 환불 여부는 공식 사용량·대시보드로 확인해 주세요.", operation_id=operation_id)
        if data.get("status") != "completed":
            raise ChatKHUError("invalid_response", "지원하지 않는 비동기 작업 상태예요.", operation_id=operation_id)
        return data, operation_id

    def download(self, kind, model, location, operation_id=None):
        if not isinstance(location, str):
            raise ChatKHUError("invalid_media_url", "결과 미디어 주소를 확인하지 못했어요.")
        if location.startswith("https://") and not location.startswith(self.settings.base_url.rstrip("/")+"/"):
            raw, _ = self._bytes("GET", "", media_url=location, limit=MAX_MEDIA)
            return raw
        if kind == "video" and operation_id:
            path = operation_path(kind, operation_id)+"download/"
            expected = "/v1/gateway"+path
            parts = urlsplit(location)
            if parts.path != expected or (parts.netloc and parts.netloc != "factchat-cloud.mindlogic.ai"):
                raise ChatKHUError("invalid_media_url", "문서에 정의된 작업 다운로드 주소가 아니에요.")
            raw, _ = self._bytes("GET", path, params={"model":model}, limit=MAX_MEDIA)
            return raw
        raise ChatKHUError("invalid_media_url", "지원하지 않는 미디어 주소예요.")
