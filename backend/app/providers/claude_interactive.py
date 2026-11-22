"""Create one interactive lesson through the existing ChatKHU Messages client."""

import asyncio
from base64 import b64encode
from dataclasses import replace
import logging
import re
from threading import BoundedSemaphore

from ..config import ConfigurationError
from ..services.errors import LearningError
from .chatkhu import ChatKHUError, GatewayClient, get_chatkhu_settings

logger = logging.getLogger("aha.generation")
CLAUDE_SLOTS = BoundedSemaphore(2)


def lesson_settings(timeout_seconds: float):
    settings = replace(get_chatkhu_settings(), request_timeout=timeout_seconds)
    settings.validate(require_key=True)
    if not re.fullmatch(r"claude-[a-z0-9.-]{1,90}", settings.interactive_model):
        raise ConfigurationError("AHA_INTERACTIVE_CLAUDE_MODEL에 공식 Claude 모델 ID를 설정해 주세요.")
    return settings


class ClaudeInteractiveProvider:
    def __init__(self, timeout_seconds: float):
        self.settings = lesson_settings(timeout_seconds)
        self.model = self.settings.interactive_model

    def _request(self, instruction, reference, image, request_id):
        if not CLAUDE_SLOTS.acquire(blocking=False):
            raise LearningError("claude_busy", "인터랙티브 생성 요청이 많아요. 잠시 후 시도해 주세요.", 503)
        try:
            content = reference
            if image:
                mime, blob = image
                content = [{"type": "text", "text": reference}, {"type": "image", "source": {
                    "type": "base64", "media_type": mime, "data": b64encode(blob).decode("ascii"),
                }}]
            messages = [{"role": "system", "content": instruction}, {"role": "user", "content": content}]
            with GatewayClient(self.settings) as client:
                response = client.complete_interactive_lesson(self.model, messages)
                event = next((event for event in reversed(client.events) if event.get("phase") == "accepted"), {})
                usage = {key: event[key] for key in ("input_tokens", "output_tokens", "credits_charged")
                         if event.get(key) is not None}
                logger.info("request_id=%s provider=claude model=%s elapsed_seconds=%s usage=%s",
                            request_id, self.model, event.get("elapsed_seconds"), usage)
                return response, usage
        except ChatKHUError as exc:
            logger.warning("request_id=%s provider=claude code=%s upstream_status=%s", request_id, exc.code, exc.status)
            errors = {
                "credits_unavailable": (402, "ChatKHU 크레딧을 확인해 주세요."),
                "gateway_timeout": (504, "ChatKHU Claude 응답 시간이 초과됐어요."),
                "model_forbidden": (503, "이 ChatKHU 계정에서 설정한 Claude 모델을 사용할 수 없어요."),
                "rate_limited": (429, "ChatKHU 요청 한도에 도달했어요. 잠시 후 다시 시도해 주세요."),
                "interactive_output_limit": (502, "Claude 실습 명세가 출력 한도에서 잘렸어요."),
            }
            status, message = errors.get(exc.code, (502, "ChatKHU Claude의 실습 응답을 받지 못했어요."))
            raise LearningError(f"claude_{exc.code}", message, status) from None
        finally:
            CLAUDE_SLOTS.release()

    async def generate(self, instruction, reference, image, request_id):
        return await asyncio.to_thread(self._request, instruction, reference, image, request_id)
