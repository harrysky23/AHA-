"""Resource policy and safe process boundary shared by rendering adapters."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


class RenderError(Exception):
    def __init__(self, code: str, message: str, scene_id: str | None = None):
        super().__init__(message)
        self.code, self.message, self.scene_id = code, message, scene_id

    def as_dict(self):
        # Only fixed diagnostics and validated IDs. Never subprocess stderr/input.
        return {"code": self.code, "message": self.message, "scene_id": self.scene_id}


@dataclass(frozen=True)
class RenderOptions:
    preview: bool = False
    fps: int = 30
    timeout_seconds: int = 600
    max_disk_bytes: int = 512 * 1024 * 1024
    min_free_bytes: int = 256 * 1024 * 1024

    def __post_init__(self):
        if type(self.preview) is not bool or type(self.fps) is not int or not 1 <= self.fps <= 30:
            raise ValueError("preview must be bool; fps must be an integer in 1..30")
        if type(self.timeout_seconds) is not int or not 10 <= self.timeout_seconds <= 1800:
            raise ValueError("timeout must be 10..1800 seconds")
        if not 1024 * 1024 <= self.max_disk_bytes <= 2 * 1024**3 or self.min_free_bytes < 0:
            raise ValueError("Invalid disk budget")

    @property
    def size(self):
        return (540, 960) if self.preview else (1080, 1920)


class Budget:
    def __init__(self, root: Path, options: RenderOptions):
        self.root, self.options = root, options
        self.deadline = time.monotonic() + options.timeout_seconds
        self.scene_id = None

    def remaining(self):
        value = self.deadline - time.monotonic()
        if value <= 0:
            raise RenderError("render_timeout", "렌더링 시간 제한을 초과했어요.", self.scene_id)
        return value

    def check(self):
        self.remaining()
        used = 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    used += path.stat().st_size
            except FileNotFoundError:
                # The worker may remove a completed audio/frame file concurrently.
                continue
        if used > self.options.max_disk_bytes:
            raise RenderError("disk_limit", "렌더링 임시 파일 용량 제한을 초과했어요.", self.scene_id)
        if shutil.disk_usage(self.root).free < self.options.min_free_bytes:
            raise RenderError("disk_full", "렌더링에 필요한 디스크 여유 공간이 부족해요.", self.scene_id)


def executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RenderError("dependency_missing", f"필수 실행 도구 {name}이 설치되어 있지 않아요.")
    return path


def run_process(command: list[str], budget: Budget, code: str, *, input_data: bytes | None = None):
    """No shell or inherited API keys; bounded child lifetime.

    Children only receive a minimal local environment. stderr is never surfaced
    because voice/browser/encoder diagnostics can include user text or paths.
    """
    budget.check()
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}}
    try:
        with subprocess.Popen(command, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, env=env) as process:
            try:
                output, _ = process.communicate(input_data, timeout=budget.remaining())
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise RenderError("render_timeout", "로컬 처리 중 시간 제한을 초과했어요.", budget.scene_id) from None
            if process.returncode:
                raise RenderError(code, "로컬 처리 도구 실행에 실패했어요. 설치와 음성 설정을 확인해 주세요.", budget.scene_id)
    except OSError:
        raise RenderError(code, "로컬 처리 도구를 실행할 수 없어요.", budget.scene_id) from None
    budget.check()
    return output


def probe(path: Path, budget: Budget) -> dict:
    raw = run_process([executable("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], budget, "probe_failed")
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        raise RenderError("probe_failed", "미디어 정보를 읽지 못했어요.", budget.scene_id) from None
