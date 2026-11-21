"""Synchronous render entry point; one local job, bounded disposable worker."""
from contextlib import contextmanager, ExitStack
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
from threading import Event
from typing import Callable

from pydantic import ValidationError

from ..storyboard_schema import StoryboardSpec
from .core import Budget, RenderError, RenderOptions, executable
from .processes import ProcessTree

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


def render_storyboard(value, output: Path, options: RenderOptions | None = None, *,
                      cancel_event: Event | None = None, on_progress: Callable[[dict], None] | None = None,
                      media_plan=None, asset_root: Path | None = None,
                      renderer: str = "svg", animation_plan=None, audit: bool = False) -> dict:
    """Render a validated spec to a local file. Never reads .env or calls AI.

    No source-grounding claim: quote matching belongs to the generation service
    with access to the original PDF. This boundary validates DSL/timing only.
    """
    spec = validate_spec(value)
    options = options or RenderOptions()
    if renderer not in {"svg","remotion"}:
        raise RenderError("invalid_renderer", "지원하는 렌더러는 svg 또는 remotion이에요.")
    if type(audit) is not bool or (audit and renderer!="remotion"):
        raise RenderError("invalid_renderer", "프레임 감사는 Remotion에서만 사용할 수 있어요.")
    animation = None
    if animation_plan is not None:
        try:
            from ..remotion_schema import RemotionPlan
            animation = RemotionPlan.model_validate(animation_plan.model_dump() if isinstance(animation_plan,RemotionPlan) else animation_plan).bind(spec)
            if renderer != "remotion":
                raise ValueError()
        except (ValueError,TypeError,ValidationError):
            raise RenderError("invalid_animation_plan", "장면·자막 타이밍과 원본 명세를 확인해 주세요.") from None
    plan = None
    if media_plan is not None:
        from .multimodal import parse_media_plan
        plan = parse_media_plan(media_plan, spec)
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise RenderError("render_cancelled", "영상 생성을 취소했어요.")
    check_cancel()
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
        with tempfile.TemporaryDirectory(prefix=".aha-render-", dir=output.parent) as directory, ExitStack() as runtime:
            work = Path(directory)
            budget = Budget(work, options)
            (work / "input.json").write_text(spec.model_dump_json(), encoding="utf-8")
            (work / "options.json").write_text(json.dumps(asdict(options)), encoding="utf-8")
            if renderer == "remotion":
                (work / "renderer.json").write_text(json.dumps({"renderer":"remotion"}))
                # Webpack treats ! as loader syntax, including in absolute paths.
                # Parent owns this lexical view and removes it AFTER reaping the
                # worker. Actual output/profile bytes remain inside the budget.
                alias=Path(runtime.enter_context(tempfile.TemporaryDirectory(prefix="aha-remotion-",dir="/private/tmp" if Path("/private/tmp").is_dir() else "/tmp")))
                (alias/"project").symlink_to(ROOT/"video-remotion",target_is_directory=True)
                (alias/"work").symlink_to(work,target_is_directory=True)
                (work/"remotion-runtime.json").write_text(json.dumps({"project":str(alias/"project"),"work":str(alias/"work"),"audit":audit}))
            if animation is not None:
                (work / "animation-plan.json").write_text(animation.model_dump_json())
            if plan is not None:
                from .multimodal import stage_media
                stage_media(plan,asset_root,work,budget,cancel_event)
            # No .env loaded and no GEMINI_API_KEY/other credentials inherited.
            env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "AHA_BROWSER_EXECUTABLE"}}
            env["PYTHONPATH"] = str(ROOT)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            runtime_tmp = work / "runtime-tmp"
            runtime_tmp.mkdir(mode=0o700)
            # Include Playwright/Chromium profiles in the job's disk budget and
            # cleanup, even when cancellation skips browser.close().
            env["TMPDIR"] = str(runtime_tmp)
            process = subprocess.Popen([sys.executable, "-m", "backend.app.rendering.worker", str(work)],
                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False, start_new_session=True)
            tree = ProcessTree(process.pid)
            tracking_ready = False
            try:
                try:
                    tree.capture()
                    tracking_ready = True
                except PermissionError:
                    raise RenderError("process_tracking_denied", "자식 프로세스를 확인할 권한이 없어 안전하게 렌더링을 시작할 수 없어요.") from None
                parent_file = work / "parent.tmp"
                parent_file.write_text(json.dumps({"parent_pid": os.getpid()}))
                parent_file.replace(work / "parent.json")
                last_progress = None
                while process.poll() is None:
                    check_cancel()
                    tree.capture()
                    try:
                        progress = json.loads((work / "progress.json").read_text())
                        budget.scene_id = progress.get("scene_id")
                        if progress != last_progress and on_progress:
                            on_progress(progress)
                            last_progress = progress
                    except (OSError, ValueError):
                        pass
                    budget.check()
                    time.sleep(.1)
                budget.check()
                check_cancel()
                if process.returncode:
                    try:
                        failure = json.loads((work / "error.json").read_text())
                    except (OSError, ValueError):
                        raise RenderError("worker_failed", "렌더링 프로세스가 비정상 종료됐어요.", budget.scene_id) from None
                    raise RenderError(failure["code"], failure["message"], failure.get("scene_id") or budget.scene_id)
                report = json.loads((work / "report.json").read_text())
                check_cancel()
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
                try:
                    clean = tree.stop() if tracking_ready else True
                    if not tracking_ready:
                        _stop(process)
                    process.wait()
                except Exception:
                    _stop(process)
                    raise RenderError("cleanup_failed", "렌더링 프로세스 정리를 확인하지 못했어요.", budget.scene_id) from None
                if not clean:
                    raise RenderError("cleanup_failed", "렌더링 자식 프로세스 종료를 확인하지 못했어요.", budget.scene_id)
