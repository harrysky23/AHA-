import base64
import hashlib
from pathlib import Path
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ConfigurationError
from .routes.learn import router
from .routes.storyboard import router as storyboard_router
from .routes.videos import router as videos_router
from .services.video_jobs import VideoJobs
from .video_config import get_video_settings
from .services.errors import LearningError
import logging

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
MAX_BODY_BYTES = 6 * 1024 * 1024


class BoundedBodyMiddleware:
    """Bound the entire upload, including multipart overhead, before parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                response = JSONResponse({"detail": "요청이 너무 커요. 파일은 5MB 이하로 올려 주세요."}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


logging.getLogger("aha.generation").setLevel(logging.INFO)
if not logging.getLogger("aha.generation").handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logging.getLogger("aha.generation").addHandler(handler)
    logging.getLogger("aha.generation").propagate = False

@asynccontextmanager
async def lifespan(app):
    jobs = VideoJobs(get_video_settings())
    await jobs.start()
    app.state.video_jobs = jobs
    try:
        yield
    finally:
        await jobs.close()
        app.state.video_jobs = None


app = FastAPI(title="AHA!", version="0.3.0", lifespan=lifespan)
app.add_middleware(BoundedBodyMiddleware)
app.include_router(router)
app.include_router(storyboard_router)
app.include_router(videos_router)
app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")


@app.exception_handler(LearningError)
async def learning_error(request, exc: LearningError):
    data = {"detail":exc.message, "code":exc.code, "fallback_available":exc.fallback}
    headers = {}
    if request.url.path.startswith("/api/videos"):
        headers["Cache-Control"] = "private, no-store"
    if exc.retry_after is not None:
        data["retry_after_seconds"] = exc.retry_after
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(data, status_code=exc.status, headers=headers)


@app.exception_handler(ConfigurationError)
async def configuration_error(request, exc: ConfigurationError):
    return JSONResponse({"detail":str(exc), "code":"invalid_configuration", "fallback_available":True}, status_code=503)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/lessons/secant-tangent", response_class=HTMLResponse, include_in_schema=False)
async def lesson():
    return lesson_response((FRONTEND / "lessons" / "secant-tangent.html").read_text(encoding="utf-8"))


@app.get("/lessons/interactive", response_class=HTMLResponse, include_in_schema=False)
async def interactive_lesson():
    directory = FRONTEND / "lessons"
    html = (directory / "interactive.html").read_text(encoding="utf-8")
    html = html.replace("__MOTION_SCENE_SCRIPT__", (directory / "motion-scene.js").read_text(encoding="utf-8"))
    response = lesson_response(html.replace("__INTERACTIVE_SCRIPT__", (directory / "interactive.js").read_text(encoding="utf-8")), inline_images=True)
    response.headers["Cache-Control"] = "no-cache"
    return response


def lesson_response(html: str, *, inline_images: bool = False) -> HTMLResponse:
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in scripts)
    images = "img-src data:; " if inline_images else ""
    return HTMLResponse(html, headers={
        "Content-Security-Policy": f"default-src 'none'; script-src {hashes}; style-src 'unsafe-inline'; {images}connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox allow-scripts",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    })
