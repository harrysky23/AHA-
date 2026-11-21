import base64
import hashlib
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes.learn import router

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


app = FastAPI(title="AHA! Phase 1", version="0.1.0")
app.add_middleware(BoundedBodyMiddleware)
app.include_router(router)
app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/lessons/secant-tangent", response_class=HTMLResponse, include_in_schema=False)
async def lesson():
    html = (FRONTEND / "lessons" / "secant-tangent.html").read_text()
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in scripts)
    return HTMLResponse(html, headers={
        "Content-Security-Policy": f"default-src 'none'; script-src {hashes}; style-src 'unsafe-inline'; connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox allow-scripts",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    })
