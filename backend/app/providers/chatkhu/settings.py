"""Server-only ChatKHU media settings. Not part of the Gemini provider switch."""
from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit

from dotenv import dotenv_values

from ...config import ROOT, ConfigurationError

OFFICIAL_BASE = "https://factchat-cloud.mindlogic.ai/v1/gateway"
IMAGE_MODELS = {"gemini-3.1-flash-lite-image", "gemini-3.1-flash-image-preview"}
VIDEO_MODELS = {"fal-ai/kling-video/v3", "bytedance/seedance-2.0"}
TTS_MODELS = {"gemini-3.1-flash-tts-preview"}


@dataclass(frozen=True)
class ChatKHUSettings:
    api_key: str = field(default="", repr=False)
    base_url: str = OFFICIAL_BASE
    image_model: str = "gemini-3.1-flash-lite-image"
    video_model: str = "fal-ai/kling-video/v3"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    request_timeout: float = 120
    operation_timeout: float = 600
    max_polls: int = 60

    def validate(self, require_key=False):
        parsed = urlsplit(self.base_url)
        if (parsed.scheme != "https" or parsed.netloc != "factchat-cloud.mindlogic.ai"
                or parsed.path.rstrip("/") != "/v1/gateway" or parsed.query or parsed.fragment):
            raise ConfigurationError("CHATKHU_BASE_URL은 공식 HTTPS Gateway 주소여야 해요.")
        if (self.image_model not in IMAGE_MODELS or self.video_model not in VIDEO_MODELS
                or self.tts_model not in TTS_MODELS):
            raise ConfigurationError("ChatKHU 모델은 문서에서 확인한 이번 검증 후보 중 하나를 설정해 주세요.")
        if require_key and not self.api_key:
            raise ConfigurationError("서버 .env에 CHATKHU_API_KEY를 설정해 주세요.")
        if any(c.isspace() for c in self.api_key):
            raise ConfigurationError("CHATKHU_API_KEY 형식을 확인해 주세요. 값은 표시하지 않아요.")
        if not 1 <= self.request_timeout <= 120 or not 1 <= self.operation_timeout <= 900 or not 1 <= self.max_polls <= 60:
            raise ConfigurationError("ChatKHU 제한 시간과 조회 횟수 설정을 확인해 주세요.")

    def public(self):
        self.validate()
        return {"key_present": bool(self.api_key), "base_url": self.base_url.rstrip("/"),
                "image_model": self.image_model, "video_model": self.video_model, "tts_model": self.tts_model}


def get_chatkhu_settings():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    settings = ChatKHUSettings(api_key=values.get("CHATKHU_API_KEY", "") or "",
        base_url=values.get("CHATKHU_BASE_URL", OFFICIAL_BASE) or OFFICIAL_BASE,
        image_model=values.get("CHATKHU_IMAGE_MODEL", "gemini-3.1-flash-lite-image") or "",
        video_model=values.get("CHATKHU_VIDEO_MODEL", "fal-ai/kling-video/v3") or "",
        tts_model=values.get("CHATKHU_TTS_MODEL", "gemini-3.1-flash-tts-preview") or "")
    settings.validate()
    return settings
