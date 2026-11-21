import asyncio
import json
from types import SimpleNamespace
from threading import Event

import httpx
import pytest

from backend.app.providers.chatkhu import ChatKHUSettings, GatewayClient, ChatKHUError
from backend.app.rendering.core import RenderError, RenderOptions
from backend.app.services import generated_video as video


def test_claude_gateway_uses_existing_bearer_and_counts_usage():
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        assert request.url.path == "/v1/gateway/claude/v1/messages/"
        assert request.headers["Authorization"] == "Bearer fixture-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert body["model"] == "claude-opus-5-5"
        assert body["max_tokens"] == 5500 and body["stream"] is False
        assert body["output_config"] == {"effort": "low"}
        assert body["system"] == "instructions"
        assert body["messages"] == [{"role": "user", "content": "example"}]
        return httpx.Response(200, json={"model": body["model"],
            "stop_reason": "end_turn", "content":[{"type":"thinking","thinking":""}, {"type":"text","text":"{}"}],
            "usage": {"input_tokens": 212, "output_tokens": 411}})

    with GatewayClient(ChatKHUSettings(api_key="fixture-key"), transport=httpx.MockTransport(handle)) as client:
        messages = [{"role": "system", "content": "instructions"}, {"role":"user","content":"example"}]
        assert client.complete_video_code(client.settings.code_model, messages) == "{}"
        assert client.events[-1]["input_tokens"] == 212
        assert client.events[-1]["output_tokens"] == 411
        with pytest.raises(ChatKHUError, match="1회"):
            client.complete_video_code(client.settings.code_model, [])
        assert len(requests) == 1


def test_image_and_text_become_reference_data():
    reference, image, grounding = asyncio.run(video.resolve_reference({
        "concept":"도형", "question":"각도를 설명해 줘.", "material_text":"설명 자료",
        "material":{"content_type":"image/png"}, "file_data":b"synthetic",
    }))
    messages = video.generation_messages(reference, image)
    assert messages[1]["content"][0]["type"] == "text"
    assert json.loads(messages[1]["content"][0]["text"])["material_text"] == "설명 자료"
    assert messages[1]["content"][1] == {"type":"image","source":{
        "type":"base64","media_type":"image/png","data":"c3ludGhldGlj",
    }}
    assert grounding["status"] == "image_supplied"


def test_truncated_claude_reply_records_actual_usage_without_returning_partial_code():
    def reply(request):
        return httpx.Response(200, json={"model":"claude-opus-5-5","stop_reason":"max_tokens",
            "content":[{"type":"text","text":"partial"}],"usage":{"input_tokens":764,"output_tokens":5500}})

    with GatewayClient(ChatKHUSettings(api_key="fixture-key"), transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ChatKHUError) as error:
            client.complete_video_code(client.settings.code_model, [])
        assert error.value.code == "code_output_limit"
        assert client.events[-2]["stop_reason"] == "max_tokens"
        assert client.events[-2]["output_tokens"] == 5500


def test_missing_isolation_prevents_first_billable_call(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise RenderError("isolated_unavailable", "Docker missing")

    def no_gateway(*args, **kwargs):
        pytest.fail("Gateway must not be touched")

    monkeypatch.setattr(video, "run_isolated", unavailable)
    with pytest.raises(RenderError) as failure:
        video.run_generated_video(tmp_path/"out.mp4", RenderOptions(), Event(), {}, None, {}, use_client=no_gateway)
    assert failure.value.code == "isolated_unavailable"
    assert not (tmp_path/"out.mp4").exists()


def test_second_validation_failure_has_one_repair_and_no_tts(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "get_chatkhu_settings", lambda: SimpleNamespace(code_model="claude-opus-5-5", repair_model="claude-opus-5-5"))
    attempts = []
    scene = {"title": "정의", "description":"개념 설명", "narration":"한글로 개념의 핵심을 설명하는 문장입니다.", "visual_plan":"두 도형의 변화"}
    code = "export default function Visual() { return <div/>; }"

    class Fixture:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass

        def complete_video_code(self, model, messages, *, repair=False):
            attempts.append(repair)
            if repair:
                return json.dumps({"tsx":code})
            return json.dumps({"title":"검사", "objective":"목표", "assumptions":[], "scenes":[scene]*3, "tsx":code})

    def reject(mode, *args, **kwargs):
        if mode != "check":
            raise RenderError("code_validation", "Test validation failure")

    monkeypatch.setattr(video, "run_isolated", reject)
    with pytest.raises(RenderError, match="Test validation"):
        video.run_generated_video(tmp_path/"out.mp4", RenderOptions(), Event(), {}, None, {}, use_client=Fixture)
    report_path = next(tmp_path.glob("code-*/report.json"))
    report = json.loads(report_path.read_text())
    assert attempts == [False, True]
    assert report["retries"] == 1 and len(report["render_errors"]) == 2
    assert not (tmp_path/"out.mp4").exists()


def test_web_claude_opt_in_consent_and_text(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import main
    from backend.app.video_config import VideoSettings
    import time

    monkeypatch.setattr(main, "get_video_settings", lambda: VideoSettings(root=tmp_path, renderer="claude"))
    calls = []

    def render(output, options, cancel, reference, image, grounding, **kwargs):
        calls.append((reference, image))
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"fixture")
        return {"mode":"claude_code","media":{},"grounding":grounding,"fallbacks":{}}

    monkeypatch.setattr(video, "run_generated_video", render)
    fields = {"concept": (None, "삼각형"), "format": (None, "shorts"),
              "file": ("lesson.txt", "세 각의 합은 180도".encode(), "text/plain")}
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["video_renderer"] == "claude"
        assert client.post("/api/videos", files=fields).status_code == 428
        assert not calls
        response = client.post("/api/videos", files={**fields, "consent":(None,"true")})
        assert response.status_code == 202
        url = response.headers["location"]
        for _ in range(100):
            result = client.get(url).json()
            if result["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(.01)
        assert result["status"] == "completed"
        assert result["result"]["mode"] == "claude_code"
        assert calls[0][0]["material_text"].strip() == "세 각의 합은 180도"
        assert client.get(url+"/file", headers={"Range":"bytes=0-2"}).content == b"fix"
