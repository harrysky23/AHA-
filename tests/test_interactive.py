import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.providers.gemini import GeminiProvider
from backend.app.services import interactive
from pdf_fixture import pdf_bytes

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


def test_new_route_checks_consent_before_generation(fixture_provider):
    response = TestClient(app).post("/api/learn", files={
        "question": (None, "빛은 어떻게 전달되나요?"), "format": (None, "interactive"),
    })
    assert response.status_code == 428
    assert not fixture_provider


def test_rejects_fabricated_quote_executable_fields_and_bounds_enforced_locally():
    too_many_curves = [{**GRAPH["curves"][0], "id": f"curve_{index}"} for index in range(5)]
    invalid_quiz = spec("보기 수 제한", GRAPH)
    invalid_quiz["quiz"]["options"].append("네 번째")
    invalid_outputs = [
        spec("가짜 인용", GRAPH, [{"page": 1, "quote": "Not in the PDF"}]),
        spec("스크립트 삽입", {**GRAPH, "code": "alert(1)"}),
        spec("곡선 수 제한", {**GRAPH, "curves": too_many_curves}),
        spec("좌표 범위", {**GRAPH, "x_range": {"min": 0, "max": 1001}}),
        invalid_quiz,
    ]
    for payload in invalid_outputs:
        with pytest.raises(interactive.LearningError) as error:
            interactive.parse_interactive(json.dumps(payload), [{"page": 1, "text": QUOTE}])
        assert error.value.code == "invalid_interactive_spec"


def test_interactive_viewer_uses_local_hashed_script_in_opaque_sandbox():
    response = TestClient(app).get("/lessons/interactive")
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'sha256-" in csp
    assert "connect-src 'none'" in csp
    assert "sandbox allow-scripts" in csp
    assert "allow-same-origin" not in csp
    assert "__INTERACTIVE_SCRIPT__" not in response.text
