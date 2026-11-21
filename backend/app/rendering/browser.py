"""Network-denied, locally owned HTML/SVG scene template."""
import base64
import hashlib
import os
from pathlib import Path

from .core import Budget, RenderError

ASSETS = Path(__file__).parent / "assets"


def template_html() -> str:
    javascript = (ASSETS / "scene.js").read_text(encoding="utf-8")
    css = (ASSETS / "scene.css").read_text(encoding="utf-8")
    digest = base64.b64encode(hashlib.sha256(javascript.encode()).digest()).decode()
    csp = (f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; "
           "connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; "
           "frame-src 'none'; object-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'")
    return (ASSETS / "scene.html").read_text(encoding="utf-8").replace("__CSP__", csp).replace("__CSS__", css).replace("__JS__", javascript)


def browser_executable():
    # Trusted local runtime configuration, never from the storyboard/LLM.
    configured = os.environ.get("AHA_BROWSER_EXECUTABLE")
    if configured:
        return configured
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return chrome if Path(chrome).is_file() else None


class FrameRenderer:
    def __init__(self, spec, budget: Budget, *, layered=False):
        self.spec, self.budget = spec, budget
        self.layered = layered

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.manager = sync_playwright().start()
        try:
            self.browser = self.manager.chromium.launch(
                executable_path=browser_executable(), headless=True, timeout=min(30000, self.budget.remaining()*1000),
                # No persistent profile or remote debugging endpoint. These flags
                # suppress background services; network isolation below is per-context.
                args=["--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run", "--force-color-profile=srgb", "--disable-gpu", "--disable-gpu-compositing", "--disable-skia-runtime-opts"],
            )
            # Layout/rasterize at the DSL's canonical size, including previews.
            # Chromium's fractional CSS zoom caused rounded-edge pixel drift.
            # FFmpeg downsamples previews after capture; low FPS limits work.
            width, height = self.spec.video.width, self.spec.video.height
            self.context = self.browser.new_context(viewport={"width": width, "height": height},
                device_scale_factor=1, offline=True, service_workers="block", accept_downloads=False,
                locale="ko-KR", timezone_id="Asia/Seoul", color_scheme="light", reduced_motion="reduce")
            self.blocked_requests = 0
            def deny(route):
                self.blocked_requests += 1
                route.abort()
            self.context.route("**/*", deny)
            self.context.route_web_socket("**/*", lambda route: route.close())
            self.page = self.context.new_page()
            self.page.set_default_timeout(10000)
            self.page.set_content(template_html(), wait_until="load", timeout=min(10000, self.budget.remaining()*1000))
            if self.layered:
                self.page.evaluate("() => document.documentElement.classList.add('multimodal')")
            self.page.evaluate("() => document.fonts.ready")
            # Passed as serialized arguments, never interpolated into JS/HTML.
            self.layout = self.page.evaluate("value => window.AHA.init(value)", self.spec.model_dump())
            # Settle Chromium's first-paint compositing before returning frames.
            self.page.screenshot(type="png", animations="disabled", timeout=min(10000, self.budget.remaining()*1000))
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise RenderError("browser_failed", "프레임 브라우저를 시작할 수 없어요. Chrome 또는 Playwright Chromium 설치를 확인해 주세요.", self.budget.scene_id) from None

    def frame(self, seconds: float, *, subtitle=None, text_motion=False) -> tuple[bytes, dict]:
        self.budget.check()
        scene = next((s for s in self.spec.scenes if s.start_seconds <= seconds < s.end_seconds), self.spec.scenes[-1])
        self.budget.scene_id = scene.id
        try:
            state = self.page.evaluate("v => window.AHA.render(v.time, {subtitle:v.subtitle,text_motion:v.text_motion})",
                                       {"time":seconds,"subtitle":subtitle,"text_motion":text_motion})
            if state["overflow"]:
                raise RenderError("layout_overflow", "텍스트를 안전 영역에 배치할 수 없어요.", scene.id)
            frame = self.page.screenshot(type="png", animations="disabled", omit_background=self.layered,
                                         timeout=min(10000, self.budget.remaining()*1000))
        except RenderError:
            raise
        except Exception:
            raise RenderError("frame_failed", "장면 프레임을 생성하지 못했어요.", scene.id) from None
        return frame, state

    def __exit__(self, *_):
        try:
            if hasattr(self, "browser"):
                self.browser.close()
        finally:
            if hasattr(self, "manager"):
                self.manager.stop()
