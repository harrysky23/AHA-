"""Bounded, single-process local queue. All job mutations run on the ASGI loop."""
import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
import fcntl
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
from threading import Event
import time
from uuid import uuid4

from ..rendering.core import RenderError
from ..rendering.engine import render_storyboard
from ..video_config import VideoSettings
from .errors import LearningError
from .storyboard import create_storyboard

TERMINAL = {"completed", "failed", "cancelled"}
JOB_ID = re.compile(r"^[a-f0-9]{32}$")


@dataclass
class Job:
    id: str
    owner: str = field(repr=False)
    payload: dict | None = field(repr=False)
    settings: object = field(repr=False)
    created: float = 0
    expires: float = 0
    status: str = "queued"
    stage: str = "queued"
    progress: dict = field(default_factory=dict)
    error: dict | None = None
    result: dict | None = None
    cancel: Event = field(default_factory=Event, repr=False)
    cancel_reason: str | None = None
    expired: bool = False
    started: float | None = None
    generation_task: asyncio.Task | None = field(default=None, repr=False)
    leases: int = 0


class VideoJobs:
    def __init__(self, policy: VideoSettings, *, generate=create_storyboard, render=render_storyboard, clock=time.time):
        if render is render_storyboard and policy.renderer == "remotion":
            render=partial(render_storyboard,renderer="remotion")
        self.policy, self.generate, self.render, self.clock = policy, generate, render, clock
        self.jobs: dict[str, Job] = {}
        self.queue = deque()
        self.wake = asyncio.Event()
        self.closed = False
        self.storage_used = 0
        self.lock_fd = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aha-video")

    async def start(self):
        root = self.policy.root
        if root.is_symlink():
            raise RuntimeError("영상 작업 저장소에는 심볼릭 링크를 사용할 수 없어요.")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.lock_fd = os.open(root / ".service.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock_fd); self.lock_fd = None
            self.pool.shutdown(wait=False)
            raise RuntimeError("영상 작업 서버는 같은 저장소에서 1개 프로세스만 실행할 수 있어요.") from None
        # Previous server's worker watchdog gets a chance to stop orphan children.
        old = [p for p in root.iterdir() if JOB_ID.fullmatch(p.name)]
        if old:
            await asyncio.sleep(.5)
            for path in old:
                if path.is_symlink():
                    path.unlink()
                else:
                    await asyncio.to_thread(shutil.rmtree, path, True)
        self.runner = asyncio.create_task(self._run(), name="aha-video-runner")
        self.sweeper = asyncio.create_task(self._sweep_loop(), name="aha-video-expiry")

    def submit(self, owner: str, payload: dict, settings) -> dict:
        if self.closed:
            raise LearningError("jobs_unavailable", "영상 작업 서버가 종료 중이에요.", 503)
        if self.storage_used + self.policy.render.max_disk_bytes > self.policy.storage_bytes:
            raise LearningError("video_storage_full", "영상 저장 공간이 부족해요. 완료 영상을 삭제한 뒤 다시 시도해 주세요.", 507)
        # Bounded tombstones: keep cancelled/failed status for recovery until
        # capacity is needed; completed files are never evicted this way.
        for old in list(self.jobs.values()):
            if len(self.jobs) < self.policy.max_jobs:
                break
            if (old.status in {"cancelled", "failed"} and old.leases == 0
                    and not (self.policy.root / old.id).exists()):
                self.jobs.pop(old.id, None)
        waiting = sum(j.status == "queued" for j in self.jobs.values())
        if waiting >= self.policy.queue_limit or len(self.jobs) >= self.policy.max_jobs:
            raise LearningError("video_queue_full", "영상 대기열이 가득 찼어요. 기존 작업을 지우거나 잠시 후 다시 시도해 주세요.", 429, True, 5)
        if sum(j.owner == owner and j.status not in TERMINAL for j in self.jobs.values()) >= 2:
            raise LearningError("owner_job_limit", "한 브라우저에서 동시에 최대 2개 작업을 만들 수 있어요.", 429, True, 5)
        now = self.clock()
        job = Job(uuid4().hex, owner, payload, settings, now, now+self.policy.ttl_seconds)
        self.jobs[job.id] = job
        self.queue.append(job.id)
        self.wake.set()
        return self.public(job)

    def owned(self, job_id: str, owner: str) -> Job:
        job = self.jobs.get(job_id) if JOB_ID.fullmatch(job_id) else None
        if job is None or not hmac.compare_digest(job.owner, owner) or job.expired or self.clock() >= job.expires:
            raise LearningError("video_not_found", "영상을 찾을 수 없어요. 소유권·만료·서버 재시작 여부를 확인해 주세요.", 404, False)
        return job

    def public(self, job: Job):
        return {"job_id": job.id, "status": job.status, "stage": job.stage,
                "cancel_requested": job.cancel.is_set(), "error": job.error,
                "progress": dict(job.progress), "created_at": job.created, "expires_at": job.expires,
                "video_url": f"/api/videos/{job.id}/file" if job.status == "completed" and not job.cancel.is_set() else None,
                "result": job.result if job.status == "completed" else None}

    def path(self, job):
        return self.policy.root / job.id / "video.mp4"

    def request_cancel(self, job: Job, reason="user_cancelled"):
        job.cancel_reason = job.cancel_reason or reason
        job.cancel.set()
        if job.generation_task is not None:
            job.generation_task.cancel()
        if job.status == "queued":
            try:
                self.queue.remove(job.id)
            except ValueError:
                pass
            job.payload = None
            job.settings = None
            job.status, job.stage = "cancelled", "cancelled"
        self.wake.set()

    async def cancel(self, job: Job):
        if job.error and job.error["code"] == "cleanup_failed":
            raise LearningError("cleanup_failed", "자식 프로세스 종료를 확인하지 못한 작업은 취소 완료로 표시할 수 없어요.", 409, False)
        self.request_cancel(job)
        if job.status in TERMINAL:
            await self._clean_files(job)
            job.status, job.stage, job.result, job.error = "cancelled", "cancelled", None, None
        return self.public(job)

    async def _clean_files(self, job):
        if job.leases == 0:
            await asyncio.to_thread(shutil.rmtree, self.policy.root / job.id, True)

    def lease(self, job):
        if job.status != "completed" or job.cancel.is_set() or not self.path(job).is_file():
            raise LearningError("video_not_ready", "완료된 영상만 받을 수 있어요.", 409, False)
        job.leases += 1
        return self.path(job)

    async def release(self, job):
        job.leases -= 1
        if job.expired or job.cancel.is_set():
            await self._clean_files(job)

    def _progress(self, job, progress):
        if job.status != "rendering":
            return
        phase = progress.get("phase")
        if phase not in {"tts", "browser", "frames", "encode", "verify"}:
            return
        job.stage = phase
        job.progress = {k: progress[k] for k in ("scene_id", "frames_done", "frames_total") if k in progress}

    async def _execute(self, job):
        job.started = self.clock()
        job.status, job.stage = "generating", "analyzing"
        phase = "generation"
        try:
            if self.policy.renderer == "claude":
                from .generated_video import resolve_reference, run_generated_video
                job.generation_task = asyncio.create_task(resolve_reference(job.payload))
                reference, image, grounding = await job.generation_task
                job.generation_task = None
                job.payload, job.settings = None, None
                if job.cancel.is_set():
                    return
                await self.sweep()
                if self.storage_used + self.policy.render.max_disk_bytes > self.policy.storage_bytes:
                    raise LearningError("video_storage_full", "영상 저장 공간이 부족해요.", 507)
                phase = "rendering"
                job.status, job.stage = "rendering", "waiting_renderer"
                loop = asyncio.get_running_loop()
                def show_stage(stage):
                    loop.call_soon_threadsafe(setattr, job, "stage", stage)
                result = await loop.run_in_executor(self.pool, lambda: run_generated_video(
                    self.path(job), self.policy.render, job.cancel, reference, image, grounding, on_stage=show_stage))
                if not job.cancel.is_set():
                    job.result = result
                    job.status, job.stage, job.progress = "completed", "ready", {}
                return
            def stage(value):
                if not job.cancel.is_set():
                    job.stage = value
            job.generation_task = asyncio.create_task(self.generate(job.settings, **job.payload, on_stage=stage))
            data = await job.generation_task
            job.generation_task = None
            job.payload, job.settings = None, None
            if job.cancel.is_set():
                return
            phase = "rendering"
            await self.sweep()
            if self.storage_used + self.policy.render.max_disk_bytes > self.policy.storage_bytes:
                raise LearningError("video_storage_full", "영상 저장 공간이 부족해요. 완료 영상을 삭제해 주세요.", 507)
            job.status, job.stage = "rendering", "waiting_renderer"
            loop = asyncio.get_running_loop()
            def progress(value):
                loop.call_soon_threadsafe(self._progress, job, value)
            while not job.cancel.is_set():
                try:
                    report = await loop.run_in_executor(self.pool, lambda: self.render(
                        data["storyboard"], self.path(job), self.policy.render,
                        cancel_event=job.cancel, on_progress=progress))
                    break
                except RenderError as exc:
                    if exc.code != "render_busy":
                        raise
                    await asyncio.sleep(.3)
            else:
                return
            # Linearize publication on the loop, after renderer cleanup ack.
            if not job.cancel.is_set():
                job.result = {"mode": data["mode"], "generation": data["generation"], "grounding": data["grounding"],
                              "media": report["media"], "fallbacks": report["layout"]["fallbacks"]}
                job.status, job.stage, job.progress = "completed", "ready", {}
        except asyncio.CancelledError:
            # Only the generation child task is cancelled by normal operations.
            job.cancel.set()
        except (LearningError, RenderError) as exc:
            job.error = {"code": exc.code, "message": exc.message, "phase": phase,
                         "scene_id": getattr(exc, "scene_id", None)}
        except Exception:
            job.error = {"code": "video_job_failed", "message": "영상 작업 중 오류가 발생했어요.", "phase": phase, "scene_id": None}
        finally:
            job.payload, job.settings, job.generation_task = None, None, None
            if job.status == "completed" and not job.cancel.is_set():
                return
            final_status, final_error = "failed", job.error
            if job.cancel.is_set() and (not job.error or job.error["code"] != "cleanup_failed"):
                if job.cancel_reason == "job_timeout":
                    final_error = {"code": "video_job_timeout", "message": "영상 작업의 전체 처리 시간을 초과했어요.", "phase": phase, "scene_id": job.progress.get("scene_id")}
                else:
                    final_status, final_error = "cancelled", None
            # Failed Claude jobs retain private TSX and diagnostics until deletion or expiry.
            if self.policy.renderer != "claude" or job.cancel.is_set():
                await self._clean_files(job)
            job.result, job.error, job.status, job.stage = None, final_error, final_status, final_status

    async def _run(self):
        while not self.closed or self.queue:
            if not self.queue:
                self.wake.clear()
                await self.wake.wait()
                continue
            job = self.jobs.get(self.queue.popleft())
            if job and job.status == "queued":
                await self._execute(job)

    async def sweep(self):
        now = self.clock()
        for job in list(self.jobs.values()):
            if now >= job.expires:
                job.expired = True
                self.request_cancel(job, "expired")
            elif job.started is not None and job.status not in TERMINAL and now-job.started >= self.policy.run_seconds:
                self.request_cancel(job, "job_timeout")
            if job.expired and job.status in TERMINAL and not job.leases:
                await self._clean_files(job)
                self.jobs.pop(job.id, None)
        # Reserve the entire next renderer budget, not just current MP4 sizes.
        def disk_size():
            size = 0
            for path in self.policy.root.rglob("*"):
                try:
                    if path.is_file():
                        size += path.stat().st_size
                except FileNotFoundError:
                    pass
            return size
        size = await asyncio.to_thread(disk_size)
        self.storage_used = size

    async def _sweep_loop(self):
        while not self.closed:
            await self.sweep()
            await asyncio.sleep(1)

    async def close(self):
        self.closed = True
        for job in self.jobs.values():
            if job.status not in TERMINAL:
                self.request_cancel(job, "shutdown")
        self.wake.set()
        await self.runner
        self.sweeper.cancel()
        await asyncio.gather(self.sweeper, return_exceptions=True)
        self.pool.shutdown(wait=True)
        for job in list(self.jobs.values()):
            await self._clean_files(job)
        self.jobs.clear()
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None


def owner_digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()
