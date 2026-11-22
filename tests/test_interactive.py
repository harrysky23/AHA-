from base64 import b64decode
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.providers.gemini import GeminiProvider
from backend.app.services import interactive
from pdf_fixture import pdf_bytes

PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")
PROCESS = {
    "type": "process_diagram", "flow": "sequence",
    "nodes": [
        {"id": "before", "label": "빛 흡수", "detail": "엽록소가 빛 에너지를 흡수해요.", "x": .2, "y": .5, "color": "green"},
        {"id": "after", "label": "에너지 전환", "detail": "빛 에너지가 화학 에너지로 바뀌어요.", "x": .8, "y": .5, "color": "violet"},
    ],
    "edges": [{"id": "conversion", "source": "before", "target": "after", "label": "흡수한 에너지 사용"}],
}
GRAPH = {
    "type": "function_graph", "x_label": "시간", "y_label": "거리",
    "x_range": {"min": 0, "max": 4}, "y_range": {"min": 0, "max": 8},
    "curves": [{"id": "motion", "label": "일정한 속력", "coefficients": [0, 2], "color": "violet"}],
    "markers": [], "connectors": [], "marker_keyframes": [],
}
QUOTE = "Chlorophyll absorbs energy from light."


def spec(title, visual, source_quotes=None):
    return {
        "schema_version": "interactive-1", "title": title,
        "objective": "입력한 개념에서 원인과 결과를 설명해요.",
        "explanation": "관계를 직접 확인할 수 있는 예제예요.", "activity": "값을 바꾸고 결과를 관찰해 보세요.",
        "visualization": visual,
        "quiz": {"question": "무엇이 달라지나요?", "options": ["첫 번째", "두 번째", "세 번째"],
                 "correct_index": 1, "explanation": "실습에서 확인한 관계가 두 번째 설명과 일치해요."},
        "source_quotes": source_quotes or [], "limitations": [],
    }


@pytest.fixture
def fixture_provider(monkeypatch):
    received = []
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", api_key="stand-in-key")
    interactive.interactive_cache.clear()

    def handle(request):
        payload = json.loads(request.content)
        user = json.loads(payload["contents"][0]["parts"][0]["text"])
        received.append((user, payload["generationConfig"]["responseJsonSchema"]))
        if user["concept"] == "광합성의 에너지 전환":
            result = spec(user["concept"], PROCESS, [{"page": 1, "quote": QUOTE}])
        else:
            result = spec(user["concept"], GRAPH)
        return httpx.Response(200, json={
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}],
        })

    monkeypatch.setattr(interactive, "GeminiProvider", lambda settings: GeminiProvider(settings, httpx.MockTransport(handle)))
    yield received
    interactive.interactive_cache.clear()


def test_questions_select_different_interactions_and_cache_validated_spec(fixture_provider):
    client = TestClient(app)
    biology = {"concept": "광합성의 에너지 전환", "question": "빛을 흡수한 뒤 어떤 일이 일어나나요?",
               "format": "interactive", "consent": "true"}
    file = {"file": ("study.pdf", pdf_bytes(QUOTE), "application/pdf")}
    first = client.post("/api/learn", data=biology, files=file)
    again = client.post("/api/learn", data=biology, files=file)
    physics = client.post("/api/learn", files={
        key: (None, value) for key, value in {
            **biology, "concept": "등속 운동", "question": "시간을 두 배로 늘리면 거리가 왜 두 배가 되나요?",
        }.items()
    })
    assert first.status_code == again.status_code == physics.status_code == 200
    assert len(fixture_provider) == 2
    first, again, physics = first.json(), again.json(), physics.json()
    assert first["lesson"]["viewer_url"] == "/lessons/interactive"
    assert first["lesson"]["background"] is None
    assert first["lesson"]["spec"]["visualization"]["type"] == "process_diagram"
    assert first["lesson"]["spec"]["source_quotes"] == [{"page": 1, "quote": QUOTE}]
    assert first["material"]["sent_to_provider"]
    assert again["generation"]["cached"] and not again["material"]["sent_to_provider"]
    assert physics["lesson"]["spec"]["visualization"]["type"] == "function_graph"
    assert physics["title"] != first["title"]
    assert fixture_provider[0][0]["question"] == biology["question"]
    assert QUOTE in fixture_provider[0][0]["pdf_pages"][0]["text"]
    sent_schema = fixture_provider[0][1]
    for bound in ("minItems", "maxItems", "minimum", "maximum"):
        assert f'"{bound}":' not in json.dumps(sent_schema)
    variants = sent_schema["properties"]["visualization"]["anyOf"]
    assert {v["properties"]["type"]["enum"][0] for v in variants} == {
        "function_graph", "process_diagram", "timeline", "comparison", "state_transition", "text_explanation",
    }
    assert set(sent_schema["properties"]["motion_scene"]["properties"]) == {"actor", "landmarks", "states"}
    assert sent_schema["properties"]["background_prompt"]["type"] == ["string", "null"]


