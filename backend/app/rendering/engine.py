"""Synchronous render entry point; one local job, bounded disposable worker."""
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from pydantic import ValidationError

from ..storyboard_schema import StoryboardSpec
from .core import Budget, RenderError, RenderOptions, executable

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def render_slot():
    # Shared by all CLI/API callers for this OS user, including other checkouts.
    path = Path(tempfile.gettempdir()) / f"aha-render-{os.getuid()}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RenderError("render_busy", "다른 영상이 렌더링 중이에요. 완료 후 다시 시도해 주세요.") from None
        yield
    finally:
        os.close(fd)


def validate_spec(value) -> StoryboardSpec:
    try:
        # Revalidate even a previously validated (but possibly mutated) instance.
        data = value.model_dump() if isinstance(value, StoryboardSpec) else value
        return StoryboardSpec.model_validate(data)
    except (ValidationError, TypeError, ValueError, RecursionError):
        raise RenderError("invalid_storyboard", "StoryboardSpec 검증에 실패했어요. 시간·시각화·참조를 확인해 주세요.") from None


def _stop(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def render_storyboard(value, output: Path, options: RenderOptions | None = None) -> dict:
    """Render a validated spec to a local file. Never reads .env or calls AI.

    No source-grounding claim: quote matching belongs to the generation service
    with access to the original PDF. This boundary validates DSL/timing only.
    """
    spec = validate_spec(value)
    options = options or RenderOptions()
    output = Path(output).resolve()
    if output.suffix.lower() != ".mp4":
        raise RenderError("invalid_output", "출력 파일 확장자는 .mp4여야 해요.")
    report_path = output.with_suffix(".render.json")
    if output.exists() or report_path.exists():
        raise RenderError("output_exists", "출력 파일이 이미 있어요. 다른 파일명을 선택해 주세요.")
    executable("ffmpeg")
    executable("ffprobe")
    with render_slot():
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".aha-render-", dir=output.parent) as directory:
            work = Path(directory)
            budget = Budget(work, options)
            (work / "input.json").write_text(spec.model_dump_json(), encoding="utf-8")
            (work / "options.json").write_text(json.dumps(asdict(options)), encoding="utf-8")
            # No .env loaded and no GEMINI_API_KEY/other credentials inherited.
            env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "AHA_BROWSER_EXECUTABLE"}}
            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            process = subprocess.Popen([sys.executable, "-m", "backend.app.rendering.worker", str(work)],
                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False, start_new_session=True)
            try:
                while process.poll() is None:
                    try:
                        progress = json.loads((work / "progress.json").read_text())
                        budget.scene_id = progress.get("scene_id")
                    except (OSError, ValueError):
                        pass
                    budget.check()
                    time.sleep(.1)
                budget.check()
                if process.returncode:
                    try:
                        failure = json.loads((work / "error.json").read_text())
                    except (OSError, ValueError):
                        raise RenderError("worker_failed", "렌더링 프로세스가 비정상 종료됐어요.", budget.scene_id) from None
                    raise RenderError(failure["code"], failure["message"], failure.get("scene_id") or budget.scene_id)
                report = json.loads((work / "report.json").read_text())
                # Publish only after successful encode, probe and complete decode.
                # Hard links provide no-overwrite semantics even if a local file
                # appears after the initial existence check. Same filesystem.
                os.link(work / "result.mp4", output)
                try:
                    os.link(work / "report.json", report_path)
                except OSError:
                    output.unlink()
                    raise
                return report
            finally:
                # Also reap remaining descendants when the worker itself has
                # already crashed/exited; they may still own the process group.
                _stop(process)
