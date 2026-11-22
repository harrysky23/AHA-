import base64
import json

import httpx
from fastapi.testclient import TestClient
import pytest

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.providers import claude_interactive
from backend.app.providers.chatkhu import ChatKHUSettings, GatewayClient
from backend.app.services.interactive import interactive_cache
from pdf_fixture import pdf_bytes
from test_interactive import GRAPH, PNG, spec


@pytest.fixture
def claude_gateway(monkeypatch):
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", interactive_provider="claude")
    monkeypatch.setattr(claude_interactive, "get_chatkhu_settings",
                        lambda: ChatKHUSettings(api_key="fixture-chatkhu-secret"))
    requests = []
    interactive_cache.clear()
    result = spec("코일과 자석", GRAPH)
    result["motion_scene"] = {
        "actor": "자석", "landmarks": [],
        "states": [
            {"label": "접근 전", "detail": "자석을 코일에 가까이 가져가 봐요.", "x": .2, "y": .5,
             "size": 60, "shape": "magnet", "color": "blue"},
            {"label": "접근 중", "detail": "코일을 지나는 자기선속이 변해요.", "x": .68, "y": .5,
             "size": 60, "shape": "magnet", "color": "blue",
             "effects": [{"label": "자기선속 변화", "x": .75, "y": .53, "size": 65, "shape": "ring", "color": "yellow"}]},
        ],
    }
    result["background_prompt"] = "A coil on the right of a plain science lab bench."

    def handle(request):
        assert request.url.path == "/v1/gateway/claude/v1/messages/"
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert payload["model"] == "claude-opus-5-5" and payload["max_tokens"] == 5500
        assert "effects" in payload["system"]
        if payload["messages"][0]["content"] == '{"concept": "", "question": "크레딧 확인", "pdf_pages": []}':
            return httpx.Response(402, json={"detail": "insufficient credits"})
        return httpx.Response(200, json={
            "model": payload["model"], "stop_reason": "end_turn", "credits_charged": 6.5,
            "usage": {"input_tokens": 123, "output_tokens": 81},
            "content": [{"type": "text", "text": " ```json\n" + json.dumps(result) + "\n``` "}],
        })

    monkeypatch.setattr(claude_interactive, "GatewayClient",
                        lambda settings: GatewayClient(settings, transport=httpx.MockTransport(handle)))
    yield requests
    interactive_cache.clear()


def test_claude_interactive_requires_provider_specific_approval_and_caches_approved_image(claude_gateway):
    browser = TestClient(app)
    base = {"format": "interactive", "consent": "true"}
    file = {"file": ("private-filename.png", PNG, "image/png")}
    assert browser.get("/api/health").json()["interactive_provider"] == "claude"
    rejected = browser.post("/api/learn", data=base, files=file)
    assert rejected.status_code == 428 and rejected.json()["code"] == "claude_consent_required"
    base["consent"] = "claude"
    rejected_image = browser.post("/api/learn", data={**base, "image_consent": "true"}, files=file)
    assert rejected_image.status_code == 428 and rejected_image.json()["code"] == "image_consent_required"
    assert not claude_gateway
    endorsed = {**base, "image_consent": "claude"}
    result = browser.post("/api/learn", data=endorsed, files=file).json()
    assert result["mode"] == "claude"
    assert result["generation"]["usage"] == {"input_tokens": 123, "output_tokens": 81, "credits_charged": 6.5}
    assert result["lesson"]["spec"]["motion_scene"]["states"][1]["effects"][0]["shape"] == "ring"
    assert result["lesson"]["background"]["recommended"] is True
    assert result["material"]["sent_to_provider"]
    cached = browser.post("/api/learn", data=endorsed, files=file).json()
    assert cached["generation"]["cached"] and cached["generation"]["usage"] == {}
    assert len(claude_gateway) == 1
    text, image = claude_gateway[0]["messages"][0]["content"]
    assert json.loads(text["text"]) == {"concept": "", "question": "", "pdf_pages": []}
    assert image["source"]["media_type"] == "image/png"
    assert base64.b64decode(image["source"]["data"]) == PNG
    assert "private-filename.png" not in json.dumps(claude_gateway)


def test_claude_receives_pdf_text_and_does_not_retry_on_credit_failure(claude_gateway):
    client = TestClient(app)
    fragment = "Moving the magnet changes magnetic flux through the coil."
    response = client.post("/api/learn", data={"question": "자석을 움직이면?", "format": "interactive", "consent": "claude"},
                           files={"file": ("reference.pdf", pdf_bytes(fragment), "application/pdf")})
    assert response.status_code == 200
    assert fragment in json.loads(claude_gateway[0]["messages"][0]["content"])["pdf_pages"][0]["text"]
    rejected = client.post("/api/learn", files={"question": (None, "크레딧 확인"),
        "format": (None, "interactive"), "consent": (None, "claude")})
    assert rejected.status_code == 402 and rejected.json()["code"] == "claude_credits_unavailable"
    assert len(claude_gateway) == 2
