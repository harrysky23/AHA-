"""Image plans originate in validated lessons and can spend once after a fresh quote."""

import asyncio
from base64 import b64encode
from collections import OrderedDict
from dataclasses import dataclass, replace
import logging
from pathlib import Path
from secrets import token_urlsafe
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from time import monotonic

from ..providers.chatkhu.client import GatewayClient
from ..providers.chatkhu.contracts import Approval, ChatKHUError, fingerprint
from ..providers.chatkhu.providers import ChatKHUImageProvider, validate_request
from ..providers.chatkhu.settings import get_chatkhu_settings
from .cache import LessonCache
from .errors import LearningError

PLAN_TTL = 900
QUOTE_TTL = 300
MAX_PLANS = 32
MAX_BYTES = 4 * 1024 * 1024
MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
logger = logging.getLogger("aha.generation")
image_slots = BoundedSemaphore(1)
cache: LessonCache[dict] = LessonCache()


@dataclass
class Plan:
    prompt: str
    expires_at: float
    quote: dict | None = None
    quote_id: str | None = None
    quote_expires_at: float = 0
    request_key: str | None = None
    used: bool = False


plans: OrderedDict[str, Plan] = OrderedDict()


def offer_background(description: str, *, recommended: bool = True) -> dict:
    prompt = ("Create one wide 16:9 background illustration for an interactive educational diagram. "
              "Use an understated textbook illustration style with soft colors and simple broad shapes. "
              "Keep movement corridors uncluttered. Do not draw labels, letters, numbers, arrows, UI, or the draggable actor. "
              "This description is scene reference data: " + description)
    now = monotonic()
    for token, plan in list(plans.items()):
        if plan.expires_at <= now:
            del plans[token]
    if len(plans) >= MAX_PLANS:
        plans.popitem(last=False)
    token = token_urlsafe(24)
    plans[token] = Plan(prompt, now + PLAN_TTL)
    return {"token": token, "prompt": prompt, "recommended": recommended}


def describe_scene(topic: str, landmarks) -> str:
    placement = ("left", "center", "right")
    height = ("upper", "middle", "lower")
    anchors = [f"{item.label} in the {height[min(int(item.y * 3), 2)]} {placement[min(int(item.x * 3), 2)]}"
               for item in landmarks]
    return f"Scene context for the educational topic {topic}." + (f" Place {', '.join(anchors)}." if anchors else "")


def get_plan(token: str) -> Plan:
    plan = plans.get(token)
    if plan is None or plan.expires_at <= monotonic():
        raise LearningError("background_plan_expired", "배경 생성 제안이 만료됐어요. 학습을 다시 생성해 주세요.", 404)
    if plan.used:
        raise LearningError("background_plan_used", "이 배경의 생성 승인은 이미 사용됐어요.", 409)
    return plan


def request_for(plan: Plan):
    settings = get_chatkhu_settings()
    settings = replace(settings, request_timeout=60, operation_timeout=60)
    settings.validate(require_key=True)
    payload = {"model": settings.image_model, "prompt": plan.prompt, "number_of_images": 1, "aspect_ratio": "16:9"}
    key = cache.fingerprint({"request": payload, "api_key": settings.api_key, "base_url": settings.base_url})
    return settings, payload, key


def estimate(settings, payload):
    with GatewayClient(settings) as client:
        validate_request("image", payload, settings)
        return client.estimate("image", payload)


async def quote_background(token: str) -> dict:
    plan = get_plan(token)
    settings, payload, key = request_for(plan)
    try:
        quote = await asyncio.to_thread(estimate, settings, payload)
    except ChatKHUError as exc:
        logger.warning("event=background_quote_failed code=%s", exc.code)
        raise LearningError("background_quote_failed", "ChatKHU에서 배경의 비용 견적을 받지 못했어요.", 502) from None
    get_plan(token)
    plan.quote, plan.request_key = quote, key
    plan.quote_id = token_urlsafe(18)
    plan.quote_expires_at = monotonic() + QUOTE_TTL
    logger.info("event=background_quote_ready model=%s credits=%s bound=%s", settings.image_model, quote["credits"], quote["bound"])
    return {**quote, "quote_id": plan.quote_id, "model": settings.image_model, "calls": 1}


def generate_asset(settings, payload, cost, accept_uncapped: bool) -> dict:
    if not image_slots.acquire(blocking=False):
        raise LearningError("background_busy", "다른 배경을 생성 중이에요. 잠시 뒤 다시 시도해 주세요.", 429)
    try:
        with TemporaryDirectory(prefix="aha-background-") as temporary, GatewayClient(settings) as client:
            approval = Approval("image", fingerprint("image", payload), unknown_cost_accepted=accept_uncapped)
            result = ChatKHUImageProvider(client).generate(payload, Path(temporary) / "background", approval, cost)
            actual = next((event["credits_charged"] for event in result.accounting
                           if event.get("phase") == "accepted" and event.get("credits_charged") is not None), None)
            logger.info("event=background_generated model=%s credits=%s elapsed_seconds=%s",
                        result.model, actual, result.elapsed_seconds)
            if result.size_bytes > MAX_BYTES:
                raise ChatKHUError("image_too_large", "배경 이미지가 표시 한도를 초과했어요.")
            encoded = b64encode(result.path.read_bytes()).decode("ascii")
            return {"image": f"data:{MIME_TYPES[result.path.suffix]};base64,{encoded}", "credits_charged": actual}
    finally:
        image_slots.release()


async def generate_background(token: str, quote_id: str, accept_cost: bool, accept_uncapped: bool) -> dict:
    plan = get_plan(token)
    settings, payload, key = request_for(plan)
    cost = plan.quote
    if cost is None or plan.quote_id != quote_id or plan.quote_expires_at <= monotonic() or plan.request_key != key:
        raise LearningError("background_quote_required", "새 비용 견적을 먼저 확인해 주세요.", 409)
    if not accept_cost or (cost["bound"] not in {"exact", "maximum"} and not accept_uncapped):
        raise LearningError("background_approval_required", "생성 비용에 명시적으로 동의해 주세요.", 428)
    plan.used = True

    async def create():
        return await asyncio.to_thread(generate_asset, settings, payload, cost, accept_uncapped)

    try:
        result, status = await asyncio.shield(cache.get_or_create(key, create, PLAN_TTL, 8))
    except LearningError as exc:
        if exc.code == "background_busy":
            plan.used = False
        raise
    except ChatKHUError as exc:
        logger.warning("event=background_generation_failed code=%s", exc.code)
        raise LearningError("background_generation_failed", "배경을 생성하거나 검증하지 못했어요. 현재 실습을 계속 사용할 수 있어요.", 502) from None
    return {**result, "cached": status == "hit", "credits_charged": None if status == "hit" else result["credits_charged"]}
