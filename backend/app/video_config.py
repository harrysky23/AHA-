"""Local job policy, independent of AI provider settings."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values

from .config import ROOT, ConfigurationError
from .rendering.core import RenderOptions


@dataclass(frozen=True)
class VideoSettings:
    root: Path = ROOT / "tmp/video-jobs"
    queue_limit: int = 3
    max_jobs: int = 16
    ttl_seconds: int = 3600
    run_seconds: int = 900
    storage_bytes: int = 2048 * 1024**2
    render: RenderOptions = field(default_factory=RenderOptions)
    renderer: str = "svg"


def get_video_settings():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    try:
        preview = env.get("AHA_VIDEO_PREVIEW", "false")
        if preview not in {"true", "false"}:
            raise ValueError()
        value = VideoSettings(
            renderer=env.get("AHA_VIDEO_RENDERER", "svg"),
            queue_limit=int(env.get("AHA_VIDEO_QUEUE_LIMIT", "3")), max_jobs=int(env.get("AHA_VIDEO_MAX_JOBS", "16")),
            ttl_seconds=int(env.get("AHA_VIDEO_TTL_SECONDS", "3600")), run_seconds=int(env.get("AHA_VIDEO_RUN_SECONDS", "900")),
            storage_bytes=int(env.get("AHA_VIDEO_STORAGE_MB", "2048"))*1024**2,
            render=RenderOptions(preview=preview == "true", fps=int(env.get("AHA_VIDEO_FPS", "30")),
                timeout_seconds=int(env.get("AHA_VIDEO_RENDER_TIMEOUT_SECONDS", "600")),
                max_disk_bytes=int(env.get("AHA_VIDEO_MAX_DISK_MB", "512"))*1024**2))
        if not (value.renderer in {"svg","remotion","claude"} and 1 <= value.queue_limit <= 8 and value.queue_limit + 1 <= value.max_jobs <= 64
                and 120 <= value.ttl_seconds <= 7200 and 10 <= value.run_seconds <= 1800
                and 512*1024**2 <= value.storage_bytes <= 4096*1024**2):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ConfigurationError("영상 작업 설정 범위를 확인해 주세요. README의 AHA_VIDEO 설정을 참고하세요.") from None
