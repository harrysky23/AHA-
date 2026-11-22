"""Verify spending authorization with the production provider and an HTTP stand-in."""

from base64 import b64encode
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.main import app
from backend.app.providers.chatkhu.client import GatewayClient
from backend.app.providers.chatkhu.settings import ChatKHUSettings
from backend.app.services import interactive_backgrounds as backgrounds
from test_chatkhu import png


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
