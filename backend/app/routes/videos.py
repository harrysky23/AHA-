"""Session-owned asynchronous jobs. Cookie secrets never appear in URLs/logs."""
import re
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from ..config import Settings, get_settings
from ..services.errors import LearningError
from ..services.storyboard_input import read_storyboard_input
from ..services.video_jobs import VideoJobs, owner_digest

router = APIRouter(prefix="/api/videos")
COOKIE = "aha_video_owner"
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
PRIVATE = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}


def get_jobs(request: Request) -> VideoJobs:
    jobs = getattr(request.app.state, "video_jobs", None)
    if jobs is None:
        raise LearningError("jobs_unavailable", "영상 작업 서버가 준비되지 않았어요.", 503)
    return jobs


def session(request, create=False):
    token = request.cookies.get(COOKIE, "")
    if not TOKEN.fullmatch(token):
        token = secrets.token_urlsafe(32) if create else ""
    return token


def same_origin(request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise LearningError("cross_origin_denied", "같은 AHA! 페이지에서만 작업을 변경할 수 있어요.", 403, False)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise LearningError("cross_origin_denied", "외부 사이트의 작업 요청은 허용하지 않아요.", 403, False)


@router.post("", status_code=202)
async def create(request: Request, settings: Settings = Depends(get_settings), jobs: VideoJobs = Depends(get_jobs)):
    same_origin(request)
    claude = jobs.policy.renderer == "claude"
    data = await read_storyboard_input(request, settings, claude=claude)
    if not claude and settings.mode == "gemini":
        settings.validate_gemini()
    token = session(request, create=True)
    result = jobs.submit(owner_digest(token), data, settings)
    response = JSONResponse(result, status_code=202, headers={**PRIVATE, "Location": f"/api/videos/{result['job_id']}"})
    response.set_cookie(COOKIE, token, max_age=86400, httponly=True, samesite="strict", secure=request.url.scheme == "https", path="/api/videos")
    return response


@router.get("/{job_id}")
async def status(job_id: str, request: Request, jobs: VideoJobs = Depends(get_jobs)):
    job = jobs.owned(job_id, owner_digest(session(request)))
    return JSONResponse(jobs.public(job), headers=PRIVATE)


@router.delete("/{job_id}")
async def cancel(job_id: str, request: Request, jobs: VideoJobs = Depends(get_jobs)):
    same_origin(request)
    job = jobs.owned(job_id, owner_digest(session(request)))
    result = await jobs.cancel(job)
    return JSONResponse(result, status_code=200 if result["status"] == "cancelled" else 202, headers=PRIVATE)


class OwnedVideoResponse(FileResponse):
    """Pin a verified file across Range/conditional streaming and disconnects."""
    def __init__(self, jobs, job, **kwargs):
        self.jobs, self.job = jobs, job
        super().__init__(jobs.lease(job), **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.jobs.release(self.job)


@router.get("/{job_id}/file")
async def file(job_id: str, request: Request, jobs: VideoJobs = Depends(get_jobs)):
    job = jobs.owned(job_id, owner_digest(session(request)))
    download = request.query_params.get("download") == "1"
    return OwnedVideoResponse(jobs, job, media_type="video/mp4", filename="aha-learning.mp4",
                             content_disposition_type="attachment" if download else "inline", headers=PRIVATE)
