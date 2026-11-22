"""Verify spending authorization with the production provider and an HTTP stand-in."""

from base64 import b64encode
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.providers.chatkhu.client import GatewayClient
from backend.app.providers.chatkhu.settings import ChatKHUSettings
from backend.app.providers.gemini import GeminiProvider
from backend.app.services import interactive, interactive_backgrounds as backgrounds
from test_chatkhu import png
from test_interactive import PROCESS, spec


@pytest.fixture
def gateway(monkeypatch):
    requests = []
    settings = ChatKHUSettings(api_key="fixture-chatkhu-key")
    data_url = "data:image/png;base64," + b64encode(png()).decode("ascii")
    monkeypatch.setattr(backgrounds, "get_chatkhu_settings", lambda: settings)
    backgrounds.plans.clear()
    backgrounds.cache.clear()

    def handle(request):
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        assert payload["aspect_ratio"] == "16:9" and payload["number_of_images"] == 1
        if request.url.path.endswith("/estimate/"):
            assert "prompt" not in payload and payload["kind"] == "image"
            return httpx.Response(200, json={"object": "estimate", "kind": "image", "model": settings.image_model,
                                             "credits": 34, "bound": "minimum"})
        assert request.url.path.endswith("/images/generate/")
        assert not payload.get("input_images")
        assert "Do not draw labels" in payload["prompt"]
        return httpx.Response(200, json={"data": [{"url": data_url}], "credits_charged": 36})

    monkeypatch.setattr(backgrounds, "GatewayClient", lambda value: GatewayClient(value, transport=httpx.MockTransport(handle)))
    yield requests, data_url
    backgrounds.plans.clear()
    backgrounds.cache.clear()


def test_background_needs_current_quote_and_uncapped_approval_then_reuses_validated_image(gateway):
    calls, data_url = gateway
    browser = TestClient(app)
    quote_url = "/api/learn/background/quote"
    generate_url = "/api/learn/background/generate"
    prompt = "Soft educational background of ocean below and clouds above."
    offered = backgrounds.offer_background(prompt)
    assert prompt in offered["prompt"]
    assert not calls
    fields = {"token": offered["token"], "quote_id": "x" * 24, "accept_cost": True, "accept_uncapped": True}
    assert browser.post(generate_url, json=fields).status_code == 409
    first = browser.post(quote_url, json={"token": offered["token"]}).json()
    latest = browser.post(quote_url, json={"token": offered["token"]}).json()
    assert first["credits"] == latest["credits"] == 34 and latest["bound"] == "minimum"
    assert browser.post(generate_url, json={**fields, "quote_id": first["quote_id"]}).status_code == 409
    fields["quote_id"] = latest["quote_id"]
    assert browser.post(generate_url, json={**fields, "accept_uncapped": False}).status_code == 428
    assert len(calls) == 2
    latest_image = browser.post(generate_url, json=fields)
    assert latest_image.json() == {"image": data_url, "credits_charged": 36, "cached": False}
    assert latest_image.headers["cache-control"] == "private, no-store"
    assert browser.post(generate_url, json=fields).status_code == 409
    second = backgrounds.offer_background(prompt)
    quote = browser.post(quote_url, json={"token": second["token"]}).json()
    cached = browser.post(generate_url, json={**fields, "token": second["token"], "quote_id": quote["quote_id"]})
    assert cached.json() == {"image": data_url, "credits_charged": None, "cached": True}
    assert sum(path.endswith("/images/generate/") for path, _ in calls) == 1


@pytest.mark.parametrize("description", [None, "A board with a wire coil on the right."])
def test_motion_scene_offers_a_background_even_without_gemini_recommendation(monkeypatch, gateway, description):
    calls, _ = gateway
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", api_key="fixture-gemini-key", cache_ttl_seconds=0)
    result = spec("전자기 유도 관찰", PROCESS)
    result["background_prompt"] = description
    result["motion_scene"] = {
        "actor": "막대자석",
        "landmarks": [{"label": "코일", "x": .72, "y": .48, "size": 75, "shape": "coil", "color": "violet"}],
        "states": [
            {"label": "멀리", "detail": "자석이 멀리 있어요.", "x": .2, "y": .48, "size": 55, "shape": "magnet", "color": "blue"},
            {"label": "가까이", "detail": "코일을 지나는 자기선속이 바뀌어요.", "x": .62, "y": .48, "size": 55, "shape": "magnet", "color": "blue"},
        ],
    }
    def handle(_):
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": json.dumps(result)}]}}]})

    monkeypatch.setattr(interactive, "GeminiProvider", lambda settings: GeminiProvider(settings, httpx.MockTransport(handle)))
    response = TestClient(app).post("/api/learn", files={
        "question": (None, "포함하지 않을 질문 원문"), "format": (None, "interactive"), "consent": (None, "true"),
    })
    assert response.status_code == 200
    offered = response.json()["lesson"]["background"]
    assert offered["recommended"] is bool(description)
    assert (description or "코일 in the middle right") in offered["prompt"]
    assert "포함하지 않을 질문 원문" not in offered["prompt"]
    assert not calls
