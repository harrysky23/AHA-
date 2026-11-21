"""Data-only media contracts and explicit single-request spending authorization."""
from dataclasses import dataclass, field
import hashlib
import hmac
import json
from pathlib import Path
from typing import Literal, Protocol

Kind = Literal["image", "video", "tts"]


class ChatKHUError(Exception):
    def __init__(self, code, message, status=None, operation_id=None):
        super().__init__(message)
        self.code, self.message, self.status, self.operation_id = code, message, status, operation_id


def fingerprint(kind: Kind, payload: dict) -> str:
    canonical = json.dumps({"kind": kind, "request": payload}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Approval:
    kind: Kind
    request_hash: str
    unknown_cost_accepted: bool = False
    used: bool = field(default=False, init=False)

    def consume(self, kind, payload, cost):
        if self.used:
            raise ChatKHUError("call_limit", "이 승인은 이미 사용됐어요. 생성 요청을 다시 보내지 않아요.")
        if self.kind != kind or not hmac.compare_digest(self.request_hash, fingerprint(kind, payload)):
            raise ChatKHUError("approval_mismatch", "승인한 모델·입력과 요청이 달라요. 새 요청 계획을 확인해 주세요.")
        if cost.get("bound") not in {"exact", "maximum"} and not self.unknown_cost_accepted:
            raise ChatKHUError("cost_confirmation_required", "최종 비용 상한을 확인하지 못했어요. 비용 미확정 상태의 실행을 별도로 승인해야 해요.")
        # Reserve before sending: a timeout/error may still have consumed credit.
        self.used = True


@dataclass(frozen=True)
class MediaArtifact:
    kind: Kind
    model: str
    path: Path
    sha256: str
    size_bytes: int
    metadata: dict
    elapsed_seconds: float
    accounting: list[dict]


class ImageProvider(Protocol):
    def generate(self, payload: dict, output: Path, approval: Approval, cost: dict) -> MediaArtifact: ...


class VideoProvider(Protocol):
    def generate(self, payload: dict, output: Path, approval: Approval, cost: dict) -> MediaArtifact: ...


class SpeechProvider(Protocol):
    def generate(self, payload: dict, output: Path, approval: Approval, cost: dict) -> MediaArtifact: ...