def test_new_route_checks_consent_before_generation(fixture_provider):
    response = TestClient(app).post("/api/learn", files={
        "question": (None, "빛은 어떻게 전달되나요?"), "format": (None, "interactive"),
    })
    assert response.status_code == 428
    assert not fixture_provider


def test_interactive_image_requires_specific_consent_and_keys_cache_by_image(monkeypatch):
    client = TestClient(app)
    requests = []
    interactive.interactive_cache.clear()
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", api_key="stand-in-key")

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(spec("사진 속 개념 실습", GRAPH))}],
        }}]})

    monkeypatch.setattr(interactive, "GeminiProvider", lambda settings: GeminiProvider(settings, httpx.MockTransport(handle)))

    def submit(image, *, consent=True):
        data = {"format": "interactive", "consent": "true"}
        if consent:
            data["image_consent"] = "true"
        return client.post("/api/learn", data=data, files={"file": ("example.png", image, "image/png")})

    rejected = submit(PNG, consent=False)
    assert rejected.status_code == 428 and rejected.json()["code"] == "image_consent_required"
    assert not requests

    first, cached, different = submit(PNG), submit(PNG), submit(PNG + b"other bytes")
    assert first.status_code == cached.status_code == different.status_code == 200
    assert len(requests) == 2
    assert first.json()["grounding"]["status"] == "image_provided"
    assert first.json()["material"]["sent_to_provider"] is True
    assert cached.json()["generation"]["cached"] is True
    assert cached.json()["material"]["sent_to_provider"] is False
    assert different.json()["generation"]["cached"] is False
    assert submit(PNG, consent=False).status_code == 428
    for request, image in zip(requests, (PNG, PNG + b"other bytes"), strict=True):
        text, attachment = request["contents"][0]["parts"]
        assert json.loads(text["text"]) == {"concept": "", "question": "", "pdf_pages": []}
        assert attachment["inlineData"]["mimeType"] == "image/png"
        assert b64decode(attachment["inlineData"]["data"]) == image
        assert "example.png" not in json.dumps(request)
    interactive.interactive_cache.clear()


@pytest.mark.parametrize(("statuses", "headers", "expected"), [
    ([503, 200], {}, 200),
    ([503, 503], {}, 503),
    ([503], {"Retry-After": "15"}, 503),
    ([429], {}, 429),
])
def test_interactive_retries_only_short_model_overload(monkeypatch, statuses, headers, expected):
    request_urls = []
    remaining = iter(statuses)
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", api_key="stand-in-key", cache_ttl_seconds=0)
    monkeypatch.setattr(interactive.random, "uniform", lambda low, high: 0.001)

    def handle(request):
        request_urls.append(request.url)
        status = next(remaining)
        if status != 200:
            return httpx.Response(status, headers=headers, json={"error": {"message": "The model is currently experiencing high demand."}})
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(spec("등속 운동", GRAPH))}],
        }}]})

    monkeypatch.setattr(interactive, "GeminiProvider", lambda settings: GeminiProvider(settings, httpx.MockTransport(handle)))
    response = TestClient(app).post("/api/learn", files={
        "question": (None, "이동 거리는 왜 시간에 비례하나요?"),
        "format": (None, "interactive"), "consent": (None, "true"),
    })
    assert response.status_code == expected
    assert len(request_urls) == len(statuses)
    assert len(set(request_urls)) == 1
    if headers:
        assert response.headers["Retry-After"] == headers["Retry-After"]


def test_rejects_executable_fields_and_invalid_learning_core():
    outputs = [
        spec("스크립트 삽입", {**GRAPH, "code": "alert(1)"}),
        {**spec("핵심 설명 검증", GRAPH), "explanation": "<script>alert(1)</script>"},
    ]
    for payload in outputs:
        with pytest.raises(interactive.LearningError) as error:
            interactive.parse_interactive(json.dumps(payload), [])
        assert error.value.code == "invalid_interactive_spec"


@pytest.mark.parametrize("changes", [
    {"x_range": {"min": 4, "max": 0}},
    {"x_range": {"min": 0, "max": 1001}},
    {"curves": [{**GRAPH["curves"][0], "id": f"curve_{index}"} for index in range(5)]},
])
def test_out_of_bounds_or_invalid_graph_keeps_explanation_and_quiz(changes):
    original = spec("시간과 이동 거리", {**GRAPH, **changes})
    lesson = interactive.parse_interactive(json.dumps(original), [])
    assert lesson.visualization.type == "text_explanation"
    assert lesson.visualization.fallback_reason == interactive.VISUAL_FALLBACK
    assert lesson.visualization.paragraphs == [original["explanation"]]
    assert lesson.quiz.model_dump() == original["quiz"]


def test_process_with_invalid_layout_keeps_safe_node_labels_and_details():
    nodes = [{**node, "x": 120} for node in PROCESS["nodes"]]
    process = {**PROCESS, "nodes": nodes}
    lesson = interactive.parse_interactive(json.dumps(spec("광합성에서 에너지 이동", process)), [])
    assert lesson.visualization.type == "step_explorer"
    assert [step.model_dump() for step in lesson.visualization.steps] == [
        {"label": node["label"], "detail": node["detail"]} for node in nodes
    ]
    assert lesson.quiz is not None


