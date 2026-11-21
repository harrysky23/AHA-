"""Bounded process-local TTL/LRU. Only validated output is stored; no disk or raw-input keys."""
import asyncio
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
from threading import RLock
import time

from ..config import Settings
from ..providers.base import GenerationInput, ProviderResult
from ..schemas import LessonSpec
from .errors import LearningError
from . import prompts


@dataclass
class Entry:
    expires_at: float
    value: ProviderResult


class LessonCache:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.salt = secrets.token_bytes(32)
        self.entries: OrderedDict[str, Entry] = OrderedDict()
        self.pending: dict[str, Future] = {}
        self.lock = RLock()

    def key(self, provider: str, model: str, settings: Settings, request: GenerationInput) -> str:
        # Exact sent data, schema, prompt version and generation settings invalidate reuse.
        # Account separation protects against credential changes sharing prior outputs.
        credential = hmac.new(self.salt, settings.api_key.encode(), hashlib.sha256).hexdigest()
        canonical = json.dumps({"provider":provider, "model":model, "credential":credential,
            "prompt_version":prompts.PROMPT_VERSION, "schema":LessonSpec.model_json_schema(),
            "max_output_tokens":settings.max_output_tokens,
            "messages":prompts.build_messages(request.concept,request.question,request.material,include_schema=False)},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hmac.new(self.salt, canonical.encode(), hashlib.sha256).hexdigest()

    def clear(self):
        with self.lock:
            self.entries.clear()

    async def get_or_create(self, key: str, factory, ttl: int, max_entries: int) -> tuple[ProviderResult, str]:
        if ttl == 0:
            self.clear()
            return await factory(), "disabled"
        with self.lock:
            for old_key in list(self.entries):
                if self.entries[old_key].expires_at <= self.clock():
                    del self.entries[old_key]
            while len(self.entries) > max_entries:
                self.entries.popitem(last=False)
            if key in self.entries:
                entry = self.entries.pop(key)
                self.entries[key] = entry
                return deepcopy(entry.value), "hit"
            owner = key not in self.pending
            future = self.pending.setdefault(key, Future())
        if not owner:
            # Canceling a waiter must not cancel another request's upstream generation.
            value = await asyncio.shield(asyncio.wrap_future(future))
            return deepcopy(value), "hit"
        try:
            value = await factory()
            with self.lock:
                self.entries[key] = Entry(self.clock()+ttl, deepcopy(value))
                while len(self.entries) > max_entries:
                    self.entries.popitem(last=False)
                future.set_result(deepcopy(value))
            return value, "miss"
        except BaseException as exc:
            with self.lock:
                future.set_exception(exc if isinstance(exc, Exception) else LearningError("generation_cancelled", "생성이 중단됐어요. 다시 시도하거나 기본 예제를 열어 주세요.", 503))
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)


lesson_cache = LessonCache()