@pytest.mark.parametrize("visual", [
    {**GRAPH, "x_range": {"min": 0, "max": 5000}},
    {"type": "text_explanation", "heading": "시간과 거리", "paragraphs": ["거리는 시간에 비례해요."],
     "fallback_reason": "핵심 내용을 단계로 살펴봐요."},
])
def test_topic_specific_exploration_steps_are_used_when_graph_is_unavailable(visual):
    generated = spec("등속 운동의 관찰", visual)
    generated["exploration_steps"] = [
        {"label": "1초 후", "detail": "이동 거리는 2m예요."},
        {"label": "2초 후", "detail": "시간이 두 배가 되면서 이동 거리는 4m가 돼요."},
    ]
    lesson = interactive.parse_interactive(json.dumps(generated), [])
    assert lesson.visualization.type == "step_explorer"
    assert [step.model_dump() for step in lesson.visualization.steps] == generated["exploration_steps"]


def test_validated_motion_scene_accepts_topic_specific_objects_and_visible_changes():
    response = spec("코일 주변 자석 움직이기", PROCESS)
    response["motion_scene"] = {
        "actor": "막대자석",
        "landmarks": [{"label": "코일", "x": .66, "y": .5, "size": 77, "shape": "coil", "color": "violet"}],
        "states": [
            {"label": "떨어져 있을 때", "detail": "코일에서 멀리 있어요.", "x": .2, "y": .5,
             "size": 52, "shape": "magnet", "color": "blue"},
            {"label": "가까워질 때", "detail": "코일을 지나는 자기선속이 변해요.", "x": .56, "y": .5,
             "size": 52, "shape": "magnet", "color": "pink"},
        ],
    }
    lesson = interactive.parse_interactive(json.dumps(response), [])
    assert lesson.motion_scene.model_dump(exclude_defaults=True) == response["motion_scene"]
    response["motion_scene"]["states"][1]["shape"] = "url(https://example.test)"
    assert interactive.parse_interactive(json.dumps(response), []).motion_scene is None
    response["motion_scene"]["states"][1] = {
        **response["motion_scene"]["states"][0], "label": "이름만 바뀜",
    }
    assert interactive.parse_interactive(json.dumps(response), []).motion_scene is None


def test_unmatched_quote_is_removed_and_valid_quote_is_preserved():
    quotes = [{"page": 1, "quote": "Not in the PDF"}, {"page": 1, "quote": QUOTE}]
    result = interactive.parse_interactive(json.dumps(spec("광합성", PROCESS, quotes)), [{"page": 1, "text": QUOTE}])
    assert [quote.model_dump() for quote in result.source_quotes] == [quotes[1]]
    assert result.visualization.type == "process_diagram"


def test_image_overload_then_out_of_range_model_output_opens_same_material(monkeypatch):
    calls = []
    app.dependency_overrides[get_settings] = lambda: Settings(mode="gemini", api_key="stand-in-key", cache_ttl_seconds=0)
    monkeypatch.setattr(interactive.random, "uniform", lambda low, high: 0.001)
    result = spec("사진에 있는 직선의 기울기", {**GRAPH, "x_range": {"min": 0, "max": 5000}},
                  [{"page": 21, "quote": "Invented source for an image"}])
    result["quiz"]["correct_index"] = 3

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"message": "The model is currently experiencing high demand."}})
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(result)}],
        }}]})

    monkeypatch.setattr(interactive, "GeminiProvider", lambda settings: GeminiProvider(settings, httpx.MockTransport(handle)))
    response = TestClient(app).post("/api/learn",
        data={"format": "interactive", "consent": "true", "image_consent": "true"},
        files={"file": ("study.png", PNG, "image/png")})

    assert response.status_code == 200
    assert len(calls) == 2 and calls[0].content == calls[1].content
    data = response.json()
    assert data["lesson"]["viewer_url"] == "/lessons/interactive"
    assert data["title"] == result["title"] and data["grounding"]["status"] == "image_provided"
    lesson = data["lesson"]["spec"]
    assert lesson["visualization"]["type"] == "text_explanation"
    assert lesson["explanation"] == result["explanation"]
    assert lesson["quiz"] is None and lesson["source_quotes"] == []
    assert interactive.VISUAL_FALLBACK in data["notice"] and interactive.QUIZ_FALLBACK in data["notice"]


def test_interactive_viewer_uses_local_hashed_script_in_opaque_sandbox():
    response = TestClient(app).get("/lessons/interactive")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'sha256-" in csp
    assert "connect-src 'none'" in csp
    assert "sandbox allow-scripts" in csp
    assert "allow-same-origin" not in csp
    assert "__INTERACTIVE_SCRIPT__" not in response.text
    assert "__MOTION_SCENE_SCRIPT__" not in response.text
    assert "mountMotionScene" in response.text
